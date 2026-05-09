"""Tests for sqlite.py uncovered branch paths.

Covers:
1.  ensure_queued_job IntegrityError path when active job exists [line 475]
2.  claim_job returns None when no matching row [line 545]
3.  heartbeat_job returns None when rowcount == 0 [lines 571-572]
4.  heartbeat_job succeeds [line 573]
5.  complete_job returns None when job not found [line 578]
6.  complete_job returns existing when already completed [line 580]
7.  fail_job returns None when job not found [line 608]
8.  fail_job returns existing when already failed [line 610]
"""
from datetime import UTC, datetime

import pytest

from mergemate.domain.runs.entities import RunJob
from mergemate.domain.shared import RunJobStatus, RunJobType, RunStatus
from mergemate.infrastructure.persistence.sqlite import (
    SQLiteDatabase,
    SQLiteRunJobRepository,
    SQLiteRunRepository,
)


def _build_run_entity(run_id: str = "run-sqlite-1"):
    from mergemate.domain.runs.entities import AgentRun

    now = datetime.now(UTC)
    return AgentRun(
        run_id=run_id,
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.AWAITING_CONFIRMATION,
        current_stage="planning",
        prompt="test prompt",
        estimate_seconds=30,
        plan_text=None,
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )


class TestSQLiteRunJobUncovered:
    def test_ensure_queued_job_active_exists_no_error(self, tmp_path) -> None:
        """Line 475: IntegrityError caught when active job already exists.

        We trigger this by calling ensure_queued_job twice. The first call
        creates a job (INSERT succeeds), the second also tries INSERT but
        a UNIQUE constraint may fire. The code catches it and calls
        get_active_for_run.
        """
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        run_repo = SQLiteRunRepository(database)
        run_repo.create(_build_run_entity())
        repo = SQLiteRunJobRepository(database)

        # First call succeeds
        first = repo.ensure_queued_job("run-sqlite-1")
        assert first.created is True

        # Second call hits IntegrityError -> returns existing active job
        second = repo.ensure_queued_job("run-sqlite-1")
        assert second.created is False

    def test_claim_job_returns_none_when_not_found(self, tmp_path) -> None:
        """Line 545: claim_job returns None when rowcount == 0 (no matching QUEUED job)."""
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        run_repo = SQLiteRunRepository(database)
        run_repo.create(_build_run_entity())
        repo = SQLiteRunJobRepository(database)

        # Claiming a job that doesn't exist returns None
        result = repo.claim_job("nonexistent-job", worker_id="w1", lease_seconds=30)
        assert result is None

    def test_heartbeat_job_returns_none_when_not_found(self, tmp_path) -> None:
        """Lines 571-572: heartbeat_job returns None when no matching RUNNING job."""
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        run_repo = SQLiteRunRepository(database)
        run_repo.create(_build_run_entity())
        repo = SQLiteRunJobRepository(database)

        # Heartbeat on nonexistent job returns None
        result = repo.heartbeat_job("nonexistent", worker_id="w1", lease_seconds=30)
        assert result is None

    def test_heartbeat_job_succeeds_for_owned_job(self, tmp_path) -> None:
        """Line 573: heartbeat_job returns the updated job."""
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        run_repo = SQLiteRunRepository(database)
        run_repo.create(_build_run_entity())
        repo = SQLiteRunJobRepository(database)

        queued = repo.ensure_queued_job("run-sqlite-1")
        claimed = repo.claim_job(queued.job.job_id, worker_id="w1", lease_seconds=30)
        assert claimed is not None

        # Heartbeat the job — should succeed
        result = repo.heartbeat_job(claimed.job_id, worker_id="w1", lease_seconds=30)
        assert result is not None
        assert result.job_id == claimed.job_id
        assert result.status == RunJobStatus.RUNNING

    def test_complete_job_returns_none_when_not_found(self, tmp_path) -> None:
        """Line 578: complete_job returns None when job not found."""
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        repo = SQLiteRunJobRepository(database)

        result = repo.complete_job("nonexistent-job")
        assert result is None

    def test_complete_job_returns_existing_when_already_completed(self, tmp_path) -> None:
        """Line 580: complete_job returns existing job when already COMPLETED."""
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        run_repo = SQLiteRunRepository(database)
        run_repo.create(_build_run_entity())
        repo = SQLiteRunJobRepository(database)

        # Create and complete a job
        queued = repo.ensure_queued_job("run-sqlite-1")
        repo.claim_job(queued.job.job_id, worker_id="w1", lease_seconds=30)

        first_complete = repo.complete_job(queued.job.job_id)
        assert first_complete is not None
        assert first_complete.status == RunJobStatus.COMPLETED

        # Second complete returns existing without error
        second_complete = repo.complete_job(queued.job.job_id)
        assert second_complete is not None
        assert second_complete.status == RunJobStatus.COMPLETED

    def test_fail_job_returns_none_when_not_found(self, tmp_path) -> None:
        """Line 608: fail_job returns None when job not found."""
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        repo = SQLiteRunJobRepository(database)

        result = repo.fail_job("nonexistent-job", "error text")
        assert result is None

    def test_fail_job_returns_existing_when_already_failed(self, tmp_path) -> None:
        """Line 610: fail_job returns existing job when already FAILED."""
        database = SQLiteDatabase(tmp_path / "state.db")
        database.initialize()
        run_repo = SQLiteRunRepository(database)
        run_repo.create(_build_run_entity())
        repo = SQLiteRunJobRepository(database)

        # Create and fail a job
        queued = repo.ensure_queued_job("run-sqlite-1")

        first_fail = repo.fail_job(queued.job.job_id, "first error")
        assert first_fail is not None
        assert first_fail.status == RunJobStatus.FAILED

        # Second fail returns existing without overwriting
        second_fail = repo.fail_job(queued.job.job_id, "second error")
        assert second_fail is not None
        assert second_fail.status == RunJobStatus.FAILED
        assert second_fail.error_text == "first error"