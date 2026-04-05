"""Polling-based Telegram progress notifications for in-flight runs."""

import asyncio
import logging

from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram.message_utils import send_text_chunks
from mergemate.interfaces.telegram.presenter import format_cancelled, format_completion, format_failure, format_progress_update

PROGRESS_WATCHERS_KEY = "progress_watchers"
TERMINAL_DELIVERIES_KEY = "terminal_deliveries"
logger = logging.getLogger(__name__)


def _format_terminal_update(run) -> str:
    if run.status == RunStatus.COMPLETED:
        return format_completion(run.run_id, getattr(run, "result_text", None) or "")
    if run.status == RunStatus.CANCELLED:
        return format_cancelled(run.run_id)
    return format_failure(run.run_id, getattr(run, "error_text", None))


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


def _terminal_delivery_registry(application) -> set[str]:
    return application.bot_data.setdefault(TERMINAL_DELIVERIES_KEY, set())


async def notify_terminal_update(application, chat_id: int, run) -> bool:
    try:
        await send_text_chunks(
            lambda chunk: application.bot.send_message(chat_id=chat_id, text=chunk),
            _format_terminal_update(run),
        )
    except Exception:
        logger.exception("Run %s progress update delivery failed", run.run_id)
        return False
    _terminal_delivery_registry(application).add(run.run_id)
    return True


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
        _terminal_delivery_registry(application).discard(run_id)

    task.add_done_callback(_cleanup)


async def stop_progress_watchers(application) -> None:
    registry = application.bot_data.get(PROGRESS_WATCHERS_KEY, {})
    tasks = [task for task in registry.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    registry.clear()
    application.bot_data.get(TERMINAL_DELIVERIES_KEY, set()).clear()


async def watch_run_progress(application, runtime, chat_id: int, run_id: str) -> None:
    interval_seconds = max(runtime.settings.runtime.status_update_interval_seconds, 1)
    last_snapshot: tuple[str, str, int, tuple[str, str, str, str] | None] | None = None
    terminal_statuses = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
    terminal_deliveries = _terminal_delivery_registry(application)

    while True:
        await asyncio.sleep(interval_seconds)
        run = runtime.get_run_status.execute(run_id)
        if run is None:
            return
        if run.status in terminal_statuses and run.run_id in terminal_deliveries:
            return

        snapshot = (run.status.value, run.current_stage, run.review_iterations, _tool_event_signature(run))
        if snapshot == last_snapshot:
            continue

        try:
            if run.status in terminal_statuses:
                delivered = await notify_terminal_update(application, chat_id, run)
                if not delivered:
                    continue
            else:
                await send_text_chunks(
                    lambda chunk: application.bot.send_message(chat_id=chat_id, text=chunk),
                    format_progress_update(run),
                )
        except Exception:
            logger.exception("Run %s progress update delivery failed", run_id)
            continue

        last_snapshot = snapshot
        if run.status in terminal_statuses:
            return