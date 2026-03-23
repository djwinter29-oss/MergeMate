from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

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
    format_tool_history,
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


def test_presenter_includes_recent_tool_activity_when_available() -> None:
    tool_events = [
        {
            "tool_name": "syntax_checker",
            "action": "check",
            "status": "ok",
            "detail": "done",
            "created_at": "2026-03-23T10:15:00+00:00",
        },
        {
            "tool_name": "git_repository",
            "action": "status",
            "status": "ok",
            "detail": "clean",
            "created_at": "2026-03-23T10:14:00+00:00",
        },
    ]
    base_run = RunStub()
    run = SimpleNamespace(
        run_id=base_run.run_id,
        status=base_run.status,
        current_stage=base_run.current_stage,
        review_iterations=base_run.review_iterations,
        approved=base_run.approved,
        estimate_seconds=base_run.estimate_seconds,
        created_at=base_run.created_at,
        tool_events=tool_events,
        latest_tool_event=tool_events[0],
    )

    detailed_status = format_detailed_status(run)
    progress_update = format_progress_update(run)

    assert "Recent tool activity:" in detailed_status
    assert "syntax_checker check [ok]: done" in detailed_status
    assert "Latest tool: syntax_checker check [ok] - done." in progress_update
    assert "Tool activity for run run-1:" in format_tool_history(run)
    assert "2026-03-23 10:15:00 UTC" in format_tool_history(run)


def test_presenter_formats_empty_tool_history() -> None:
    run = RunStub(run_id="run-2")

    assert format_tool_history(run) == "No tool activity recorded for run run-2."


def test_presenter_formats_tool_history_without_or_with_invalid_timestamp() -> None:
    base_run = RunStub()
    run_without_timestamp = SimpleNamespace(
        run_id=base_run.run_id,
        status=base_run.status,
        current_stage=base_run.current_stage,
        review_iterations=base_run.review_iterations,
        approved=base_run.approved,
        estimate_seconds=base_run.estimate_seconds,
        created_at=base_run.created_at,
        tool_events=[{"tool_name": "syntax_checker", "action": "check", "status": "ok", "detail": ""}],
        latest_tool_event=None,
    )
    run_with_invalid_timestamp = SimpleNamespace(
        run_id=base_run.run_id,
        status=base_run.status,
        current_stage=base_run.current_stage,
        review_iterations=base_run.review_iterations,
        approved=base_run.approved,
        estimate_seconds=base_run.estimate_seconds,
        created_at=base_run.created_at,
        tool_events=[
            {
                "tool_name": "git_repository",
                "action": "status",
                "status": "ok",
                "detail": "clean",
                "created_at": "not-a-timestamp",
            }
        ],
        latest_tool_event=None,
    )

    assert "syntax_checker check [ok]: (no detail)" in format_tool_history(run_without_timestamp)
    assert "not-a-timestamp git_repository status [ok]: clean" in format_tool_history(run_with_invalid_timestamp)