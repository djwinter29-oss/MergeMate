from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram.presenter import (
    format_acknowledgement,
    format_approval_not_needed,
    format_approval_started,
    format_auto_execution_started,
    format_cancelled,
    format_completion,
    format_detailed_status,
    format_failure,
    format_plan_for_confirmation,
    format_progress_update,
    format_status,
    format_welcome,
)


@dataclass(slots=True)
class RunStub:
    run_id: str = "run-1"
    status: RunStatus = RunStatus.RUNNING
    current_stage: str = "implementation"
    review_iterations: int = 1
    approved: bool = True
    estimate_seconds: int | None = 20
    created_at: datetime = datetime.now(UTC) - timedelta(seconds=5)


def test_presenter_formats_all_primary_messages() -> None:
    run = RunStub()

    assert "Request accepted" in format_acknowledgement("run-1", "coder", 30)
    assert "Estimated execution time after approval" in format_plan_for_confirmation("run-1", "planner", "plan", 30)
    assert format_status("run-1", "queued") == "Run run-1 is currently queued."
    assert "Estimated remaining time" in format_status("run-1", "queued", 12)
    assert "Run run-1 is running." in format_detailed_status(run)
    assert "Run run-1 completed." in format_completion("run-1", "done")
    assert "Unknown error" in format_failure("run-1", None)
    assert format_cancelled("run-1") == "Run run-1 was cancelled."
    assert "MergeMate is running" in format_welcome("coder")
    assert "approved" in format_approval_started("run-1")
    assert "already in status 'completed'" in format_approval_not_needed("run-1", "completed")
    assert "started automatically" in format_auto_execution_started("run-1", "plan", 20)
    assert "stage=implementation" in format_progress_update(run)


def test_presenter_hides_remaining_time_for_terminal_or_missing_estimate() -> None:
    terminal_run = RunStub(status=RunStatus.COMPLETED, estimate_seconds=20)
    no_estimate_run = RunStub(estimate_seconds=None)

    assert "Estimated remaining time" not in format_detailed_status(terminal_run)
    assert "Estimated remaining time" not in format_progress_update(terminal_run)
    assert "Estimated remaining time" not in format_progress_update(no_estimate_run)