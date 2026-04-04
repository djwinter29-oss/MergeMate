"""SQLite persistence for runs and conversation messages."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.repository import ApprovalDecision
from mergemate.domain.runs.value_objects import RunStatus


def _to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


@dataclass(slots=True)
class SQLiteDatabase:
    path: Path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    run_id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    workflow TEXT NOT NULL,
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

                CREATE INDEX IF NOT EXISTS idx_learning_entries_chat_id_created_at
                    ON learning_entries(chat_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_tool_events_run_id_created_at
                    ON tool_events(run_id, created_at DESC);
                """
            )
            self._ensure_column(connection, "agent_runs", "current_stage", "TEXT NOT NULL DEFAULT 'planning'")
            self._ensure_column(connection, "agent_runs", "plan_text", "TEXT")
            self._ensure_column(connection, "agent_runs", "design_text", "TEXT")
            self._ensure_column(connection, "agent_runs", "test_text", "TEXT")
            self._ensure_column(connection, "agent_runs", "review_text", "TEXT")
            self._ensure_column(connection, "agent_runs", "review_iterations", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(connection, "agent_runs", "approved", "INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        existing_columns = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()


class SQLiteRunRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, run: AgentRun) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, chat_id, user_id, agent_name, workflow, status,
                    current_stage, prompt, estimate_seconds, plan_text, design_text,
                    test_text, review_text, review_iterations, approved, result_text,
                    error_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.chat_id,
                    run.user_id,
                    run.agent_name,
                    run.workflow,
                    run.status.value,
                    run.current_stage,
                    run.prompt,
                    run.estimate_seconds,
                    run.plan_text,
                    run.design_text,
                    run.test_text,
                    run.review_text,
                    run.review_iterations,
                    int(run.approved),
                    run.result_text,
                    run.error_text,
                    run.created_at.isoformat(),
                    run.updated_at.isoformat(),
                ),
            )

    def get(self, run_id: str) -> AgentRun | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return self._row_to_run(row) if row is not None else None

    def list_for_chat(self, chat_id: int, limit: int = 5) -> list[AgentRun]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agent_runs
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        expected_current_status: RunStatus | None = None,
        current_stage: str | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> AgentRun | None:
        existing = self.get(run_id)
        if existing is None:
            return None

        updated_at = datetime.now(UTC)
        query = """
                UPDATE agent_runs
                SET status = ?,
                    current_stage = ?,
                    result_text = ?,
                    error_text = ?,
                    updated_at = ?
                WHERE run_id = ?
                """
        parameters: list[object] = [
            status.value,
            current_stage or existing.current_stage,
            result_text if result_text is not None else existing.result_text,
            error_text if error_text is not None else existing.error_text,
            updated_at.isoformat(),
            run_id,
        ]
        if expected_current_status is not None:
            query += " AND status = ?"
            parameters.append(expected_current_status.value)
        with self._database.connection() as connection:
            connection.execute(query, tuple(parameters))
        return self.get(run_id)

    def update_plan(
        self,
        run_id: str,
        plan_text: str,
        prompt: str | None = None,
        *,
        current_stage: str | None = None,
    ) -> AgentRun | None:
        existing = self.get(run_id)
        if existing is None:
            return None
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET plan_text = ?, prompt = ?, current_stage = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    plan_text,
                    prompt if prompt is not None else existing.prompt,
                    current_stage or "awaiting_user_confirmation",
                    datetime.now(UTC).isoformat(),
                    run_id,
                ),
            )
        return self.get(run_id)

    def approve(self, run_id: str) -> ApprovalDecision:
        existing = self.get(run_id)
        if existing is None:
            return ApprovalDecision(run=None, transitioned=False)
        if existing.approved:
            return ApprovalDecision(run=existing, transitioned=False)
        if existing.status not in {RunStatus.AWAITING_CONFIRMATION, RunStatus.QUEUED}:
            return ApprovalDecision(run=existing, transitioned=False)

        next_status = RunStatus.QUEUED.value if existing.status == RunStatus.AWAITING_CONFIRMATION else existing.status.value
        next_stage = (
            "queued_for_execution"
            if existing.status == RunStatus.AWAITING_CONFIRMATION
            else existing.current_stage
        )
        with self._database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET approved = 1, status = ?, current_stage = ?, updated_at = ?
                WHERE run_id = ?
                  AND approved = 0
                  AND status = ?
                """,
                (next_status, next_stage, datetime.now(UTC).isoformat(), run_id, existing.status.value),
            )
        return ApprovalDecision(run=self.get(run_id), transitioned=cursor.rowcount > 0)

    def save_artifacts(
        self,
        run_id: str,
        *,
        current_stage: str | None = None,
        design_text: str | None = None,
        test_text: str | None = None,
        review_text: str | None = None,
        result_text: str | None = None,
        review_iterations: int | None = None,
    ) -> AgentRun | None:
        existing = self.get(run_id)
        if existing is None:
            return None
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET current_stage = ?,
                    design_text = ?,
                    test_text = ?,
                    review_text = ?,
                    result_text = ?,
                    review_iterations = ?,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (
                    current_stage or existing.current_stage,
                    design_text if design_text is not None else existing.design_text,
                    test_text if test_text is not None else existing.test_text,
                    review_text if review_text is not None else existing.review_text,
                    result_text if result_text is not None else existing.result_text,
                    review_iterations if review_iterations is not None else existing.review_iterations,
                    datetime.now(UTC).isoformat(),
                    run_id,
                ),
            )
        return self.get(run_id)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> AgentRun:
        return AgentRun(
            run_id=row["run_id"],
            chat_id=row["chat_id"],
            user_id=row["user_id"],
            agent_name=row["agent_name"],
            workflow=row["workflow"],
            status=RunStatus(row["status"]),
            current_stage=row["current_stage"],
            prompt=row["prompt"],
            estimate_seconds=row["estimate_seconds"],
            plan_text=row["plan_text"],
            design_text=row["design_text"],
            test_text=row["test_text"],
            review_text=row["review_text"],
            review_iterations=row["review_iterations"],
            approved=bool(row["approved"]),
            result_text=row["result_text"],
            error_text=row["error_text"],
            created_at=_to_datetime(row["created_at"]),
            updated_at=_to_datetime(row["updated_at"]),
        )


class SQLiteConversationRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO conversation_messages (chat_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, role, content, datetime.now(UTC).isoformat()),
            )

    def list_messages(self, chat_id: int, limit: int = 8) -> list[dict[str, str]]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversation_messages
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


class SQLiteLearningRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(self, chat_id: int, workflow: str, prompt: str, result_excerpt: str) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO learning_entries (chat_id, workflow, prompt, result_excerpt, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, workflow, prompt, result_excerpt, datetime.now(UTC).isoformat()),
            )

    def list_recent(self, chat_id: int, limit: int = 3) -> list[dict[str, str]]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT workflow, prompt, result_excerpt
                FROM learning_entries
                WHERE chat_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [
            {
                "workflow": row["workflow"],
                "prompt": row["prompt"],
                "result_excerpt": row["result_excerpt"],
            }
            for row in rows
        ]


class SQLiteToolEventRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(self, run_id: str, tool_name: str, action: str, status: str, detail: str) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO tool_events (run_id, tool_name, action, status, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, tool_name, action, status, detail, datetime.now(UTC).isoformat()),
            )

    def list_for_run(self, run_id: str, limit: int = 20) -> list[dict[str, str]]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT tool_name, action, status, detail, created_at
                FROM tool_events
                WHERE run_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (run_id, limit),
            ).fetchall()
        return [
            {
                "tool_name": row["tool_name"],
                "action": row["action"],
                "status": row["status"],
                "detail": row["detail"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]