from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from mergemate.interfaces.telegram import bot as telegram_bot


class ApplicationStub:
    def __init__(self) -> None:
        self.bot_data = {}
        self.handlers = []
        self.run_polling_calls = []
        self.run_webhook_calls = []

    def add_handler(self, handler) -> None:
        self.handlers.append(handler)

    def run_polling(self, *, allowed_updates) -> None:
        self.run_polling_calls.append(allowed_updates)

    def run_webhook(self, **kwargs) -> None:
        self.run_webhook_calls.append(kwargs)


class BuilderStub:
    def __init__(self) -> None:
        self.token_value = None
        self.application = ApplicationStub()
        self.post_init_callback = None
        self.post_shutdown_callback = None
        self.post_stop_callback = None

    def token(self, value: str):
        self.token_value = value
        return self

    def post_init(self, callback):
        self.post_init_callback = callback
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
    lifecycle_notifier: object | None = None


def test_build_application_registers_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    builder = BuilderStub()
    runtime = RuntimeStub(
        settings=SimpleNamespace(telegram=SimpleNamespace(mode="polling"), resolve_telegram_token=lambda: "token"),
        worker=SimpleNamespace(),
        lifecycle_notifier=SimpleNamespace(bind_application=lambda application: None),
    )

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
    assert builder.post_init_callback is telegram_bot.start_runtime_tasks
    assert builder.post_shutdown_callback is telegram_bot.stop_runtime_tasks
    assert builder.post_stop_callback is telegram_bot.stop_runtime_tasks
    assert application.bot_data["runtime"] is runtime
    assert application.bot_data["progress_watchers"] == {}
    assert application.handlers[0] == ("command", "start", "start_command")
    assert ("command", "tools", "tools_command") in application.handlers
    assert application.handlers[-1] == ("message", "handle_prompt")


def test_run_polling_uses_all_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    application = ApplicationStub()
    runtime = RuntimeStub(settings=SimpleNamespace())
    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)

    monkeypatch.setattr(bot_runtime, "build_application", lambda: application)
    monkeypatch.setattr(telegram_bot, "Update", SimpleNamespace(ALL_TYPES="all-types"))

    bot_runtime.run_polling()

    assert application.run_polling_calls == ["all-types"]


def test_run_webhook_uses_webhook_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    application = ApplicationStub()
    created_health_servers = []

    class HealthServerStub:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.started = False
            self.stopped = False
            created_health_servers.append(self)

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.stopped = True

    class ReadinessStateStub:
        def __init__(self) -> None:
            self.statuses = []

        def mark_ready(self) -> None:
            self.statuses.append("ready")

        def mark_stopping(self) -> None:
            self.statuses.append("stopping")

    runtime = RuntimeStub(
        settings=SimpleNamespace(
            telegram=SimpleNamespace(
                webhook_listen_host="127.0.0.1",
                webhook_listen_port=9443,
                webhook_path="/telegram/hook",
                webhook_healthcheck_enabled=True,
                webhook_healthcheck_listen_host="127.0.0.1",
                webhook_healthcheck_listen_port=8081,
                webhook_healthcheck_path="/healthz",
            ),
            resolve_telegram_webhook_url=lambda: "https://bot.example.com/telegram/hook",
            resolve_telegram_webhook_secret_token=lambda: "secret-token",
        )
    )
    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)

    monkeypatch.setattr(bot_runtime, "build_application", lambda **kwargs: application)
    monkeypatch.setattr(telegram_bot, "Update", SimpleNamespace(ALL_TYPES="all-types"))
    monkeypatch.setattr(telegram_bot, "WebhookHealthServer", HealthServerStub)
    monkeypatch.setattr(telegram_bot, "WebhookReadinessState", ReadinessStateStub)

    bot_runtime.run_webhook()

    assert len(created_health_servers) == 1
    assert created_health_servers[0].kwargs["listen_host"] == "127.0.0.1"
    assert created_health_servers[0].kwargs["listen_port"] == 8081
    assert created_health_servers[0].kwargs["path"] == "/healthz"
    assert created_health_servers[0].started is True
    assert created_health_servers[0].stopped is True
    assert application.run_webhook_calls == [
        {
            "listen": "127.0.0.1",
            "port": 9443,
            "url_path": "telegram/hook",
            "webhook_url": "https://bot.example.com/telegram/hook",
            "secret_token": "secret-token",
            "allowed_updates": "all-types",
        }
    ]


def test_run_webhook_skips_health_server_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    application = ApplicationStub()
    created_health_servers = []

    class HealthServerStub:
        def __init__(self, **kwargs) -> None:
            created_health_servers.append(kwargs)

        def start(self) -> None:
            raise AssertionError("health server should not start when disabled")

    runtime = RuntimeStub(
        settings=SimpleNamespace(
            telegram=SimpleNamespace(
                webhook_listen_host="127.0.0.1",
                webhook_listen_port=9443,
                webhook_path="/telegram/hook",
                webhook_healthcheck_enabled=False,
            ),
            resolve_telegram_webhook_url=lambda: "https://bot.example.com/telegram/hook",
            resolve_telegram_webhook_secret_token=lambda: "secret-token",
        )
    )
    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)

    monkeypatch.setattr(bot_runtime, "build_application", lambda **kwargs: application)
    monkeypatch.setattr(telegram_bot, "Update", SimpleNamespace(ALL_TYPES="all-types"))
    monkeypatch.setattr(telegram_bot, "WebhookHealthServer", HealthServerStub)

    bot_runtime.run_webhook()

    assert created_health_servers == []


def test_run_dispatches_to_webhook_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = RuntimeStub(settings=SimpleNamespace(telegram=SimpleNamespace(mode="webhook")))
    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)
    observed = []

    monkeypatch.setattr(bot_runtime, "run_webhook", lambda: observed.append("webhook"))
    monkeypatch.setattr(bot_runtime, "run_polling", lambda: observed.append("polling"))

    bot_runtime.run()

    assert observed == ["webhook"]


def test_run_dispatches_to_polling_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = RuntimeStub(settings=SimpleNamespace(telegram=SimpleNamespace(mode="polling")))
    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)
    observed = []

    monkeypatch.setattr(bot_runtime, "run_webhook", lambda: observed.append("webhook"))
    monkeypatch.setattr(bot_runtime, "run_polling", lambda: observed.append("polling"))

    bot_runtime.run()

    assert observed == ["polling"]


@pytest.mark.asyncio
async def test_start_runtime_tasks_binds_application_starts_worker_and_marks_ready() -> None:
    calls = []

    class WorkerStub:
        async def start(self) -> None:
            calls.append("worker")

    class NotifierStub:
        def bind_application(self, application) -> None:
            calls.append(("notifier", application))

    class ReadinessStub:
        def mark_ready(self) -> None:
            calls.append("ready")

    application = ApplicationStub()
    application.bot_data["runtime"] = RuntimeStub(
        settings=SimpleNamespace(),
        worker=WorkerStub(),
        lifecycle_notifier=NotifierStub(),
    )
    application.bot_data["webhook_readiness_state"] = ReadinessStub()

    await telegram_bot.start_runtime_tasks(application)

    assert calls[0] == ("notifier", application)
    assert calls[1:] == ["worker", "ready"]


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
