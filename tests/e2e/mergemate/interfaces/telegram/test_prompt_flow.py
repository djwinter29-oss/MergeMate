from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mergemate.application.use_cases.submit_prompt import ApproveRunResult, SubmitPromptResult
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram import handlers


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


@dataclass(slots=True)
class FakeUser:
    id: int


@dataclass(slots=True)
class FakeChat:
    id: int


@dataclass(slots=True)
class FakeBot:
    sent_messages: list[tuple[int, str]] = field(default_factory=list)

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


@dataclass(slots=True)
class FakeApplication:
    runtime: object
    bot: FakeBot = field(default_factory=FakeBot)
    bot_data: dict[str, object] = field(init=False)

    def __post_init__(self) -> None:
        self.bot_data = {"runtime": self.runtime}

    def create_task(self, coroutine):
        return coroutine


@dataclass(slots=True)
class FakeContext:
    application: FakeApplication
    args: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RuntimeSettingsStub:
    default_agent: str = "coder"
    workflow_control: object = field(
        default_factory=lambda: SimpleNamespace(planner_agent_name="planner")
    )
    agents: dict[str, object] = field(
        default_factory=lambda: {"coder": SimpleNamespace(workflow="generate_code")}
    )


class GetRunStatusStub:
    def __init__(self, latest_run=None) -> None:
        self.latest_run = latest_run
        self.calls: list[tuple[str | None, int | None]] = []

    def execute(self, run_id: str | None = None, *, chat_id: int | None = None):
        self.calls.append((run_id, chat_id))
        return self.latest_run


class SubmitPromptStub:
    def __init__(self, result: SubmitPromptResult, revised_result: SubmitPromptResult | None = None) -> None:
        self.result = result
        self.revised_result = revised_result
        self.execute_calls: list[dict[str, object]] = []
        self.revise_calls: list[tuple[str, str]] = []

    async def execute(self, **kwargs) -> SubmitPromptResult:
        self.execute_calls.append(kwargs)
        return self.result

    async def revise_plan(self, run_id: str, feedback: str) -> SubmitPromptResult | None:
        self.revise_calls.append((run_id, feedback))
        return self.revised_result


class ApproveRunStub:
    def __init__(self, result: ApproveRunResult) -> None:
        self.result = result
        self.calls: list[str] = []

    def execute(self, run_id: str, on_finished=None):
        self.calls.append(run_id)
        return self.result


def _build_update(message_text: str):
    message = FakeMessage(message_text)
    update = SimpleNamespace(
        effective_message=message,
        effective_user=FakeUser(id=22),
        effective_chat=FakeChat(id=11),
    )
    return update, message


def _build_runtime(*, latest_run=None, submit_prompt=None, approve_run=None):
    return SimpleNamespace(
        settings=RuntimeSettingsStub(),
        get_run_status=GetRunStatusStub(latest_run=latest_run),
        submit_prompt=submit_prompt,
        approve_run=approve_run,
    )


def _awaiting_run(run_id: str = "run-1") -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        run_id=run_id,
        chat_id=11,
        user_id=22,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.AWAITING_CONFIRMATION,
        current_stage="awaiting_user_confirmation",
        prompt="initial prompt",
        estimate_seconds=30,
        plan_text="# Approved Plan\n1. initial prompt",
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_handle_prompt_returns_confirmation_plan_for_new_request(monkeypatch: pytest.MonkeyPatch) -> None:
    started_watchers: list[tuple[int, str]] = []
    submit_prompt = SubmitPromptStub(
        SubmitPromptResult(
            run_id="run-123",
            status=RunStatus.AWAITING_CONFIRMATION.value,
            estimate_seconds=30,
            plan_text="# Approved Plan\n1. build login flow",
        )
    )
    runtime = _build_runtime(latest_run=None, submit_prompt=submit_prompt, approve_run=None)
    application = FakeApplication(runtime)
    context = FakeContext(application=application)
    update, message = _build_update("build login flow")

    monkeypatch.setattr(
        handlers,
        "_start_progress_watcher",
        lambda application, runtime, chat_id, run_id: started_watchers.append((chat_id, run_id)),
    )

    await handlers.handle_prompt(update, context)

    assert submit_prompt.execute_calls
    assert started_watchers == []
    assert len(message.replies) == 1
    assert "Requirements captured for run run-123." in message.replies[0]
    assert "build login flow" in message.replies[0]


@pytest.mark.asyncio
async def test_handle_prompt_revises_existing_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    started_watchers: list[tuple[int, str]] = []
    latest_run = _awaiting_run("run-456")
    submit_prompt = SubmitPromptStub(
        SubmitPromptResult(
            run_id="unused",
            status=RunStatus.AWAITING_CONFIRMATION.value,
            estimate_seconds=30,
            plan_text="# Approved Plan\n1. unused",
        ),
        revised_result=SubmitPromptResult(
            run_id="run-456",
            status=RunStatus.AWAITING_CONFIRMATION.value,
            estimate_seconds=30,
            plan_text="# Approved Plan\n1. add audit logs",
        ),
    )
    runtime = _build_runtime(latest_run=latest_run, submit_prompt=submit_prompt, approve_run=None)
    application = FakeApplication(runtime)
    context = FakeContext(application=application)
    update, message = _build_update("add audit logs")

    monkeypatch.setattr(
        handlers,
        "_start_progress_watcher",
        lambda application, runtime, chat_id, run_id: started_watchers.append((chat_id, run_id)),
    )

    await handlers.handle_prompt(update, context)

    assert submit_prompt.execute_calls == []
    assert submit_prompt.revise_calls == [("run-456", "add audit logs")]
    assert started_watchers == []
    assert len(message.replies) == 1
    assert "Requirements captured for run run-456." in message.replies[0]
    assert "add audit logs" in message.replies[0]


@pytest.mark.asyncio
async def test_approve_command_replies_and_starts_progress_watcher(monkeypatch: pytest.MonkeyPatch) -> None:
    started_watchers: list[tuple[int, str]] = []
    latest_run = _awaiting_run("run-789")
    approve_run = ApproveRunStub(
        ApproveRunResult(run_id="run-789", dispatched=True, status=RunStatus.QUEUED.value)
    )
    runtime = _build_runtime(latest_run=latest_run, submit_prompt=None, approve_run=approve_run)
    application = FakeApplication(runtime)
    context = FakeContext(application=application)
    update, message = _build_update("/approve")

    monkeypatch.setattr(
        handlers,
        "_start_progress_watcher",
        lambda application, runtime, chat_id, run_id: started_watchers.append((chat_id, run_id)),
    )

    await handlers.approve_command(update, context)

    assert approve_run.calls == ["run-789"]
    assert started_watchers == [(11, "run-789")]
    assert len(message.replies) == 1
    assert message.replies[0] == (
        "Run run-789 approved. Retrieving context, designing, implementing, testing, and reviewing now."
    )