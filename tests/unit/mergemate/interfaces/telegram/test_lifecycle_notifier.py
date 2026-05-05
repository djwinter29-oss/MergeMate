"""Unit tests for TelegramRunLifecycleNotifier."""

from dataclasses import dataclass

import pytest

from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram.lifecycle_notifier import TelegramRunLifecycleNotifier


class BotStub:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class ApplicationStub:
    def __init__(self) -> None:
        self.bot = BotStub()


class SettingsStub:
    def resolve_agent_name_for_workflow(self, workflow: str) -> str:
        return "planner"


@dataclass(slots=True)
class RunStub:
    run_id: str
    status: RunStatus = RunStatus.RUNNING
    chat_id: int = 99
    plan_text: str | None = "plan"
    estimate_seconds: int = 30
    error_text: str | None = None


@pytest.mark.asyncio
async def test_notify_plan_ready_returns_true_and_sends_message() -> None:
    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    notifier.bind_application(ApplicationStub())
    run = RunStub(run_id="run-1")

    result = await notifier.notify_plan_ready(run)

    assert result is True
    assert len(notifier._application.bot.messages) == 1  # type: ignore[union-attr]
    chat_id, text = notifier._application.bot.messages[0]  # type: ignore[union-attr]
    assert chat_id == 99
    assert "run-1" in text


@pytest.mark.asyncio
async def test_notify_plan_ready_returns_false_when_application_not_bound() -> None:
    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    run = RunStub(run_id="run-1")

    result = await notifier.notify_plan_ready(run)

    assert result is False


@pytest.mark.asyncio
async def test_notify_plan_ready_returns_false_on_send_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    application = ApplicationStub()
    notifier.bind_application(application)

    async def failing_send(*args: object, **kwargs: object) -> None:
        raise RuntimeError("send failed")

    monkeypatch.setattr(application.bot, "send_message", failing_send)
    run = RunStub(run_id="run-1")

    result = await notifier.notify_plan_ready(run)

    assert result is False
    assert len(application.bot.messages) == 0


@pytest.mark.asyncio
async def test_notify_auto_execution_started_returns_true_and_sends_message_and_starts_watcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_watchers: list[tuple[object, object, int, str]] = []
    monkeypatch.setattr(
        "mergemate.interfaces.telegram.lifecycle_notifier.start_progress_watcher",
        lambda application, runtime, chat_id, run_id: started_watchers.append((application, runtime, chat_id, run_id)),
    )

    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    application = ApplicationStub()
    notifier.bind_application(application)
    runtime = object()
    notifier.bind_runtime(runtime)
    run = RunStub(run_id="run-2")

    result = await notifier.notify_auto_execution_started(run)

    assert result is True
    assert len(application.bot.messages) == 1
    assert started_watchers == [(application, runtime, 99, "run-2")]


@pytest.mark.asyncio
async def test_notify_auto_execution_started_returns_false_when_application_not_bound() -> None:
    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    notifier.bind_runtime(object())
    run = RunStub(run_id="run-2")

    result = await notifier.notify_auto_execution_started(run)

    assert result is False


@pytest.mark.asyncio
async def test_notify_auto_execution_started_returns_false_when_runtime_not_bound() -> None:
    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    notifier.bind_application(ApplicationStub())
    run = RunStub(run_id="run-2")

    result = await notifier.notify_auto_execution_started(run)

    assert result is False


@pytest.mark.asyncio
async def test_notify_auto_execution_started_returns_false_on_send_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mergemate.interfaces.telegram.lifecycle_notifier.start_progress_watcher",
        lambda application, runtime, chat_id, run_id: None,
    )

    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    application = ApplicationStub()
    notifier.bind_application(application)
    notifier.bind_runtime(object())

    async def failing_send(*args: object, **kwargs: object) -> None:
        raise RuntimeError("send failed")

    monkeypatch.setattr(application.bot, "send_message", failing_send)
    run = RunStub(run_id="run-2")

    result = await notifier.notify_auto_execution_started(run)

    assert result is False
    assert len(application.bot.messages) == 0


@pytest.mark.asyncio
async def test_notify_terminal_returns_false_when_application_not_bound() -> None:
    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    run = RunStub(run_id="run-3")

    result = await notifier.notify_terminal(run)

    assert result is False


@pytest.mark.asyncio
async def test_notify_terminal_returns_false_for_non_terminal_statuses() -> None:
    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    notifier.bind_application(ApplicationStub())
    run = RunStub(run_id="run-3", status=RunStatus.RUNNING)

    result = await notifier.notify_terminal(run)

    assert result is False


@pytest.mark.asyncio
async def test_notify_terminal_delegates_to_notify_terminal_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_notify(*args: object, **kwargs: object) -> bool:
        terminal_calls.append(args)
        return True

    terminal_calls: list[tuple[object, int, object]] = []
    monkeypatch.setattr(
        "mergemate.interfaces.telegram.lifecycle_notifier.notify_terminal_update",
        fake_notify,
    )

    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    notifier.bind_application(ApplicationStub())
    run = RunStub(run_id="run-3", status=RunStatus.COMPLETED)

    result = await notifier.notify_terminal(run)

    assert result is True


@pytest.mark.asyncio
async def test_notify_terminal_forwards_for_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_notify(*args: object, **kwargs: object) -> bool:
        terminal_calls.append(args)
        return True

    terminal_calls: list[tuple[object, int, object]] = []
    monkeypatch.setattr(
        "mergemate.interfaces.telegram.lifecycle_notifier.notify_terminal_update",
        fake_notify,
    )

    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    notifier.bind_application(ApplicationStub())
    run = RunStub(run_id="run-4", status=RunStatus.FAILED)

    result = await notifier.notify_terminal(run)

    assert result is True


@pytest.mark.asyncio
async def test_notify_terminal_forwards_for_cancelled_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_notify(*args: object, **kwargs: object) -> bool:
        terminal_calls.append(args)
        return True

    terminal_calls: list[tuple[object, int, object]] = []
    monkeypatch.setattr(
        "mergemate.interfaces.telegram.lifecycle_notifier.notify_terminal_update",
        fake_notify,
    )

    notifier = TelegramRunLifecycleNotifier(SettingsStub())
    notifier.bind_application(ApplicationStub())
    run = RunStub(run_id="run-5", status=RunStatus.CANCELLED)

    result = await notifier.notify_terminal(run)

    assert result is True