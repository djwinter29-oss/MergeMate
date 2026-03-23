from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from mergemate.domain.runs.value_objects import RunStatus
from mergemate.interfaces.telegram import handlers


class MessageStub:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


@dataclass(slots=True)
class UserStub:
    id: int = 3


@dataclass(slots=True)
class ChatStub:
    id: int = 5


@dataclass(slots=True)
class UpdateStub:
    effective_message: MessageStub | None
    effective_user: UserStub | None = field(default_factory=UserStub)
    effective_chat: ChatStub | None = field(default_factory=ChatStub)


class BotStub:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class ApplicationStub:
    def __init__(self, runtime) -> None:
        self.bot_data = {"runtime": runtime}
        self.bot = BotStub()
        self.created_tasks = []

    def create_task(self, task) -> None:
        self.created_tasks.append(task)


@dataclass(slots=True)
class ContextStub:
    application: ApplicationStub
    args: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunStub:
    run_id: str = "run-1"
    status: RunStatus = RunStatus.AWAITING_CONFIRMATION
    current_stage: str = "planning"
    review_iterations: int = 0
    approved: bool = False
    estimate_seconds: int = 15
    plan_text: str | None = "plan"
    result_text: str | None = "done"
    error_text: str | None = None
    chat_id: int = 5
    created_at: object = field(default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").UTC))


class GetRunStatusStub:
    def __init__(self, results=None) -> None:
        self.results = list(results or [])
        self.calls = []

    def execute(self, run_id: str | None = None, chat_id: int | None = None, tool_event_limit: int = 5):
        self.calls.append((run_id, chat_id, tool_event_limit))
        if not self.results:
            return None
        return self.results.pop(0)


class SubmitPromptStub:
    def __init__(self, execute_result=None, revise_result=None) -> None:
        self.execute_result = execute_result
        self.revise_result = revise_result
        self.execute_calls = []
        self.revise_calls = []

    async def execute(self, **kwargs):
        self.execute_calls.append(kwargs)
        return self.execute_result

    async def revise_plan_for_chat(self, run_id: str, feedback: str, *, chat_id: int | None = None):
        self.revise_calls.append((run_id, feedback, chat_id))
        return self.revise_result


class ApproveRunStub:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    def execute(self, run_id: str, *, chat_id: int | None = None, on_finished=None):
        self.calls.append((run_id, chat_id, on_finished is not None))
        return self.result


class CancelRunStub:
    def __init__(self, result) -> None:
        self.result = result
        self.calls = []

    def execute(self, run_id: str | None = None, chat_id: int | None = None):
        self.calls.append((run_id, chat_id))
        return self.result


def _runtime(*, latest=None, submit=None, approve=None, cancel=None, default_agent="coder", workflow="generate_code"):
    settings = SimpleNamespace(
        default_agent=default_agent,
        agents={default_agent: SimpleNamespace(workflow=workflow)},
        resolve_agent_name_for_workflow=lambda requested_workflow: "planner" if requested_workflow == "planning" else default_agent,
    )
    return SimpleNamespace(
        settings=settings,
        get_run_status=latest or GetRunStatusStub(),
        submit_prompt=submit or SubmitPromptStub(),
        approve_run=approve or ApproveRunStub(None),
        cancel_run=cancel or CancelRunStub(None),
    )


@pytest.mark.asyncio
async def test_start_command_replies_with_welcome() -> None:
    runtime = _runtime()
    message = MessageStub("/start")
    await handlers.start_command(UpdateStub(message), ContextStub(ApplicationStub(runtime)))

    assert "MergeMate is running" in message.replies[0]


@pytest.mark.asyncio
async def test_start_and_status_commands_return_when_message_or_chat_missing() -> None:
    runtime = _runtime()
    application = ApplicationStub(runtime)

    await handlers.start_command(UpdateStub(None), ContextStub(application))
    await handlers.status_command(UpdateStub(MessageStub("/status"), effective_chat=None), ContextStub(application))
    await handlers.tools_command(UpdateStub(MessageStub("/tools"), effective_chat=None), ContextStub(application))

    assert application.bot.messages == []


@pytest.mark.asyncio
async def test_status_command_handles_missing_and_existing_runs() -> None:
    runtime = _runtime(latest=GetRunStatusStub([None, RunStub(status=RunStatus.RUNNING)]))
    application = ApplicationStub(runtime)

    missing_message = MessageStub("/status")
    await handlers.status_command(UpdateStub(missing_message), ContextStub(application))
    assert missing_message.replies == ["No runs found for this chat."]

    status_message = MessageStub("/status run-1")
    await handlers.status_command(UpdateStub(status_message), ContextStub(application, args=["run-1"]))
    assert "Run run-1 is running." in status_message.replies[0]
    assert runtime.get_run_status.calls == [(None, 5, 5), ("run-1", 5, 5)]


@pytest.mark.asyncio
async def test_tools_command_handles_missing_existing_and_latest_runs() -> None:
    run_with_tools = SimpleNamespace(
        run_id="run-1",
        tool_events=[
            {
                "tool_name": "syntax_checker",
                "action": "check",
                "status": "ok",
                "detail": "done",
                "created_at": "2026-03-23T10:15:00+00:00",
            }
        ],
    )
    runtime = _runtime(latest=GetRunStatusStub([None, run_with_tools, run_with_tools]))
    application = ApplicationStub(runtime)

    missing_message = MessageStub("/tools")
    await handlers.tools_command(UpdateStub(missing_message), ContextStub(application))
    assert missing_message.replies == ["No runs found for this chat."]

    explicit_message = MessageStub("/tools run-1")
    await handlers.tools_command(UpdateStub(explicit_message), ContextStub(application, args=["run-1"]))
    assert "Tool activity for run run-1:" in explicit_message.replies[0]
    assert "syntax_checker check [ok]: done" in explicit_message.replies[0]
    assert "2026-03-23 10:15:00 UTC" in explicit_message.replies[0]

    latest_message = MessageStub("/tools")
    await handlers.tools_command(UpdateStub(latest_message), ContextStub(application))
    assert "Tool activity for run run-1:" in latest_message.replies[0]
    assert runtime.get_run_status.calls == [(None, 5, 10), ("run-1", 5, 10), (None, 5, 10)]


@pytest.mark.asyncio
async def test_tools_command_accepts_limit_with_or_without_run_id() -> None:
    run_with_tools = SimpleNamespace(
        run_id="run-1",
        tool_events=[
            {
                "tool_name": "syntax_checker",
                "action": "check",
                "status": "ok",
                "detail": "done",
                "created_at": "2026-03-23T10:15:00+00:00",
            }
        ],
    )
    runtime = _runtime(latest=GetRunStatusStub([run_with_tools, run_with_tools]))
    application = ApplicationStub(runtime)

    latest_message = MessageStub("/tools 15")
    await handlers.tools_command(UpdateStub(latest_message), ContextStub(application, args=["15"]))
    assert "Tool activity for run run-1:" in latest_message.replies[0]

    explicit_message = MessageStub("/tools run-1 7")
    await handlers.tools_command(UpdateStub(explicit_message), ContextStub(application, args=["run-1", "7"]))
    assert "Tool activity for run run-1:" in explicit_message.replies[0]
    assert runtime.get_run_status.calls == [(None, 5, 15), ("run-1", 5, 7)]


@pytest.mark.asyncio
async def test_tools_command_rejects_invalid_limit_values() -> None:
    runtime = _runtime(latest=GetRunStatusStub())
    application = ApplicationStub(runtime)

    zero_only_message = MessageStub("/tools 0")
    await handlers.tools_command(UpdateStub(zero_only_message), ContextStub(application, args=["0"]))
    assert zero_only_message.replies == ["Usage: /tools [run_id] [limit]. Limit must be a positive integer."]

    bad_text_message = MessageStub("/tools run-1 many")
    await handlers.tools_command(UpdateStub(bad_text_message), ContextStub(application, args=["run-1", "many"]))
    assert bad_text_message.replies == ["Usage: /tools [run_id] [limit]. Limit must be a positive integer."]

    zero_with_run_message = MessageStub("/tools run-1 0")
    await handlers.tools_command(UpdateStub(zero_with_run_message), ContextStub(application, args=["run-1", "0"]))
    assert zero_with_run_message.replies == ["Usage: /tools [run_id] [limit]. Limit must be a positive integer."]

    too_many_args_message = MessageStub("/tools run-1 5 extra")
    await handlers.tools_command(UpdateStub(too_many_args_message), ContextStub(application, args=["run-1", "5", "extra"]))
    assert too_many_args_message.replies == ["Usage: /tools [run_id] [limit]."]


@pytest.mark.asyncio
async def test_approve_command_handles_missing_failed_and_not_needed_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    started = []
    monkeypatch.setattr(handlers, "_start_progress_watcher", lambda app, runtime, chat_id, run_id: started.append((chat_id, run_id)))
    runtime = _runtime(
        latest=GetRunStatusStub([None, RunStub(run_id="run-2")]),
        approve=ApproveRunStub(SimpleNamespace(run_id="run-3", dispatched=False, status="completed")),
    )
    application = ApplicationStub(runtime)

    missing_message = MessageStub("/approve")
    await handlers.approve_command(UpdateStub(missing_message), ContextStub(application))
    assert missing_message.replies == ["No run is available to approve."]

    fail_runtime = _runtime(approve=ApproveRunStub(None))
    fail_message = MessageStub("/approve run-1")
    await handlers.approve_command(UpdateStub(fail_message), ContextStub(ApplicationStub(fail_runtime), args=["run-1"]))
    assert fail_message.replies == ["Run approval failed."]

    noop_message = MessageStub("/approve run-3")
    await handlers.approve_command(UpdateStub(noop_message), ContextStub(application, args=["run-3"]))
    assert "was not re-approved" in noop_message.replies[0]
    assert started == []


@pytest.mark.asyncio
async def test_approve_command_starts_watcher_when_dispatched(monkeypatch: pytest.MonkeyPatch) -> None:
    started = []
    monkeypatch.setattr(handlers, "_start_progress_watcher", lambda app, runtime, chat_id, run_id: started.append((chat_id, run_id)))
    runtime = _runtime(approve=ApproveRunStub(SimpleNamespace(run_id="run-4", dispatched=True, status="queued")))
    application = ApplicationStub(runtime)
    message = MessageStub("/approve run-4")

    await handlers.approve_command(UpdateStub(message), ContextStub(application, args=["run-4"]))

    assert "approved" in message.replies[0]
    assert started == [(5, "run-4")]


@pytest.mark.asyncio
async def test_approve_command_uses_latest_run_when_no_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    started = []
    monkeypatch.setattr(handlers, "_start_progress_watcher", lambda app, runtime, chat_id, run_id: started.append((chat_id, run_id)))
    runtime = _runtime(
        latest=GetRunStatusStub([RunStub(run_id="run-latest")]),
        approve=ApproveRunStub(SimpleNamespace(run_id="run-latest", dispatched=True, status="queued")),
    )

    message = MessageStub("/approve")
    await handlers.approve_command(UpdateStub(message), ContextStub(ApplicationStub(runtime)))

    assert started == [(5, "run-latest")]


@pytest.mark.asyncio
async def test_cancel_command_handles_missing_and_successful_cancel() -> None:
    runtime = _runtime(cancel=CancelRunStub(None))
    missing_message = MessageStub("/cancel")
    await handlers.cancel_command(UpdateStub(missing_message), ContextStub(ApplicationStub(runtime)))
    assert missing_message.replies == ["No run could be cancelled."]

    runtime = _runtime(cancel=CancelRunStub(SimpleNamespace(run_id="run-5")))
    message = MessageStub("/cancel run-5")
    await handlers.cancel_command(UpdateStub(message), ContextStub(ApplicationStub(runtime), args=["run-5"]))
    assert message.replies == ["Run run-5 was cancelled."]


@pytest.mark.asyncio
async def test_handle_prompt_ignores_blank_message() -> None:
    runtime = _runtime()
    message = MessageStub("   ")

    await handlers.handle_prompt(UpdateStub(message), ContextStub(ApplicationStub(runtime)))

    assert message.replies == []


def test_build_request_uses_runtime_default_agent() -> None:
    runtime = _runtime(default_agent="reviewer")
    request = handlers._build_request(UpdateStub(MessageStub("hello")), runtime)

    assert request.chat_id == 5
    assert request.user_id == 3
    assert request.message_text == "hello"
    assert request.agent_name == "reviewer"


def test_start_progress_watcher_creates_task(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _runtime()
    application = ApplicationStub(runtime)
    monkeypatch.setattr(handlers, "watch_run_progress", lambda application, runtime, chat_id, run_id: "watcher")

    handlers._start_progress_watcher(application, runtime, 5, "run-1")

    assert application.created_tasks == ["watcher"]


@pytest.mark.asyncio
async def test_approve_and_cancel_commands_return_when_message_or_chat_missing() -> None:
    runtime = _runtime()
    application = ApplicationStub(runtime)

    await handlers.approve_command(UpdateStub(MessageStub("/approve"), effective_chat=None), ContextStub(application))
    await handlers.cancel_command(UpdateStub(MessageStub("/cancel"), effective_chat=None), ContextStub(application))

    assert application.bot.messages == []


@pytest.mark.asyncio
async def test_handle_prompt_revises_existing_plan_and_handles_failure() -> None:
    latest = GetRunStatusStub([RunStub(run_id="run-6", status=RunStatus.AWAITING_CONFIRMATION), RunStub(run_id="run-6", status=RunStatus.AWAITING_CONFIRMATION)])
    runtime = _runtime(latest=latest, submit=SubmitPromptStub(revise_result=SimpleNamespace(run_id="run-6", plan_text="updated plan", estimate_seconds=10)))
    application = ApplicationStub(runtime)
    message = MessageStub("add tests")

    await handlers.handle_prompt(UpdateStub(message), ContextStub(application))

    assert "Requirements captured for run run-6." in message.replies[0]
    assert runtime.submit_prompt.revise_calls == [("run-6", "add tests", 5)]

    failed_runtime = _runtime(
        latest=GetRunStatusStub([RunStub(run_id="run-7", status=RunStatus.AWAITING_CONFIRMATION)]),
        submit=SubmitPromptStub(revise_result=None),
    )
    failed_message = MessageStub("add logs")
    await handlers.handle_prompt(UpdateStub(failed_message), ContextStub(ApplicationStub(failed_runtime)))
    assert failed_message.replies == ["Could not revise the current plan."]


@pytest.mark.asyncio
async def test_handle_prompt_handles_auto_execution_and_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    started = []
    monkeypatch.setattr(handlers, "_start_progress_watcher", lambda app, runtime, chat_id, run_id: started.append((chat_id, run_id)))

    auto_submit = SubmitPromptStub(execute_result=SimpleNamespace(run_id="run-8", status="queued", plan_text="plan", estimate_seconds=12))
    auto_runtime = _runtime(latest=GetRunStatusStub([None]), submit=auto_submit, workflow="debug_code")
    auto_message = MessageStub("debug it")
    await handlers.handle_prompt(UpdateStub(auto_message), ContextStub(ApplicationStub(auto_runtime)))
    assert "started automatically" in auto_message.replies[0]
    assert auto_submit.execute_calls[0]["workflow"] == "debug_code"
    assert started == [(5, "run-8")]

    confirm_submit = SubmitPromptStub(execute_result=SimpleNamespace(run_id="run-9", status="awaiting_confirmation", plan_text="plan", estimate_seconds=18))
    confirm_runtime = _runtime(latest=GetRunStatusStub([None]), submit=confirm_submit)
    confirm_message = MessageStub("build it")
    await handlers.handle_prompt(UpdateStub(confirm_message), ContextStub(ApplicationStub(confirm_runtime)))
    assert "Requirements captured for run run-9." in confirm_message.replies[0]


@pytest.mark.asyncio
async def test_notify_terminal_update_formats_terminal_messages() -> None:
    runtime = _runtime()
    application = ApplicationStub(runtime)

    await handlers._notify_terminal_update(application, 5, SimpleNamespace(status=RunStatus.COMPLETED, run_id="run-1", result_text="done", error_text=None))
    await handlers._notify_terminal_update(application, 5, SimpleNamespace(status=RunStatus.CANCELLED, run_id="run-2", result_text=None, error_text=None))
    await handlers._notify_terminal_update(application, 5, SimpleNamespace(status=RunStatus.FAILED, run_id="run-3", result_text=None, error_text="boom"))

    assert application.bot.messages == [
        (5, "Run run-1 completed.\n\ndone"),
        (5, "Run run-2 was cancelled."),
        (5, "Run run-3 failed.\n\nboom"),
    ]