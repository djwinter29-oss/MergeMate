from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
import asyncio

import pytest

from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram.progress_notifier import (
    notify_terminal_update,
    start_progress_watcher,
    stop_progress_watchers,
    watch_run_progress,
)


class BotStub:
    def __init__(self, *, fail_first_send: bool = False) -> None:
        self.messages = []
        self.fail_first_send = fail_first_send

    async def send_message(self, chat_id: int, text: str) -> None:
        if self.fail_first_send:
            self.fail_first_send = False
            raise RuntimeError("telegram unavailable")
        self.messages.append((chat_id, text))


class ApplicationStub:
    def __init__(self, *, fail_first_send: bool = False) -> None:
        self.bot = BotStub(fail_first_send=fail_first_send)
        self.bot_data = {}
        self.created_tasks = []

    def create_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.created_tasks.append(task)
        return task


class GetRunStatusStub:
    def __init__(self, runs: list[object]) -> None:
        self._runs = list(runs)
        self._index = 0

    def execute(self, run_id: str):
        run = self._runs[min(self._index, len(self._runs) - 1)]
        self._index += 1
        return run


@dataclass(slots=True)
class RuntimeConfigStub:
    status_update_interval_seconds: int = 1


@dataclass(slots=True)
class SettingsStub:
    runtime: RuntimeConfigStub = field(default_factory=RuntimeConfigStub)


class RuntimeStub:
    def __init__(self, runs: list[AgentRun]) -> None:
        self.settings = SettingsStub()
        self.get_run_status = GetRunStatusStub(runs)


def _build_run(status: RunStatus, stage: str, review_iterations: int = 0) -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        run_id="run-1",
        chat_id=99,
        user_id=77,
        agent_name="coder",
        workflow="generate_code",
        status=status,
        current_stage=stage,
        prompt="build feature",
        estimate_seconds=30,
        plan_text="plan",
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=review_iterations,
        approved=True,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )


def _build_snapshot(run: AgentRun, tool_events: list[dict[str, str]] | None = None):
    tool_events = list(tool_events or [])
    return SimpleNamespace(
        run=run,
        tool_events=tool_events,
        latest_tool_event=tool_events[0] if tool_events else None,
        run_id=run.run_id,
        chat_id=run.chat_id,
        status=run.status,
        current_stage=run.current_stage,
        review_iterations=run.review_iterations,
        estimate_seconds=run.estimate_seconds,
        created_at=run.created_at,
    )


@pytest.mark.asyncio
async def test_watch_run_progress_sends_updates_for_stage_changes(monkeypatch) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub()
    runtime = RuntimeStub(
        [
            _build_snapshot(_build_run(RunStatus.RUNNING, "retrieve_context")),
            _build_snapshot(_build_run(RunStatus.RUNNING, "implementation", review_iterations=1)),
            _build_snapshot(_build_run(RunStatus.COMPLETED, "completed", review_iterations=1)),
        ]
    )

    await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 3
    assert "stage=retrieve_context" in application.bot.messages[0][1]
    assert "stage=implementation" in application.bot.messages[1][1]
    assert "Run run-1 completed." in application.bot.messages[2][1]


@pytest.mark.asyncio
async def test_watch_run_progress_skips_duplicate_snapshots_and_missing_runs(monkeypatch) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub()
    runtime = RuntimeStub([
        _build_snapshot(_build_run(RunStatus.RUNNING, "retrieve_context")),
        _build_snapshot(_build_run(RunStatus.RUNNING, "retrieve_context")),
        None,
    ])

    await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 1


@pytest.mark.asyncio
async def test_watch_run_progress_sends_update_for_new_tool_activity_on_same_stage(monkeypatch) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub()
    runtime = RuntimeStub(
        [
            _build_snapshot(_build_run(RunStatus.WAITING_TOOL, "tool:syntax_checker")),
            _build_snapshot(
                _build_run(RunStatus.WAITING_TOOL, "tool:syntax_checker"),
                tool_events=[{"tool_name": "syntax_checker", "action": "check", "status": "started", "detail": "Invoking tool."}],
            ),
            _build_snapshot(_build_run(RunStatus.COMPLETED, "completed")),
        ]
    )

    await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 3
    assert "Latest tool: syntax_checker check [started] - Invoking tool.." in application.bot.messages[1][1]
    assert "Run run-1 completed." in application.bot.messages[2][1]


