"""Formatting helpers for Telegram replies."""

from datetime import UTC, datetime


def _remaining_seconds(run) -> int | None:
    if run.estimate_seconds is None:
        return None
    now = datetime.now(UTC)
    elapsed = int((now - run.created_at).total_seconds())
    return max(run.estimate_seconds - elapsed, 0)


def format_acknowledgement(run_id: str, agent: str, estimate_seconds: int) -> str:
    return (
        f"Request accepted. Run ID: {run_id}. Agent: {agent}. Status: queued. "
        f"Estimated time: {estimate_seconds}s."
    )


def format_plan_for_confirmation(run_id: str, agent: str, plan_text: str, estimate_seconds: int) -> str:
    return (
        f"Requirements captured for run {run_id}. Planning agent: {agent}. "
        f"Estimated execution time after approval: {estimate_seconds}s.\n\n"
        f"{plan_text}\n\n"
        "Reply with more requirements to revise the plan, or run /approve <run_id> to continue."
    )


def format_status(run_id: str, status: str, estimate_seconds: int | None = None) -> str:
    if estimate_seconds is None:
        return f"Run {run_id} is currently {status}."
    return f"Run {run_id} is currently {status}. Estimated remaining time: {estimate_seconds}s."


def format_detailed_status(run) -> str:
    remaining_seconds = _remaining_seconds(run)
    estimate_line = (
        f"\nEstimated remaining time: {remaining_seconds}s."
        if remaining_seconds is not None and run.status.value in {"queued", "running", "waiting_tool"}
        else ""
    )
    return (
        f"Run {run.run_id} is {run.status.value}.\n"
        f"Current stage: {run.current_stage}.\n"
        f"Review iterations: {run.review_iterations}.\n"
        f"Approved: {'yes' if run.approved else 'no'}."
        f"{estimate_line}"
    )


def format_completion(run_id: str, result_text: str) -> str:
    return f"Run {run_id} completed.\n\n{result_text}"


def format_failure(run_id: str, error_text: str | None) -> str:
    detail = error_text or "Unknown error"
    return f"Run {run_id} failed.\n\n{detail}"


def format_cancelled(run_id: str) -> str:
    return f"Run {run_id} was cancelled."


def format_welcome(default_agent: str) -> str:
    return (
        "MergeMate is running. Send a normal message to capture requirements and draft a plan. "
        f"The current default coding agent is {default_agent}. Use /status to inspect the latest run."
    )


def format_approval_started(run_id: str) -> str:
    return f"Run {run_id} approved. Retrieving context, designing, implementing, testing, and reviewing now."


def format_approval_not_needed(run_id: str, status: str) -> str:
    return f"Run {run_id} was not re-approved because it is already in status '{status}'."


def format_auto_execution_started(run_id: str, plan_text: str, estimate_seconds: int) -> str:
    return (
        f"Run {run_id} started automatically because confirmation is disabled. "
        f"Estimated completion time: {estimate_seconds}s.\n\n"
        f"{plan_text}"
    )


def format_progress_update(run) -> str:
    remaining_seconds = _remaining_seconds(run)
    estimate_line = (
        f" Estimated remaining time: {remaining_seconds}s."
        if remaining_seconds is not None and run.status.value in {"queued", "running", "waiting_tool"}
        else ""
    )
    return (
        f"Run {run.run_id} update: status={run.status.value}, stage={run.current_stage}, "
        f"review_iterations={run.review_iterations}.{estimate_line}"
    )