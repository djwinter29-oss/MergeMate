"""Polling-based Telegram progress notifications for in-flight runs."""

import asyncio

from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram.presenter import format_progress_update


def _tool_event_signature(run) -> tuple[str, str, str, str] | None:
    latest_tool_event = getattr(run, "latest_tool_event", None)
    if latest_tool_event is None:
        return None
    return (
        latest_tool_event["tool_name"],
        latest_tool_event["action"],
        latest_tool_event["status"],
        latest_tool_event["detail"],
    )


async def watch_run_progress(application, runtime, chat_id: int, run_id: str) -> None:
    interval_seconds = max(runtime.settings.runtime.status_update_interval_seconds, 1)
    last_snapshot: tuple[str, str, int, tuple[str, str, str, str] | None] | None = None
    terminal_statuses = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}

    while True:
        await asyncio.sleep(interval_seconds)
        run = runtime.get_run_status.execute(run_id)
        if run is None:
            return
        if run.status in terminal_statuses:
            return

        snapshot = (run.status.value, run.current_stage, run.review_iterations, _tool_event_signature(run))
        if snapshot == last_snapshot:
            continue

        last_snapshot = snapshot
        await application.bot.send_message(chat_id=chat_id, text=format_progress_update(run))