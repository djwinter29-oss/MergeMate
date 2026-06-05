# mypy: allow-untyped-defs
"""SQLite repository implementations for runs, conversations, jobs, and knowledge."""

from __future__ import annotations

from datetime import UTC, datetime
import sqlite3
from uuid import uuid4
from typing import Any

from mergemate.domain.runs.entities import AgentRun, RunJob
from mergemate.domain.runs.repository import (
    ApprovalDecision,
    QueuedRunJobDecision,
    StatusUpdateDecision,
)
from mergemate.domain.shared import RunJobStatus, RunJobType, RunStage, RunStatus

from .sqlite_common import _to_datetime, build_fts_query
from .sqlite_schema import SQLiteDatabase


class SQLiteRunRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def create(self, run: AgentRun) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, chat_id, user_id, agent_name, workflow, repo_name, status,
                    current_stage, prompt, estimate_seconds, plan_text, design_text,
                    test_text, review_text, review_iterations, approved, result_text,
                    error_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.chat_id,
                    run.user_id,
                    run.agent_name,
                    run.workflow,
                    run.repo_name,
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

    def search(self, query: str, limit: int = 10, *, chat_id: int | None = None) -> list[AgentRun]:
        fts_query = build_fts_query(query)
        if fts_query is None:
            return []

        with self._database.connection() as connection:
            try:
                query_sql = """
                    SELECT agent_runs.*, bm25(agent_runs_fts) AS _score
                    FROM agent_runs_fts
                    JOIN agent_runs ON agent_runs.rowid = agent_runs_fts.rowid
                    WHERE agent_runs_fts MATCH ?
                """
                parameters: list[object] = [fts_query]
                if chat_id is not None:
                    query_sql += " AND agent_runs.chat_id = ?"
                    parameters.append(chat_id)
                query_sql += " ORDER BY _score ASC, agent_runs.updated_at DESC LIMIT ?"
                parameters.append(limit)
                rows = connection.execute(query_sql, tuple(parameters)).fetchall()
                return [self._row_to_run(row) for row in rows]
            except sqlite3.OperationalError:
                pass

        return self._search_with_like(query, limit, chat_id=chat_id)

    def _search_with_like(
        self, query: str, limit: int = 10, *, chat_id: int | None = None
    ) -> list[AgentRun]:
        terms = [t.strip().lower() for t in query.split() if t.strip()]
        if not terms:
            return []

        search_fields = [
            "lower(coalesce(run_id, ''))",
            "lower(coalesce(agent_name, ''))",
            "lower(coalesce(workflow, ''))",
            "lower(coalesce(status, ''))",
            "lower(coalesce(current_stage, ''))",
            "lower(coalesce(prompt, ''))",
            "lower(coalesce(plan_text, ''))",
            "lower(coalesce(design_text, ''))",
            "lower(coalesce(test_text, ''))",
            "lower(coalesce(review_text, ''))",
            "lower(coalesce(result_text, ''))",
            "lower(coalesce(error_text, ''))",
        ]

        term_clauses: list[str] = []
        for term in terms:
            parts = " OR ".join(f"{fld} LIKE ?" for fld in search_fields)
            term_clauses.append(f"({parts})")

        where_sql = " AND ".join(term_clauses)
        chat_where = ""
        if chat_id is not None:
            chat_where = " AND chat_id = ?"

        score_parts: list[str] = []
        for fld in search_fields:
            term_counts = " + ".join(f"CASE WHEN {fld} LIKE ? THEN 1 ELSE 0 END" for _ in terms)
            full_phrase_bonus = f"CASE WHEN {fld} LIKE ? THEN 1 ELSE 0 END"
            score_parts.append(f"({term_counts} + {full_phrase_bonus})")

        relevance_score = " + ".join(score_parts)

        score_params: list[object] = []
        for fld in search_fields:
            for term in terms:
                score_params.append(f"%{term}%")
        for fld in search_fields:
            score_params.append(f"%{query.lower()}%")

        where_params: list[object] = []
        for term in terms:
            like_param = f"%{term}%"
            where_params.extend([like_param] * len(search_fields))
        if chat_id is not None:
            where_params.append(chat_id)

        parameters: list[object] = score_params + where_params + [limit]
        query_sql = f"""
                SELECT *, ({relevance_score}) AS _score
                FROM agent_runs
                WHERE {where_sql}{chat_where}
                ORDER BY _score DESC, updated_at DESC
                LIMIT ?
                """

        with self._database.connection() as connection:
            rows = connection.execute(query_sql, tuple(parameters)).fetchall()
        return [self._row_to_run(row) for row in rows]

    def try_update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        expected_current_status: RunStatus | None = None,
        current_stage: str | RunStage | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> StatusUpdateDecision:
        existing = self.get(run_id)
        if existing is None:
            return StatusUpdateDecision(run=None, transitioned=False)

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
            cursor = connection.execute(query, tuple(parameters))
        return StatusUpdateDecision(run=self.get(run_id), transitioned=cursor.rowcount > 0)

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        expected_current_status: RunStatus | None = None,
        current_stage: str | RunStage | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> AgentRun | None:
        decision = self.try_update_status(
            run_id,
            status,
            expected_current_status=expected_current_status,
            current_stage=current_stage,
            result_text=result_text,
            error_text=error_text,
        )
        return decision.run

    def update_plan(
        self,
        run_id: str,
        plan_text: str,
        prompt: str | None = None,
        *,
        current_stage: str | RunStage | None = None,
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
                    current_stage or RunStage.AWAITING_USER_CONFIRMATION,
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

        next_status = (
            RunStatus.QUEUED.value
            if existing.status == RunStatus.AWAITING_CONFIRMATION
            else existing.status.value
        )
        next_stage = (
            RunStage.QUEUED_FOR_EXECUTION
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
                (
                    next_status,
                    next_stage,
                    datetime.now(UTC).isoformat(),
                    run_id,
                    existing.status.value,
                ),
            )
        return ApprovalDecision(run=self.get(run_id), transitioned=cursor.rowcount > 0)

    def save_artifacts(
        self,
        run_id: str,
        *,
        current_stage: str | RunStage | None = None,
        design_text: str | None = None,
        test_text: str | None = None,
        review_text: str | None = None,
        result_text: str | None = None,
        review_iterations: int | None = None,
        **extra: Any,
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
                    review_iterations
                    if review_iterations is not None
                    else existing.review_iterations,
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
            repo_name=row["repo_name"],
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

    def search_messages(
        self,
        query: str,
        limit: int = 10,
        *,
        chat_id: int | None = None,
    ) -> list[dict[str, str | int]]:
        fts_query = build_fts_query(query)
        if fts_query is None:
            return []

        with self._database.connection() as connection:
            try:
                query_sql = """
                    SELECT conversation_messages.chat_id,
                           conversation_messages.role,
                           conversation_messages.content,
                           conversation_messages.created_at,
                           bm25(conversation_messages_fts) AS _score
                    FROM conversation_messages_fts
                    JOIN conversation_messages ON conversation_messages.rowid = conversation_messages_fts.rowid
                    WHERE conversation_messages_fts MATCH ?
                """
                parameters: list[object] = [fts_query]
                if chat_id is not None:
                    query_sql += " AND conversation_messages.chat_id = ?"
                    parameters.append(chat_id)
                query_sql += " ORDER BY _score ASC, conversation_messages.created_at DESC LIMIT ?"
                parameters.append(limit)
                rows = connection.execute(query_sql, tuple(parameters)).fetchall()
                return [
                    {
                        "chat_id": row["chat_id"],
                        "role": row["role"],
                        "content": row["content"],
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]
            except sqlite3.OperationalError:
                pass

        return self._search_messages_with_like(query, limit, chat_id=chat_id)

    def _search_messages_with_like(
        self,
        query: str,
        limit: int = 10,
        *,
        chat_id: int | None = None,
    ) -> list[dict[str, str | int]]:
        terms = [t.strip().lower() for t in query.split() if t.strip()]
        if not terms:
            return []

        term_clauses = ["lower(coalesce(content, '')) LIKE ?" for _ in terms]
        where_sql = " AND ".join(term_clauses)
        where_params: list[object] = []
        for term in terms:
            where_params.append(f"%{term}%")
        if chat_id is not None:
            where_sql += " AND chat_id = ?"
            where_params.append(chat_id)

        term_score = " + ".join(
            "CASE WHEN lower(coalesce(content, '')) LIKE ? THEN 1 ELSE 0 END" for _ in terms
        )
        phrase_bonus = "CASE WHEN lower(coalesce(content, '')) LIKE ? THEN 1 ELSE 0 END"
        relevance_score = f"({term_score} + {phrase_bonus})"

        score_params = [f"%{t}%" for t in terms] + [f"%{query.lower()}%"]

        query_sql = f"""
                SELECT chat_id, role, content, created_at, ({relevance_score}) AS _score
                FROM conversation_messages
                WHERE {where_sql}
                ORDER BY _score DESC, created_at DESC
                LIMIT ?
                """
        all_params = score_params + where_params + [limit]

        with self._database.connection() as connection:
            rows = connection.execute(query_sql, tuple(all_params)).fetchall()
        return [
            {
                "chat_id": row["chat_id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]


class SQLiteRunJobRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def ensure_queued_job(
        self,
        run_id: str,
        *,
        job_type: RunJobType = RunJobType.EXECUTE_RUN,
    ) -> QueuedRunJobDecision:
        now = datetime.now(UTC)
        job = RunJob(
            job_id=str(uuid4()),
            run_id=run_id,
            job_type=job_type,
            status=RunJobStatus.QUEUED,
            attempt_count=0,
            lease_owner=None,
            lease_expires_at=None,
            last_heartbeat_at=None,
            error_text=None,
            queued_at=now,
            started_at=None,
            finished_at=None,
            updated_at=now,
        )
        try:
            with self._database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO run_jobs (
                        job_id, run_id, job_type, status, attempt_count,
                        lease_owner, lease_expires_at, last_heartbeat_at, error_text,
                        queued_at, started_at, finished_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job.job_id,
                        job.run_id,
                        job.job_type.value,
                        job.status.value,
                        job.attempt_count,
                        job.lease_owner,
                        job.lease_expires_at.isoformat()
                        if job.lease_expires_at is not None
                        else None,
                        job.last_heartbeat_at.isoformat()
                        if job.last_heartbeat_at is not None
                        else None,
                        job.error_text,
                        job.queued_at.isoformat(),
                        job.started_at.isoformat() if job.started_at is not None else None,
                        job.finished_at.isoformat() if job.finished_at is not None else None,
                        job.updated_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.get_active_for_run(run_id, job_type=job_type)
            if existing is None:
                raise
            return QueuedRunJobDecision(job=existing, created=False)
        return QueuedRunJobDecision(job=job, created=True)

    def get(self, job_id: str) -> RunJob | None:
        with self._database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM run_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return self._row_to_job(row) if row is not None else None

    def get_active_for_run(
        self,
        run_id: str,
        *,
        job_type: RunJobType | None = None,
    ) -> RunJob | None:
        query = """
                SELECT * FROM run_jobs
                WHERE run_id = ?
                  AND status IN (?, ?)
                """
        parameters: list[object] = [
            run_id,
            RunJobStatus.QUEUED.value,
            RunJobStatus.RUNNING.value,
        ]
        if job_type is not None:
            query += " AND job_type = ?"
            parameters.append(job_type.value)
        query += " ORDER BY queued_at DESC LIMIT 1"
        with self._database.connection() as connection:
            row = connection.execute(query, tuple(parameters)).fetchone()
        return self._row_to_job(row) if row is not None else None

    def claim_job(self, job_id: str, *, worker_id: str, lease_seconds: int) -> RunJob | None:
        now = datetime.now(UTC)
        lease_expires_at = datetime.fromtimestamp(now.timestamp() + lease_seconds, UTC)
        with self._database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE run_jobs
                SET status = ?,
                    attempt_count = attempt_count + 1,
                    lease_owner = ?,
                    lease_expires_at = ?,
                    last_heartbeat_at = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE job_id = ?
                  AND (
                    status = ?
                    OR (status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at < ?)
                  )
                """,
                (
                    RunJobStatus.RUNNING.value,
                    worker_id,
                    lease_expires_at.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    job_id,
                    RunJobStatus.QUEUED.value,
                    RunJobStatus.RUNNING.value,
                    now.isoformat(),
                ),
            )
        if cursor.rowcount == 0:
            return None
        return self.get(job_id)

    def heartbeat_job(self, job_id: str, *, worker_id: str, lease_seconds: int) -> RunJob | None:
        now = datetime.now(UTC)
        next_expiry = datetime.fromtimestamp(now.timestamp() + lease_seconds, UTC)
        with self._database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE run_jobs
                SET lease_expires_at = ?,
                    last_heartbeat_at = ?,
                    updated_at = ?
                WHERE job_id = ?
                  AND status = ?
                  AND lease_owner = ?
                """,
                (
                    next_expiry.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    job_id,
                    RunJobStatus.RUNNING.value,
                    worker_id,
                ),
            )
        if cursor.rowcount == 0:
            return None
        return self.get(job_id)

    def complete_job(self, job_id: str) -> RunJob | None:
        existing = self.get(job_id)
        if existing is None:
            return None
        if existing.status == RunJobStatus.COMPLETED:
            return existing
        now = datetime.now(UTC)
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE run_jobs
                SET status = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_heartbeat_at = ?,
                    finished_at = ?,
                    updated_at = ?,
                    error_text = NULL
                WHERE job_id = ?
                """,
                (
                    RunJobStatus.COMPLETED.value,
                    now.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                    job_id,
                ),
            )
        return self.get(job_id)

    def fail_job(self, job_id: str, error_text: str) -> RunJob | None:
        existing = self.get(job_id)
        if existing is None:
            return None
        if existing.status == RunJobStatus.FAILED:
            return existing
        now = datetime.now(UTC)
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE run_jobs
                SET status = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_heartbeat_at = ?,
                    error_text = ?,
                    finished_at = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (
                    RunJobStatus.FAILED.value,
                    now.isoformat(),
                    error_text,
                    now.isoformat(),
                    now.isoformat(),
                    job_id,
                ),
            )
        return self.get(job_id)

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> RunJob:
        return RunJob(
            job_id=row["job_id"],
            run_id=row["run_id"],
            job_type=RunJobType(row["job_type"]),
            status=RunJobStatus(row["status"]),
            attempt_count=row["attempt_count"],
            lease_owner=row["lease_owner"],
            lease_expires_at=_to_datetime(row["lease_expires_at"])
            if row["lease_expires_at"] is not None
            else None,
            last_heartbeat_at=_to_datetime(row["last_heartbeat_at"])
            if row["last_heartbeat_at"] is not None
            else None,
            error_text=row["error_text"],
            queued_at=_to_datetime(row["queued_at"]),
            started_at=_to_datetime(row["started_at"]) if row["started_at"] is not None else None,
            finished_at=_to_datetime(row["finished_at"])
            if row["finished_at"] is not None
            else None,
            updated_at=_to_datetime(row["updated_at"]),
        )


class SQLiteLearningRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(
        self,
        chat_id: int,
        workflow: str,
        prompt: str,
        result_excerpt: str,
        learning_lessons: str | None = None,
    ) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO learning_entries (chat_id, workflow, prompt, result_excerpt, learning_lessons, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    workflow,
                    prompt,
                    result_excerpt,
                    learning_lessons,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def list_recent(self, chat_id: int, limit: int = 3) -> list[dict[str, str]]:
        with self._database.connection() as connection:
            rows = connection.execute(
                """
                SELECT workflow, prompt, result_excerpt, learning_lessons
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
                "learning_lessons": row["learning_lessons"],
            }
            for row in rows
        ]

    def list_grouped_by_workflow(
        self,
        chat_id: int,
        current_workflow: str,
        same_workflow_limit: int = 3,
        other_workflow_limit: int = 1,
    ) -> list[dict[str, str]]:
        """Return learning entries grouped by workflow.

        - same_workflow_limit: how many entries from current workflow.
        - other_workflow_limit: how many entries from each *other* workflow.
        """
        with self._database.connection() as connection:
            rows = connection.execute(
                """SELECT workflow, prompt, result_excerpt, learning_lessons
                   FROM learning_entries
                   WHERE chat_id = ?
                   ORDER BY workflow, created_at DESC""",
                (chat_id,),
            ).fetchall()

        groups: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            wf = row["workflow"]
            if wf not in groups:
                groups[wf] = []
            groups[wf].append(
                {
                    "workflow": wf,
                    "prompt": row["prompt"],
                    "result_excerpt": row["result_excerpt"],
                    "learning_lessons": row["learning_lessons"],
                }
            )

        current_entries = groups.pop(current_workflow, [])[:same_workflow_limit]

        other_entries: list[dict[str, str]] = []
        for wf, entries in groups.items():
            other_entries.extend(entries[:other_workflow_limit])

        return current_entries + other_entries


class SQLiteRepoKnowledgeRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(self, chat_id: int, repo_name: str, topic: str, summary: str) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO repo_knowledge (chat_id, repo_name, topic, summary, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, repo_name, topic, summary, datetime.now(UTC).isoformat()),
            )

    def list_recent(
        self, chat_id: int, repo_name: str | None = None, limit: int = 5
    ) -> list[dict[str, str]]:
        with self._database.connection() as connection:
            if repo_name is not None:
                rows = connection.execute(
                    """
                    SELECT repo_name, topic, summary
                    FROM repo_knowledge
                    WHERE chat_id = ? AND repo_name = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (chat_id, repo_name, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT repo_name, topic, summary
                    FROM repo_knowledge
                    WHERE chat_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (chat_id, limit),
                ).fetchall()
        return [
            {"repo_name": row["repo_name"], "topic": row["topic"], "summary": row["summary"]}
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


__all__ = [
    "SQLiteRunRepository",
    "SQLiteConversationRepository",
    "SQLiteRunJobRepository",
    "SQLiteLearningRepository",
    "SQLiteRepoKnowledgeRepository",
    "SQLiteToolEventRepository",
]
