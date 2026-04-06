from dataclasses import dataclass

import pytest

from mergemate.application.jobs.dispatcher import RunDispatcher
from mergemate.application.use_cases.cancel_run import CancelRunUseCase
from mergemate.application.services.context_service import ContextService
from mergemate.application.use_cases.approve_run import ApproveRunUseCase
from mergemate.application.use_cases.get_run_status import GetRunStatusUseCase
from mergemate.application.use_cases.submit_prompt import SubmitPromptUseCase
from mergemate.domain.runs.value_objects import RunStatus
from mergemate.infrastructure.persistence.sqlite import (
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteRunRepository,
)


class WorkerStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enqueue(self, run_id: str, on_finished=None) -> None:
        self.calls.append(run_id)


class PlanningServiceStub:
    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        suffix = f"\n\nPrior feedback:\n{prior_feedback}" if prior_feedback else ""
        return f"# Approved Plan\n1. {prompt.strip()}{suffix}"

    async def revise_plan(self, existing_prompt: str, feedback: str) -> tuple[str, str]:
        updated_prompt = f"{existing_prompt}\n\nAdditional user feedback:\n{feedback.strip()}"
        return updated_prompt, f"# Approved Plan\n1. {updated_prompt}"


@dataclass(slots=True)
class WorkflowControlConfigStub:
    require_confirmation: bool


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlConfigStub


@pytest.fixture
def sqlite_runtime(tmp_path):
    database = SQLiteDatabase(tmp_path / "integration.db")
    database.initialize()
    run_repository = SQLiteRunRepository(database)
    conversation_repository = SQLiteConversationRepository(database)
    context_service = ContextService(conversation_repository)
    worker = WorkerStub()
    dispatcher = RunDispatcher(worker)
    submit_prompt = SubmitPromptUseCase(
        run_repository,
        context_service,
        dispatcher,
        PlanningServiceStub(),
        SettingsStub(WorkflowControlConfigStub(require_confirmation=True)),
    )
    return {
        "database": database,
        "run_repository": run_repository,
        "conversation_repository": conversation_repository,
        "submit_prompt": submit_prompt,
        "approve_run": ApproveRunUseCase(submit_prompt),
        "cancel_run": CancelRunUseCase(run_repository),
        "get_run_status": GetRunStatusUseCase(run_repository),
        "worker": worker,
    }


@pytest.mark.asyncio
async def test_submit_prompt_persists_run_plan_and_conversation(sqlite_runtime) -> None:
    submit_result = await sqlite_runtime["submit_prompt"].execute(
        chat_id=321,
        user_id=654,
        agent_name="coder",
        workflow="generate_code",
        prompt="build login flow",
    )
    planned_result = await sqlite_runtime["submit_prompt"].complete_planning(submit_result.run_id)

    saved_run = sqlite_runtime["run_repository"].get(submit_result.run_id)
    latest_run = sqlite_runtime["get_run_status"].execute(chat_id=321)
    messages = sqlite_runtime["conversation_repository"].list_messages(321)

    assert submit_result.status == RunStatus.AWAITING_CONFIRMATION.value
    assert submit_result.plan_text is None
    assert planned_result is not None
    assert saved_run is not None
    assert saved_run.status == RunStatus.AWAITING_CONFIRMATION
    assert saved_run.current_stage == "awaiting_user_confirmation"
    assert saved_run.plan_text == "# Approved Plan\n1. build login flow"
    assert latest_run is not None
    assert latest_run.run_id == submit_result.run_id
    assert messages == [{"role": "user", "content": "build login flow"}]
    assert sqlite_runtime["worker"].calls == []


@pytest.mark.asyncio
async def test_approve_run_dispatches_and_updates_persisted_status(sqlite_runtime) -> None:
    submit_result = await sqlite_runtime["submit_prompt"].execute(
        chat_id=777,
        user_id=888,
        agent_name="coder",
        workflow="generate_code",
        prompt="implement audit logs",
    )
    await sqlite_runtime["submit_prompt"].complete_planning(submit_result.run_id)

    approval_result = sqlite_runtime["approve_run"].execute(submit_result.run_id, chat_id=777)
    saved_run = sqlite_runtime["run_repository"].get(submit_result.run_id)

    assert approval_result is not None
    assert approval_result.dispatched is True
    assert approval_result.status == RunStatus.QUEUED.value
    assert saved_run is not None
    assert saved_run.approved is True
    assert saved_run.status == RunStatus.QUEUED
    assert saved_run.current_stage == "queued_for_execution"
    assert sqlite_runtime["worker"].calls == [submit_result.run_id]


@pytest.mark.asyncio
async def test_run_access_is_scoped_to_chat(sqlite_runtime) -> None:
    submit_result = await sqlite_runtime["submit_prompt"].execute(
        chat_id=100,
        user_id=200,
        agent_name="coder",
        workflow="generate_code",
        prompt="build billing flow",
    )

    assert sqlite_runtime["get_run_status"].execute(submit_result.run_id, chat_id=999) is None
    assert sqlite_runtime["approve_run"].execute(submit_result.run_id, chat_id=999) is None
    assert await sqlite_runtime["submit_prompt"].revise_plan_for_chat(
        submit_result.run_id,
        "change scope",
        chat_id=999,
    ) is None
    assert sqlite_runtime["cancel_run"].execute(submit_result.run_id, chat_id=999) is None
    assert sqlite_runtime["worker"].calls == []