@pytest.mark.asyncio
async def test_watch_run_progress_splits_oversized_updates(monkeypatch) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub()
    runtime = RuntimeStub(
        [
            _build_snapshot(
                _build_run(RunStatus.WAITING_TOOL, "tool:syntax_checker"),
                tool_events=[
                    {
                        "tool_name": "syntax_checker",
                        "action": "check",
                        "status": "started",
                        "detail": "x" * 5000,
                    }
                ],
            ),
            _build_snapshot(_build_run(RunStatus.COMPLETED, "completed")),
        ]
    )

    await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 3
    assert all(len(message_text) <= 4000 for _, message_text in application.bot.messages)


@pytest.mark.asyncio
async def test_watch_run_progress_logs_and_retries_after_send_failure(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub(fail_first_send=True)
    runtime = RuntimeStub(
        [
            _build_snapshot(_build_run(RunStatus.RUNNING, "retrieve_context")),
            _build_snapshot(_build_run(RunStatus.RUNNING, "retrieve_context")),
            _build_snapshot(_build_run(RunStatus.COMPLETED, "completed")),
        ]
    )

    with caplog.at_level("ERROR"):
        await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 2
    assert "stage=retrieve_context" in application.bot.messages[0][1]
    assert "Run run-1 completed." in application.bot.messages[1][1]
    assert "progress update delivery failed" in caplog.text


@pytest.mark.asyncio
async def test_watch_run_progress_retries_terminal_delivery_after_send_failure(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub(fail_first_send=True)
    runtime = RuntimeStub(
        [
            _build_snapshot(_build_run(RunStatus.COMPLETED, "completed")),
            _build_snapshot(_build_run(RunStatus.COMPLETED, "completed")),
        ]
    )

    with caplog.at_level("ERROR"):
        await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 1
    assert "Run run-1 completed." in application.bot.messages[0][1]
    assert "progress update delivery failed" in caplog.text


@pytest.mark.asyncio
async def test_watch_run_progress_skips_duplicate_terminal_delivery_after_immediate_send(monkeypatch) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub()
    terminal_run = _build_snapshot(_build_run(RunStatus.COMPLETED, "completed"))
    runtime = RuntimeStub([terminal_run, terminal_run])

    delivered = await notify_terminal_update(application, chat_id=99, run=terminal_run)
    assert delivered is True

    await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 1
    assert application.bot_data["terminal_deliveries"] == {"run-1"}


@pytest.mark.asyncio
async def test_start_progress_watcher_deduplicates_same_run(monkeypatch) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_watch_run_progress(application, runtime, chat_id: int, run_id: str) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr(
        "mergemate.interfaces.telegram.progress_notifier.watch_run_progress",
        fake_watch_run_progress,
    )
    application = ApplicationStub()
    runtime = RuntimeStub([])

    start_progress_watcher(application, runtime, 99, "run-1")
    await started.wait()
    start_progress_watcher(application, runtime, 99, "run-1")

    assert len(application.created_tasks) == 1

    release.set()
    await asyncio.gather(*application.created_tasks)
    assert application.bot_data["progress_watchers"] == {}


@pytest.mark.asyncio
async def test_stop_progress_watchers_cancels_active_tasks(monkeypatch) -> None:
    cancelled = asyncio.Event()

    async def fake_watch_run_progress(application, runtime, chat_id: int, run_id: str) -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(
        "mergemate.interfaces.telegram.progress_notifier.watch_run_progress",
        fake_watch_run_progress,
    )
    application = ApplicationStub()
    runtime = RuntimeStub([])

    start_progress_watcher(application, runtime, 99, "run-1")
    await asyncio.sleep(0)
    await stop_progress_watchers(application)

    assert cancelled.is_set() is True
    assert application.bot_data["progress_watchers"] == {}


@pytest.mark.asyncio
async def test_start_progress_watcher_cleanup_clears_terminal_delivery_tracking(monkeypatch) -> None:
    async def fake_watch_run_progress(application, runtime, chat_id: int, run_id: str) -> None:
        application.bot_data.setdefault("terminal_deliveries", set()).add(run_id)

    monkeypatch.setattr(
        "mergemate.interfaces.telegram.progress_notifier.watch_run_progress",
        fake_watch_run_progress,
    )
    application = ApplicationStub()
    runtime = RuntimeStub([])

    start_progress_watcher(application, runtime, 99, "run-1")
    await asyncio.gather(*application.created_tasks)

    assert application.bot_data["progress_watchers"] == {}
    assert application.bot_data["terminal_deliveries"] == set()


@pytest.mark.asyncio
async def test_stop_progress_watchers_clears_terminal_delivery_registry() -> None:
    application = ApplicationStub()
    application.bot_data["terminal_deliveries"] = {"run-1", "run-2"}

    await stop_progress_watchers(application)

    assert application.bot_data["terminal_deliveries"] == set()