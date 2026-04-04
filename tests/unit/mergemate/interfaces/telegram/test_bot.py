from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from mergemate.interfaces.telegram import bot as telegram_bot


class ApplicationStub:
    def __init__(self) -> None:
        self.bot_data = {}
        self.handlers = []
        self.run_polling_calls = []

    def add_handler(self, handler) -> None:
        self.handlers.append(handler)

    def run_polling(self, *, allowed_updates) -> None:
        self.run_polling_calls.append(allowed_updates)


class BuilderStub:
    def __init__(self) -> None:
        self.token_value = None
        self.application = ApplicationStub()
        self.post_shutdown_callback = None
        self.post_stop_callback = None

    def token(self, value: str):
        self.token_value = value
        return self

    def post_shutdown(self, callback):
        self.post_shutdown_callback = callback
        return self

    def post_stop(self, callback):
        self.post_stop_callback = callback
        return self

    def build(self):
        return self.application


class FilterStub:
    def __init__(self, name: str) -> None:
        self.name = name

    def __and__(self, other):
        return FilterStub(f"({self.name}&{other.name})")

    def __invert__(self):
        return FilterStub(f"~{self.name}")


@dataclass(slots=True)
class RuntimeStub:
    settings: object
    worker: object | None = None


def test_build_application_registers_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = BuilderStub()
    runtime = RuntimeStub(settings=SimpleNamespace(telegram=SimpleNamespace(mode="polling"), resolve_telegram_token=lambda: "token"), worker=SimpleNamespace())

    monkeypatch.setattr(telegram_bot, "ApplicationBuilder", lambda: builder)
    monkeypatch.setattr(telegram_bot, "CommandHandler", lambda name, fn: ("command", name, fn.__name__))
    monkeypatch.setattr(telegram_bot, "MessageHandler", lambda filt, fn: ("message", fn.__name__))
    monkeypatch.setattr(
        telegram_bot,
        "filters",
        SimpleNamespace(TEXT=FilterStub("text"), COMMAND=FilterStub("command")),
    )

    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)
    application = bot_runtime.build_application()

    assert application is builder.application
    assert builder.token_value == "token"
    assert builder.post_shutdown_callback is telegram_bot.stop_runtime_tasks
    assert builder.post_stop_callback is telegram_bot.stop_runtime_tasks
    assert application.bot_data["runtime"] is runtime
    assert application.bot_data["progress_watchers"] == {}
    assert application.handlers[0] == ("command", "start", "start_command")
    assert ("command", "tools", "tools_command") in application.handlers
    assert application.handlers[-1] == ("message", "handle_prompt")


def test_build_application_rejects_non_polling_mode() -> None:
    runtime = RuntimeStub(settings=SimpleNamespace(telegram=SimpleNamespace(mode="webhook")))

    with pytest.raises(ValueError, match="Only polling mode"):
        telegram_bot.TelegramBotRuntime(runtime).build_application()


def test_run_polling_uses_all_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    application = ApplicationStub()
    runtime = RuntimeStub(settings=SimpleNamespace())
    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)

    monkeypatch.setattr(bot_runtime, "build_application", lambda: application)
    monkeypatch.setattr(telegram_bot, "Update", SimpleNamespace(ALL_TYPES="all-types"))

    bot_runtime.run_polling()

    assert application.run_polling_calls == ["all-types"]


@pytest.mark.asyncio
async def test_stop_runtime_tasks_stops_watchers_and_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped = []

    async def fake_stop_progress_watchers(application) -> None:
        stopped.append("watchers")

    class WorkerStub:
        async def stop(self) -> None:
            stopped.append("worker")

    application = ApplicationStub()
    application.bot_data["runtime"] = RuntimeStub(settings=SimpleNamespace(), worker=WorkerStub())

    monkeypatch.setattr(telegram_bot, "stop_progress_watchers", fake_stop_progress_watchers)

    await telegram_bot.stop_runtime_tasks(application)

    assert stopped == ["worker", "watchers"]
