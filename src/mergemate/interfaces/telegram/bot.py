"""Telegram runtime adapter for polling and webhook modes."""

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters

from mergemate.interfaces.telegram.health import WebhookHealthServer, WebhookReadinessState
from mergemate.interfaces.telegram.handlers import (
    approve_command,
    cancel_command,
    handle_prompt,
    start_command,
    status_command,
    tools_command,
)
from mergemate.interfaces.telegram.progress_notifier import stop_progress_watchers


async def stop_runtime_tasks(application: Application) -> None:
    readiness_state = application.bot_data.get("webhook_readiness_state")
    if readiness_state is not None:
        readiness_state.mark_stopping()
    runtime = application.bot_data.get("runtime")
    worker = getattr(runtime, "worker", None)
    if worker is not None:
        await worker.stop()
    await stop_progress_watchers(application)


async def mark_runtime_ready(application: Application) -> None:
    readiness_state = application.bot_data.get("webhook_readiness_state")
    if readiness_state is not None:
        readiness_state.mark_ready()


class TelegramBotRuntime:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def build_application(self, *, readiness_state: WebhookReadinessState | None = None) -> Application:
        builder = ApplicationBuilder().token(self._runtime.settings.resolve_telegram_token())
        if readiness_state is not None:
            builder = builder.post_init(mark_runtime_ready)
        builder = builder.post_stop(stop_runtime_tasks)
        builder = builder.post_shutdown(stop_runtime_tasks)
        application = builder.build()
        application.bot_data["runtime"] = self._runtime
        application.bot_data.setdefault("progress_watchers", {})
        if readiness_state is not None:
            application.bot_data["webhook_readiness_state"] = readiness_state
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("status", status_command))
        application.add_handler(CommandHandler("tools", tools_command))
        application.add_handler(CommandHandler("approve", approve_command))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
        return application

    def run_polling(self) -> None:
        application = self.build_application()
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    def run_webhook(self) -> None:
        readiness_state = WebhookReadinessState()
        application = self.build_application(readiness_state=readiness_state)
        telegram_settings = self._runtime.settings.telegram
        health_server = None
        if telegram_settings.webhook_healthcheck_enabled:
            health_server = WebhookHealthServer(
                listen_host=telegram_settings.webhook_healthcheck_listen_host,
                listen_port=telegram_settings.webhook_healthcheck_listen_port,
                path=telegram_settings.webhook_healthcheck_path,
                state=readiness_state,
            )
            health_server.start()

        try:
            application.run_webhook(
                listen=telegram_settings.webhook_listen_host,
                port=telegram_settings.webhook_listen_port,
                url_path=telegram_settings.webhook_path.lstrip("/"),
                webhook_url=self._runtime.settings.resolve_telegram_webhook_url(),
                secret_token=self._runtime.settings.resolve_telegram_webhook_secret_token(),
                allowed_updates=Update.ALL_TYPES,
            )
        finally:
            readiness_state.mark_stopping()
            if health_server is not None:
                health_server.stop()

    def run(self) -> None:
        if self._runtime.settings.telegram.mode == "webhook":
            self.run_webhook()
            return
        self.run_polling()