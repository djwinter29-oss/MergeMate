"""SQLite schema, migrations, and connection management."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterator

from mergemate.domain.shared import RunStage

from .sqlite_common import (
    agent_runs_search_text_sql,
    conversation_messages_search_text_sql,
)


def _ensure_column(
    connection: sqlite3.Connection, table_name: str, column_name: str, definition: str
) -> None:
    existing_columns = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? AND type = 'table'",
        (table_name,),
    ).fetchone()
    return row is not None


def _ensure_search_triggers(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        CREATE TRIGGER IF NOT EXISTS agent_runs_ai AFTER INSERT ON agent_runs BEGIN
            INSERT INTO agent_runs_fts(rowid, search_text)
            VALUES (new.rowid, {agent_runs_search_text_sql("new")});
        END;

        CREATE TRIGGER IF NOT EXISTS agent_runs_ad AFTER DELETE ON agent_runs BEGIN
            DELETE FROM agent_runs_fts WHERE rowid = old.rowid;
        END;

        CREATE TRIGGER IF NOT EXISTS agent_runs_au AFTER UPDATE ON agent_runs BEGIN
            DELETE FROM agent_runs_fts WHERE rowid = old.rowid;
            INSERT INTO agent_runs_fts(rowid, search_text)
            VALUES (new.rowid, {agent_runs_search_text_sql("new")});
        END;

        CREATE TRIGGER IF NOT EXISTS conversation_messages_ai AFTER INSERT ON conversation_messages BEGIN
            INSERT INTO conversation_messages_fts(rowid, search_text)
            VALUES (new.rowid, {conversation_messages_search_text_sql("new")});
        END;

        CREATE TRIGGER IF NOT EXISTS conversation_messages_ad AFTER DELETE ON conversation_messages BEGIN
            DELETE FROM conversation_messages_fts WHERE rowid = old.rowid;
        END;

        CREATE TRIGGER IF NOT EXISTS conversation_messages_au AFTER UPDATE ON conversation_messages BEGIN
            DELETE FROM conversation_messages_fts WHERE rowid = old.rowid;
            INSERT INTO conversation_messages_fts(rowid, search_text)
            VALUES (new.rowid, {conversation_messages_search_text_sql("new")});
        END;
        """
    )


def _rebuild_agent_runs_search_index(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        INSERT INTO agent_runs_fts(rowid, search_text)
        SELECT rowid, {agent_runs_search_text_sql("agent_runs")}
        FROM agent_runs
        """
    )


def _rebuild_conversation_messages_search_index(connection: sqlite3.Connection) -> None:
    connection.execute(
        f"""
        INSERT INTO conversation_messages_fts(rowid, search_text)
        SELECT rowid, {conversation_messages_search_text_sql("conversation_messages")}
        FROM conversation_messages
        """
    )


def initialize_sqlite_database(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            run_id TEXT PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            agent_name TEXT NOT NULL,
            workflow TEXT NOT NULL,
            repo_name TEXT,
            status TEXT NOT NULL,
            current_stage TEXT NOT NULL,
            prompt TEXT NOT NULL,
            estimate_seconds INTEGER NOT NULL,
            plan_text TEXT,
            design_text TEXT,
            test_text TEXT,
            review_text TEXT,
            review_iterations INTEGER NOT NULL DEFAULT 0,
            approved INTEGER NOT NULL DEFAULT 0,
            result_text TEXT,
            error_text TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_jobs (
            job_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            lease_owner TEXT,
            lease_expires_at TEXT,
            last_heartbeat_at TEXT,
            error_text TEXT,
            queued_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS learning_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            workflow TEXT NOT NULL,
            prompt TEXT NOT NULL,
            result_excerpt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tool_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_agent_runs_chat_id_created_at
            ON agent_runs(chat_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_conversation_messages_chat_id_created_at
            ON conversation_messages(chat_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_run_jobs_run_id_queued_at
            ON run_jobs(run_id, queued_at DESC);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_run_jobs_unique_active_job
            ON run_jobs(run_id, job_type)
            WHERE status IN ('queued', 'running');

        CREATE INDEX IF NOT EXISTS idx_learning_entries_chat_id_created_at
            ON learning_entries(chat_id, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_tool_events_run_id_created_at
            ON tool_events(run_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS repo_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            repo_name TEXT NOT NULL,
            topic TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_repo_knowledge_chat_repo
            ON repo_knowledge(chat_id, repo_name, created_at DESC);
        """
    )
    _ensure_column(
        connection,
        "agent_runs",
        "current_stage",
        f"TEXT NOT NULL DEFAULT '{RunStage.PLANNING.value}'",
    )
    _ensure_column(connection, "agent_runs", "plan_text", "TEXT")
    _ensure_column(connection, "agent_runs", "design_text", "TEXT")
    _ensure_column(connection, "agent_runs", "test_text", "TEXT")
    _ensure_column(connection, "agent_runs", "review_text", "TEXT")
    _ensure_column(connection, "agent_runs", "review_iterations", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "agent_runs", "approved", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "run_jobs", "attempt_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "run_jobs", "lease_owner", "TEXT")
    _ensure_column(connection, "run_jobs", "lease_expires_at", "TEXT")
    _ensure_column(connection, "learning_entries", "learning_lessons", "TEXT")
    _ensure_column(connection, "run_jobs", "last_heartbeat_at", "TEXT")
    _ensure_column(connection, "agent_runs", "repo_name", "TEXT")

    if not _table_exists(connection, "agent_runs_fts"):
        connection.execute(
            "CREATE VIRTUAL TABLE agent_runs_fts USING fts5(search_text, tokenize='porter')"
        )
        _rebuild_agent_runs_search_index(connection)
    if not _table_exists(connection, "conversation_messages_fts"):
        connection.execute(
            "CREATE VIRTUAL TABLE conversation_messages_fts USING fts5(search_text, tokenize='porter')"
        )
        _rebuild_conversation_messages_search_index(connection)

    _ensure_search_triggers(connection)


@dataclass(slots=True)
class SQLiteDatabase:
    path: Path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            initialize_sqlite_database(connection)

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection, table_name: str, column_name: str, definition: str
    ) -> None:
        _ensure_column(connection, table_name, column_name, definition)

    @staticmethod
    def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
        return _table_exists(connection, table_name)

    @staticmethod
    def _agent_runs_search_text_sql(prefix: str) -> str:
        return agent_runs_search_text_sql(prefix)

    @staticmethod
    def _conversation_messages_search_text_sql(prefix: str) -> str:
        return conversation_messages_search_text_sql(prefix)

    @staticmethod
    def _fts_quote(token: str) -> str:
        from .sqlite_common import fts_quote

        return fts_quote(token)

    @classmethod
    def _build_fts_query(cls, query: str) -> str | None:
        from .sqlite_common import build_fts_query

        return build_fts_query(query)

    def _ensure_search_triggers(self, connection: sqlite3.Connection) -> None:
        _ensure_search_triggers(connection)

    def _rebuild_agent_runs_search_index(self, connection: sqlite3.Connection) -> None:
        _rebuild_agent_runs_search_index(connection)

    def _rebuild_conversation_messages_search_index(self, connection: sqlite3.Connection) -> None:
        _rebuild_conversation_messages_search_index(connection)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


__all__ = ["SQLiteDatabase", "initialize_sqlite_database"]
