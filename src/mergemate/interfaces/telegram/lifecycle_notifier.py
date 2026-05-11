# mypy: allow-untyped-defs
"""Telegram delivery adapter for background run lifecycle events."""

import asyncio
import logging
from typing import Protocol, runtime_checkable

from mergemate.domain.shared import RunStatus
from mergemate.interfaces.telegram import message_utils
from mergemate.interfaces.telegram.presenter import (
    format_auto_execution_started,
    format_plan_for_confirmation,
)
from mergemate.interfaces.telegram.progress_notifier import notify_terminal_update, start_progress_watcher

__all__ = ["LifecycleNotifier", "TelegramRunLifecycleNotifier"]


class _BotLike(Protocol):
    async def send_message(self, chat_id: int, text: str) -> None: ...


class _ApplicationLike(Protocol):
    bot: _BotLike
    bot_data: dict[str, object]

    def create_task(self, coro) -> asyncio.Task[None]: ...


class _RunLike(Protocol):
    chat_id: int
    run_id: str
    plan_text: str | None
    estimate_seconds: int
    status: RunStatus | str
    current_stage: str
    review_iterations: int
    latest_tool_event: dict[str, str] | None
    result_text: str | None
    error_text: str | None


@runtime_checkable
class LifecycleNotifier(Protocol):
    """Protocol for run lifecycle notification adapters."""

    def bind_application(self, application: _ApplicationLike) -> None: ...

    def bind_runtime(self, runtime) -> None: ...

    async def notify_plan_ready(self, run: _RunLike) -> bool: ...

    async def notify_auto_execution_started(self, run: _RunLike) -> bool: ...

    async def notify_terminal(self, run: _RunLike) -> bool: ...


logger = logging.getLogger(__name__)


class TelegramRunLifecycleNotifier:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._application: _ApplicationLike | None = None
        self._runtime = None

    def bind_application(self, application: _ApplicationLike) -> None:
        self._application = application

    def bind_runtime(self, runtime) -> None:
        self._runtime = runtime

    async def notify_plan_ready(self, run: _RunLike) -> bool:
        application = self._application
        if application is None:
            return False
        try:
            await message_utils.send_text_chunks(
                lambda text: application.bot.send_message(chat_id=run.chat_id, text=text),
                format_plan_for_confirmation(
                    run.run_id,
                    self._settings.resolve_agent_name_for_workflow("planning"),
                    run.plan_text or "",
                    run.estimate_seconds,
                ),
            )
        except Exception as exc:
            logger.exception("Run %s plan delivery failed: %s", run.run_id, exc)
            return False
        return True

    async def notify_auto_execution_started(self, run: _RunLike) -> bool:
        application = self._application
        runtime = self._runtime
        if application is None or runtime is None:
            return False
        try:
            await message_utils.send_text_chunks(
                lambda text: application.bot.send_message(chat_id=run.chat_id, text=text),
                format_auto_execution_started(
                    run.run_id,
                    run.plan_text or "",
                    run.estimate_seconds,
                ),
            )
        except Exception as exc:
            logger.exception("Run %s auto-start delivery failed: %s", run.run_id, exc)
            return False

        try:
            start_progress_watcher(application, runtime, run.chat_id, run.run_id)
        except Exception as exc:
            logger.exception("Run %s progress watcher start failed: %s", run.run_id, exc)

        return True

    async def notify_terminal(self, run: _RunLike) -> bool:
        application = self._application
        if application is None:
            return False
        if run.status not in RunStatus.terminal_statuses():
            return False
        return await notify_terminal_update(application, run.chat_id, run)
