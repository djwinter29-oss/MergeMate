"""Polling-based Telegram progress notifications for in-flight runs."""

import asyncio

from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram.presenter import format_progress_update

PROGRESS_WATCHERS_KEY = "progress_watchers"


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


def _watcher_registry(application) -> dict[str, asyncio.Task[None]]:
    return application.bot_data.setdefault(PROGRESS_WATCHERS_KEY, {})


def start_progress_watcher(application, runtime, chat_id: int, run_id: str) -> None:
    registry = _watcher_registry(application)
    existing_task = registry.get(run_id)
    if existing_task is not None and not existing_task.done():
        return

    task = application.create_task(watch_run_progress(application, runtime, chat_id, run_id))
    registry[run_id] = task

    def _cleanup(completed_task: asyncio.Task[None]) -> None:
        if registry.get(run_id) is completed_task:
            registry.pop(run_id, None)

    task.add_done_callback(_cleanup)


async def stop_progress_watchers(application) -> None:
    registry = application.bot_data.get(PROGRESS_WATCHERS_KEY, {})
    tasks = [task for task in registry.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    registry.clear()


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