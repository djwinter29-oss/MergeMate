"""Tests for handlers.py uncovered branch paths.

Covers:
1.  handle_prompt returns when message is None [line 180]
2.  _continue_planning catches PromptSubmissionError and returns [lines 251-252]
3.  _continue_planning checks plan_text before sending confirmation [line 254]
"""
import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from mergemate.application.use_cases.submit_prompt import PromptSubmissionError
from mergemate.domain.shared import RunStatus
from mergemate.interfaces.telegram import handlers


@dataclass(slots=True)
class MessageStub:
    text: str | None
    replies: list[str] = field(default_factory=list)

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

    def create_task(self, task):
        created_task = asyncio.create_task(task)
        self.created_tasks.append(created_task)
        return created_task


@dataclass(slots=True)
class ContextStub:
    application: ApplicationStub
    args: list[str] = field(default_factory=list)


class SubmitPromptStub:
    def __init__(self, execute_result=None, complete_result=None, complete_error: Exception | None = None) -> None:
        self.execute_result = execute_result
        self.complete_result = complete_result
        self.complete_error = complete_error
        self.execute_calls = []
        self.complete_calls = []

    async def execute(self, **kwargs):
        self.execute_calls.append(kwargs)
        return self.execute_result

    async def complete_planning(self, run_id: str):
        self.complete_calls.append(run_id)
        if self.complete_error:
            raise self.complete_error
        return self.complete_result


class GetRunStatusStub:
    def __init__(self, results=None) -> None:
        self.results = list(results or [])

    def execute(self, **kwargs):
        if not self.results:
            return None
        return self.results.pop(0)


def _runtime(*, submit=None, latest=None, default_agent="coder", workflow="generate_code"):
    settings = SimpleNamespace(
        default_agent=default_agent,
        agents={default_agent: SimpleNamespace(workflow=workflow)},
        resolve_agent_name_for_workflow=lambda requested_workflow: "planner" if requested_workflow == "planning" else default_agent,
    )
    return SimpleNamespace(
        settings=settings,
        services=SimpleNamespace(
            submit_prompt=submit or SubmitPromptStub(),
            get_run_status=latest or GetRunStatusStub(),
        ),
    )


class TestHandlePromptMessageIsNone:
    @pytest.mark.asyncio
    async def test_returns_when_message_is_none(self) -> None:
        """Line 180: handle_prompt returns early when effective_message is None."""
        runtime = _runtime()
        application = ApplicationStub(runtime)
        update = UpdateStub(effective_message=None)

        await handlers.handle_prompt(update, ContextStub(application))

        assert application.bot.messages == []


class TestContinuePlanning:
    @pytest.mark.asyncio
    async def test_suppresses_prompt_submission_error(self) -> None:
        """Lines 251-252: _continue_planning catches PromptSubmissionError and returns."""
        run = SimpleNamespace(
            run_id="run-continue-1",
            status=RunStatus.AWAITING_CONFIRMATION,
            plan_text="plan content",
            estimate_seconds=15,
            chat_id=5,
            created_at="now",
            current_stage="planning",
            review_iterations=0,
            approved=False,
            result_text=None,
        )

        # submit_prompt.execute returns a result, but complete_planning raises
        submit = SubmitPromptStub(
            execute_result=run,
            complete_error=PromptSubmissionError("run-continue-1", "oops"),
        )

        runtime = _runtime(submit=submit)

        # We need to trigger handle_prompt which sets up _continue_planning
        # _continue_planning captures variables from the enclosing scope
        message = MessageStub("/ask build something")
        application = ApplicationStub(runtime)
        update = UpdateStub(message)
        context = ContextStub(application)

        await handlers.handle_prompt(update, context)

        # The bg task should have been created
        assert len(application.created_tasks) == 1
        await asyncio.gather(*application.created_tasks)

        # complete_planning was called but the error was suppressed
        assert submit.complete_calls == ["run-continue-1"]

    @pytest.mark.asyncio
    async def test_skips_confirmation_when_plan_text_is_none(self) -> None:
        """Line 254: _continue_planning skips sending when plan_text is None/empty."""
        run = SimpleNamespace(
            run_id="run-no-plan",
            status=RunStatus.AWAITING_CONFIRMATION,
            plan_text=None,  # no plan text -> skip notification
            estimate_seconds=15,
            chat_id=5,
            created_at="now",
            current_stage="planning",
            review_iterations=0,
            approved=False,
            result_text=None,
        )

        submit = SubmitPromptStub(execute_result=run, complete_result=run)
        runtime = _runtime(submit=submit)

        message = MessageStub("/ask build something")
        application = ApplicationStub(runtime)
        update = UpdateStub(message)
        context = ContextStub(application)

        await handlers.handle_prompt(update, context)

        assert len(application.created_tasks) == 1
        await asyncio.gather(*application.created_tasks)

        # The bot should NOT have sent any follow-up messages
        assert application.bot.messages == []