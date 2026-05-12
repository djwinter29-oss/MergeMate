"""Tests for domain entities — AgentRun state machine, RunJob fields."""

from datetime import UTC, datetime, timedelta

import pytest

from mergemate.domain.shared import (
    RunJobStatus,
    RunJobType,
    RunStage,
    RunStatus,
)
from mergemate.domain.runs.entities import AgentRun, RunJob


# ── AgentRun construction ────────────────────────────────────────────────


def test_agent_run_fields_match_constructor() -> None:
    """Verify AgentRun stores all supplied constructor fields."""
    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-abc",
        chat_id=42,
        user_id=1001,
        agent_name="tester",
        workflow="generate_code",
        status=RunStatus.QUEUED,
        current_stage=RunStage.QUEUED_FOR_EXECUTION,
        prompt="write a test",
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

    assert run.run_id == "run-abc"
    assert run.chat_id == 42
    assert run.user_id == 1001
    assert run.agent_name == "tester"
    assert run.workflow == "generate_code"
    assert run.status == RunStatus.QUEUED
    assert run.current_stage == RunStage.QUEUED_FOR_EXECUTION
    assert run.prompt == "write a test"
    assert run.estimate_seconds == 30
    assert run.review_iterations == 0
    assert run.approved is False
    assert run.created_at is now
    assert run.updated_at is now

    # Nullable text fields
    assert run.plan_text is None
    assert run.design_text is None
    assert run.test_text is None
    assert run.review_text is None
    assert run.result_text is None
    assert run.error_text is None


def test_agent_run_with_all_text_fields_populated() -> None:
    """AgentRun with all optional text fields filled."""
    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-full",
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.COMPLETED,
        current_stage=RunStage.COMPLETED,
        prompt="build a feature",
        estimate_seconds=120,
        plan_text="plan content",
        design_text="design content",
        test_text="test content",
        review_text="review content",
        review_iterations=2,
        approved=True,
        result_text="result content",
        error_text=None,
        created_at=now,
        updated_at=now,
    )

    assert run.plan_text == "plan content"
    assert run.design_text == "design content"
    assert run.test_text == "test content"
    assert run.review_text == "review content"
    assert run.result_text == "result content"
    assert run.error_text is None
    assert run.review_iterations == 2
    assert run.approved is True
    assert run.status == RunStatus.COMPLETED


def test_agent_run_current_stage_accepts_string() -> None:
    """current_stage field accepts arbitrary strings, not just RunStage values."""
    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-str-stage",
        chat_id=1,
        user_id=1,
        agent_name="bot",
        workflow="custom",
        status=RunStatus.RUNNING,
        current_stage="tool:git_commit",
        prompt="commit code",
        estimate_seconds=10,
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

    assert run.current_stage == "tool:git_commit"


def test_agent_run_is_slots_class() -> None:
    """AgentRun is a slots dataclass — no __dict__."""
    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-slots",
        chat_id=1,
        user_id=1,
        agent_name="bot",
        workflow="test",
        status=RunStatus.QUEUED,
        current_stage=RunStage.QUEUED_FOR_EXECUTION,
        prompt="test",
        estimate_seconds=0,
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

    with pytest.raises(AttributeError):
        _ = run.__dict__  # type: ignore[attr-defined]


# ── AgentRun status transitions (state-machine validation) ────────────────
# Note: AgentRun itself is a data dataclass with no methods for validation.
# The state machine logic lives in the application layer.  These tests
# verify that the dataclass *allows* all expected transitions (i.e. any
# status can be assigned to any instance) and document the intended
# lifecycle.  Application-layer validation should reject illegal transitions.


@pytest.mark.parametrize(
    ("new_status", "new_stage"),
    [
        # pending → running → waiting_for_approval → running → completed
        # NOTE: RunStatus does not have PENDING or WAITING_FOR_APPROVAL.
        # The documented pipeline uses the actual enum members.
        pytest.param(RunStatus.QUEUED, RunStage.QUEUED_FOR_EXECUTION, id="queued"),
        pytest.param(RunStatus.RUNNING, RunStage.RETRIEVE_CONTEXT, id="running"),
        pytest.param(RunStatus.RUNNING, RunStage.DESIGN, id="design"),
        pytest.param(RunStatus.RUNNING, RunStage.IMPLEMENTATION, id="implementation"),
        pytest.param(RunStatus.RUNNING, RunStage.TESTING, id="testing"),
        pytest.param(RunStatus.RUNNING, RunStage.REVIEW, id="review"),
        pytest.param(RunStatus.RUNNING, RunStage.INTERNAL_REPLANNING, id="replanning"),
        pytest.param(RunStatus.COMPLETED, RunStage.COMPLETED, id="completed"),
        pytest.param(RunStatus.FAILED, RunStage.COMPLETED, id="failed"),
        pytest.param(RunStatus.CANCELLED, RunStage.COMPLETED, id="cancelled"),
    ],
)
def test_agent_run_status_transitions(new_status: RunStatus, new_stage: RunStage) -> None:
    """AgentRun allows all expected status+stage combinations."""
    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-trans",
        chat_id=1,
        user_id=1,
        agent_name="bot",
        workflow="generate_code",
        status=RunStatus.AWAITING_CONFIRMATION,
        current_stage=RunStage.AWAITING_USER_CONFIRMATION,
        prompt="test",
        estimate_seconds=0,
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
    run.status = new_status
    run.current_stage = new_stage

    assert run.status == new_status
    assert run.current_stage == new_stage


