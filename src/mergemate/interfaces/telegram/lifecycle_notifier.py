"""Telegram delivery adapter for background run lifecycle events."""

import logging

from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram import message_utils
from mergemate.interfaces.telegram.presenter import (
    format_auto_execution_started,
    format_plan_for_confirmation,
)
from mergemate.interfaces.telegram.progress_notifier import notify_terminal_update, start_progress_watcher

logger = logging.getLogger(__name__)


class TelegramRunLifecycleNotifier:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._application = None
        self._runtime = None

    def bind_application(self, application) -> None:
        self._application = application

    def bind_runtime(self, runtime) -> None:
        self._runtime = runtime

    async def notify_plan_ready(self, run) -> bool:
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
        except Exception:
            logger.exception("Run %s plan delivery failed", run.run_id)
            return False
        return True

    async def notify_auto_execution_started(self, run) -> bool:
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
        except Exception:
            logger.exception("Run %s auto-start delivery failed", run.run_id)
            return False

        try:
            start_progress_watcher(application, runtime, run.chat_id, run.run_id)
        except Exception:
            logger.exception("Run %s progress watcher start failed", run.run_id)

        return True

    async def notify_terminal(self, run) -> bool:
        application = self._application
        if application is None:
            return False
        if run.status not in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return False
        return await notify_terminal_update(application, run.chat_id, run)