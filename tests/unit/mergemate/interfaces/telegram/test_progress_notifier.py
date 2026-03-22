from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram.progress_notifier import watch_run_progress


class BotStub:
    def __init__(self) -> None:
        self.messages = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class ApplicationStub:
    def __init__(self) -> None:
        self.bot = BotStub()


class GetRunStatusStub:
    def __init__(self, runs: list[AgentRun]) -> None:
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


@pytest.mark.asyncio
async def test_watch_run_progress_sends_updates_for_stage_changes(monkeypatch) -> None:
    async def _sleep(_seconds: int) -> None:
        return None

    monkeypatch.setattr("mergemate.interfaces.telegram.progress_notifier.asyncio.sleep", _sleep)
    application = ApplicationStub()
    runtime = RuntimeStub(
        [
            _build_run(RunStatus.RUNNING, "retrieve_context"),
            _build_run(RunStatus.RUNNING, "implementation", review_iterations=1),
            _build_run(RunStatus.COMPLETED, "completed", review_iterations=1),
        ]
    )

    await watch_run_progress(application, runtime, chat_id=99, run_id="run-1")

    assert len(application.bot.messages) == 2
    assert "stage=retrieve_context" in application.bot.messages[0][1]
    assert "stage=implementation" in application.bot.messages[1][1]