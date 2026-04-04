"""Telegram runtime adapter for polling mode."""

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters

from mergemate.interfaces.telegram.handlers import (
    approve_command,
    cancel_command,
    handle_prompt,
    start_command,
    status_command,
    tools_command,
)
from mergemate.interfaces.telegram.progress_notifier import stop_progress_watchers


class TelegramBotRuntime:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def build_application(self) -> Application:
        if self._runtime.settings.telegram.mode != "polling":
            raise ValueError("Only polling mode is implemented in the MVP draft")

        builder = ApplicationBuilder().token(self._runtime.settings.resolve_telegram_token())
        builder = builder.post_stop(stop_progress_watchers)
        builder = builder.post_shutdown(stop_progress_watchers)
        application = builder.build()
        application.bot_data["runtime"] = self._runtime
        application.bot_data.setdefault("progress_watchers", {})
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