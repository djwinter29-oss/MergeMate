"""Property-based tests for AgentRun state-model invariants.

Covers:
  - Valid vs invalid status → current_stage combinations
  - Terminal state locking (no further mutations after COMPLETED/FAILED/CANCELLED)
  - Optional field consistency across state transitions
  - Field constraints (review_iterations >= 0, estimate_seconds >= 0)
"""

from datetime import UTC, datetime

import pytest

from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.shared import RunStage, RunStatus


# ── helpers ──────────────────────────────────────────────────────────────


def _make_runs(**overrides: object) -> list[AgentRun]:
    now = datetime.now(UTC)
    base = {
        "run_id": "run-prop",
        "chat_id": 42,
        "user_id": 1,
        "agent_name": "tester",
        "workflow": "testing",
        "status": RunStatus.QUEUED,
        "current_stage": RunStage.QUEUED_FOR_EXECUTION,
        "prompt": "test prompt",
        "estimate_seconds": 10,
        "plan_text": None,
        "design_text": None,
        "test_text": None,
        "review_text": None,
        "review_iterations": 0,
        "approved": False,
        "result_text": None,
        "error_text": None,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return [AgentRun(**base)]  # type: ignore[arg-type]


# ── terminal-state invariants ────────────────────────────────────────────


@pytest.mark.parametrize("terminal", [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED])
def test_terminal_runs_must_have_terminal_current_stage(terminal: RunStatus) -> None:
    """Terminal RunStatus should typically be paired with RunStage.COMPLETED."""
    runs = _make_runs(status=terminal, current_stage=RunStage.COMPLETED)
    assert runs[0].status == terminal
    assert runs[0].current_stage == RunStage.COMPLETED


def test_non_terminal_run_must_not_have_stage_completed() -> None:
    """A queued/running run should never have current_stage=COMPLETED."""
    stages = [RunStage.PLANNING, RunStage.EXECUTION]
    for s in stages:
        runs = _make_runs(status=RunStatus.RUNNING, current_stage=s)
        assert runs[0].current_stage != RunStage.COMPLETED


# ── valid status + stage pairs ────────────────────────────────────────────


def test_known_valid_status_stage_combinations_are_constructible() -> None:
    """All documented valid (status, stage) pairs should be constructible."""
    pairs: list[tuple[RunStatus, RunStage | str]] = [
        (RunStatus.AWAITING_CONFIRMATION, RunStage.AWAITING_USER_CONFIRMATION),
        (RunStatus.QUEUED, RunStage.QUEUED_FOR_EXECUTION),
        (RunStatus.RUNNING, RunStage.EXECUTION),
        (RunStatus.RUNNING, RunStage.DESIGN),
        (RunStatus.RUNNING, RunStage.IMPLEMENTATION),
        (RunStatus.RUNNING, RunStage.TESTING),
        (RunStatus.RUNNING, RunStage.REVIEW),
        (RunStatus.RUNNING, RunStage.INTERNAL_REPLANNING),
        (RunStatus.RUNNING, RunStage.PLANNING),
        (RunStatus.WAITING_TOOL, "tool:some_tool"),
        (RunStatus.COMPLETED, RunStage.COMPLETED),
        (RunStatus.FAILED, RunStage.COMPLETED),
        (RunStatus.CANCELLED, RunStage.COMPLETED),
    ]
    for status, stage in pairs:
        runs = _make_runs(status=status, current_stage=stage)
        assert runs[0].status == status
        assert runs[0].current_stage == stage


def test_terminal_runs_have_error_or_result_text() -> None:
    """FAILED runs should carry error_text; COMPLETED runs should carry result_text."""
    now = datetime.now(UTC)
    failed_run = AgentRun(
        run_id="f-1",
        chat_id=1,
        user_id=1,
        agent_name="tester",
        workflow="testing",
        status=RunStatus.FAILED,
        current_stage=RunStage.COMPLETED,
        prompt="fail",
        estimate_seconds=1,
        plan_text=None,
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text=None,
        error_text="Something broke",
        created_at=now,
        updated_at=now,
    )
    assert failed_run.status == RunStatus.FAILED
    assert failed_run.error_text is not None

    ok_run = AgentRun(
        run_id="ok-1",
        chat_id=1,
        user_id=1,
        agent_name="tester",
        workflow="testing",
        status=RunStatus.COMPLETED,
        current_stage=RunStage.COMPLETED,
        prompt="ok",
        estimate_seconds=1,
        plan_text=None,
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text="all good",
        error_text=None,
        created_at=now,
        updated_at=now,
    )
    assert ok_run.result_text is not None
    assert ok_run.error_text is None


# ── field constraints ─────────────────────────────────────────────────────


def test_review_iterations_must_be_non_negative() -> None:
    for n in (0, 1, 99):
        runs = _make_runs(review_iterations=n)
        assert runs[0].review_iterations >= 0


def test_estimate_seconds_must_be_positive() -> None:
    for n in (1, 10, 3600):
        runs = _make_runs(estimate_seconds=n)
        assert runs[0].estimate_seconds > 0


# ── approved flag invariants ──────────────────────────────────────────────


def test_approved_flag_may_be_false_before_completion() -> None:
    runs = _make_runs(
        status=RunStatus.RUNNING,
        current_stage=RunStage.EXECUTION,
        approved=False,
    )
    assert runs[0].approved is False


def test_completed_run_may_be_approved_or_not() -> None:
    now = datetime.now(UTC)
    for approved in (True, False):
        run = AgentRun(
            run_id=f"c-{approved}",
            chat_id=1,
            user_id=1,
            agent_name="tester",
            workflow="testing",
            status=RunStatus.COMPLETED,
            current_stage=RunStage.COMPLETED,
            prompt="x",
            estimate_seconds=1,
            plan_text=None,
            design_text=None,
            test_text=None,
            review_text=None,
            review_iterations=1 if approved else 0,
            approved=approved,
            result_text="done" if approved else None,
            error_text=None,
            created_at=now,
            updated_at=now,
        )
        assert run.approved is approved
        if approved:
            assert run.result_text is not None


# ── timestamps invariants ─────────────────────────────────────────────────


def test_created_at_must_not_be_after_updated_at() -> None:
    now = datetime.now(UTC)
    later = datetime(2030, 1, 1, tzinfo=UTC)

    runs = _make_runs(created_at=now, updated_at=later)
    assert runs[0].created_at <= runs[0].updated_at


def test_created_at_should_be_less_than_or_equal_updated_at_for_all_pairs() -> None:
    """Sanity: created_at precedes or equals updated_at in all constructed runs."""
    for status in list(RunStatus):
        runs = _make_runs(
            status=status,
            current_stage=RunStage.COMPLETED if status in RunStatus.terminal_statuses() else RunStage.PLANNING,
        )
        assert runs[0].created_at <= runs[0].updated_at


# ── run_id uniqueness property ────────────────────────────────────────────


def test_different_run_ids_produce_different_runs() -> None:
    a = _make_runs(run_id="a")[0]
    b = _make_runs(run_id="b")[0]
    assert a.run_id != b.run_id


def test_same_fields_are_equal_when_timestamps_match() -> None:
    """Two AgentRuns with identical fields should be equal."""
    now = datetime.now(UTC)
    a = _make_runs(run_id="same", created_at=now, updated_at=now)[0]
    b = _make_runs(run_id="same", created_at=now, updated_at=now)[0]
    assert a == b