def test_agent_run_mutable_after_creation() -> None:
    """All fields on AgentRun are mutable (no frozen=True)."""
    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-mut",
        chat_id=1,
        user_id=1,
        agent_name="bot",
        workflow="test",
        status=RunStatus.QUEUED,
        current_stage=RunStage.QUEUED_FOR_EXECUTION,
        prompt="test",
        estimate_seconds=0,
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

    run.status = RunStatus.RUNNING
    run.current_stage = RunStage.EXECUTION
    run.approved = True
    run.plan_text = "updated plan"
    run.design_text = "updated design"
    run.review_iterations = 3
    run.result_text = "done"
    run.error_text = "no error"

    assert run.status == RunStatus.RUNNING
    assert run.current_stage == RunStage.EXECUTION
    assert run.approved is True
    assert run.plan_text == "updated plan"
    assert run.design_text == "updated design"
    assert run.review_iterations == 3
    assert run.result_text == "done"
    assert run.error_text == "no error"


# ── RunJob construction & fields ─────────────────────────────────────────


def test_run_job_construction() -> None:
    """RunJob stores all supplied fields correctly."""
    now = datetime.now(UTC)
    run = RunJob(
        job_id="job-1",
        run_id="run-1",
        job_type=RunJobType.PLAN_RUN,
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

    assert run.job_id == "job-1"
    assert run.run_id == "run-1"
    assert run.job_type == RunJobType.PLAN_RUN
    assert run.status == RunJobStatus.QUEUED
    assert run.attempt_count == 0
    assert run.lease_owner is None
    assert run.lease_expires_at is None
    assert run.last_heartbeat_at is None
    assert run.error_text is None
    assert run.queued_at is now
    assert run.started_at is None
    assert run.finished_at is None
    assert run.updated_at is now


def test_run_job_with_lease_fields() -> None:
    """RunJob with lease ownership and timing fields populated."""
    now = datetime.now(UTC)
    later = now + timedelta(seconds=30)
    started = now + timedelta(seconds=1)
    finished = now + timedelta(seconds=10)

    run = RunJob(
        job_id="job-2",
        run_id="run-2",
        job_type=RunJobType.EXECUTE_RUN,
        status=RunJobStatus.RUNNING,
        attempt_count=1,
        lease_owner="worker-42",
        lease_expires_at=later,
        last_heartbeat_at=now,
        error_text=None,
        queued_at=now,
        started_at=started,
        finished_at=finished,
        updated_at=later,
    )

    assert run.lease_owner == "worker-42"
    assert run.lease_expires_at == later
    assert run.last_heartbeat_at == now
    assert run.started_at == started
    assert run.finished_at == finished
    assert run.updated_at == later


def test_run_job_with_error() -> None:
    """RunJob stores error text when execution fails."""
    now = datetime.now(UTC)

    run = RunJob(
        job_id="job-err",
        run_id="run-err",
        job_type=RunJobType.EXECUTE_RUN,
        status=RunJobStatus.FAILED,
        attempt_count=3,
        lease_owner=None,
        lease_expires_at=None,
        last_heartbeat_at=now,
        error_text="timeout after 300s",
        queued_at=now,
        started_at=now,
        finished_at=now + timedelta(seconds=300),
        updated_at=now + timedelta(seconds=300),
    )

    assert run.status == RunJobStatus.FAILED
    assert run.error_text == "timeout after 300s"
    assert run.attempt_count == 3


def test_run_job_is_slots_class() -> None:
    """RunJob is a slots dataclass — no __dict__."""
    now = datetime.now(UTC)
    run = RunJob(
        job_id="j",
        run_id="r",
        job_type=RunJobType.PLAN_RUN,
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

    with pytest.raises(AttributeError):
        _ = run.__dict__  # type: ignore[attr-defined]


def test_run_job_mutable_fields() -> None:
    """RunJob fields are mutable (no frozen=True)."""
    now = datetime.now(UTC)

    run = RunJob(
        job_id="j-mut",
        run_id="r-mut",
        job_type=RunJobType.PLAN_RUN,
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

    later = now + timedelta(seconds=60)

    run.status = RunJobStatus.RUNNING
    run.attempt_count = 1
    run.lease_owner = "worker-99"
    run.lease_expires_at = later
    run.last_heartbeat_at = now
    run.started_at = now
    run.error_text = "retrying"

    assert run.status == RunJobStatus.RUNNING
    assert run.attempt_count == 1
    assert run.lease_owner == "worker-99"
    assert run.error_text == "retrying"


# ── RunJobType completeness ──────────────────────────────────────────────


def test_run_job_type_values() -> None:
    """RunJobType covers plan and execute job types."""
    assert RunJobType.PLAN_RUN.value == "plan_run"
    assert RunJobType.EXECUTE_RUN.value == "execute_run"
    assert set(RunJobType) == {RunJobType.PLAN_RUN, RunJobType.EXECUTE_RUN}


# ── RunJobStatus completeness ────────────────────────────────────────────


def test_run_job_status_values() -> None:
    """RunJobStatus covers queued → running → completed/failed."""
    assert RunJobStatus.QUEUED.value == "queued"
    assert RunJobStatus.RUNNING.value == "running"
    assert RunJobStatus.COMPLETED.value == "completed"
    assert RunJobStatus.FAILED.value == "failed"
    assert set(RunJobStatus) == {
        RunJobStatus.QUEUED,
        RunJobStatus.RUNNING,
        RunJobStatus.COMPLETED,
        RunJobStatus.FAILED,
    }
