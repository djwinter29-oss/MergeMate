from dataclasses import dataclass

import pytest

from mergemate.application.use_cases.submit_prompt import SubmitPromptUseCase
from mergemate.domain.runs.value_objects import RunStatus


class InMemoryRunRepository:
    def __init__(self) -> None:
        self.runs = {}

    def create(self, run) -> None:
        self.runs[run.run_id] = run

    def get(self, run_id: str):
        return self.runs.get(run_id)

    def update_plan(self, run_id: str, plan_text: str, prompt: str | None = None, *, current_stage: str | None = None):
        run = self.runs[run_id]
        run.plan_text = plan_text
        if prompt is not None:
            run.prompt = prompt
        run.current_stage = current_stage or "awaiting_user_confirmation"
        return run

    def approve(self, run_id: str):
        run = self.runs[run_id]
        if run.approved:
            return run
        if run.status == RunStatus.AWAITING_CONFIRMATION:
            run.approved = True
            run.status = RunStatus.QUEUED
            run.current_stage = "queued_for_execution"
            return run
        if run.status == RunStatus.QUEUED:
            run.approved = True
        return run


class ContextServiceStub:
    def __init__(self) -> None:
        self.messages = []

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self.messages.append((chat_id, role, content))


class DispatcherStub:
    def __init__(self) -> None:
        self.dispatched_run_ids = []

    def dispatch_run(self, run_id: str, on_finished=None):
        self.dispatched_run_ids.append(run_id)

        @dataclass(slots=True)
        class Result:
            run_id: str
            status: str = "queued"

        return Result(run_id=run_id)


class WorkflowServiceStub:
    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        suffix = f"\nfeedback:{prior_feedback}" if prior_feedback else ""
        return f"plan for {prompt}{suffix}"


@dataclass(slots=True)
class WorkflowControlConfigStub:
    require_confirmation: bool


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlConfigStub


@pytest.mark.asyncio
async def test_execute_waits_for_approval_when_confirmation_required() -> None:
    repository = InMemoryRunRepository()
    dispatcher = DispatcherStub()
    use_case = SubmitPromptUseCase(
        repository,
        ContextServiceStub(),
        dispatcher,
        WorkflowServiceStub(),
        SettingsStub(WorkflowControlConfigStub(require_confirmation=True)),
    )

    result = await use_case.execute(
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        prompt="build feature",
    )

    assert result.status == RunStatus.AWAITING_CONFIRMATION.value
    assert result.plan_text == "plan for build feature"
    assert dispatcher.dispatched_run_ids == []


@pytest.mark.asyncio
async def test_execute_auto_dispatches_when_confirmation_disabled() -> None:
    repository = InMemoryRunRepository()
    dispatcher = DispatcherStub()
    use_case = SubmitPromptUseCase(
        repository,
        ContextServiceStub(),
        dispatcher,
        WorkflowServiceStub(),
        SettingsStub(WorkflowControlConfigStub(require_confirmation=False)),
    )

    result = await use_case.execute(
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        prompt="build feature",
    )

    assert result.status == RunStatus.QUEUED.value
    assert len(dispatcher.dispatched_run_ids) == 1
    saved_run = repository.get(dispatcher.dispatched_run_ids[0])
    assert saved_run is not None
    assert saved_run.approved is True
    assert saved_run.current_stage == "queued_for_execution"


def test_approve_is_idempotent_for_completed_run() -> None:
    repository = InMemoryRunRepository()
    dispatcher = DispatcherStub()
    use_case = SubmitPromptUseCase(
        repository,
        ContextServiceStub(),
        dispatcher,
        WorkflowServiceStub(),
        SettingsStub(WorkflowControlConfigStub(require_confirmation=True)),
    )
    run = next(iter(repository.runs.values()), None)
    if run is None:
        from datetime import UTC, datetime
        from mergemate.domain.runs.entities import AgentRun

        now = datetime.now(UTC)
        run = AgentRun(
            run_id="run-1",
            chat_id=1,
            user_id=2,
            agent_name="coder",
            workflow="generate_code",
            status=RunStatus.COMPLETED,
            current_stage="completed",
            prompt="done",
            estimate_seconds=10,
            plan_text="plan",
            design_text=None,
            test_text=None,
            review_text=None,
            review_iterations=1,
            approved=True,
            result_text="ok",
            error_text=None,
            created_at=now,
            updated_at=now,
        )
        repository.create(run)

    result = use_case.approve("run-1")

    assert result is not None
    assert result.dispatched is False
    assert result.status == RunStatus.COMPLETED.value
    assert dispatcher.dispatched_run_ids == []


@pytest.mark.asyncio
async def test_revise_plan_for_chat_rejects_other_chat() -> None:
    repository = InMemoryRunRepository()
    dispatcher = DispatcherStub()
    use_case = SubmitPromptUseCase(
        repository,
        ContextServiceStub(),
        dispatcher,
        WorkflowServiceStub(),
        SettingsStub(WorkflowControlConfigStub(require_confirmation=True)),
    )
    await use_case.execute(
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        prompt="build feature",
    )
    run_id = next(iter(repository.runs))

    result = await use_case.revise_plan_for_chat(run_id, "new feedback", chat_id=999)

    assert result is None


def test_approve_rejects_run_from_other_chat() -> None:
    repository = InMemoryRunRepository()
    dispatcher = DispatcherStub()
    use_case = SubmitPromptUseCase(
        repository,
        ContextServiceStub(),
        dispatcher,
        WorkflowServiceStub(),
        SettingsStub(WorkflowControlConfigStub(require_confirmation=True)),
    )
    from datetime import UTC, datetime
    from mergemate.domain.runs.entities import AgentRun

    now = datetime.now(UTC)
    repository.create(
        AgentRun(
            run_id="run-2",
            chat_id=1,
            user_id=2,
            agent_name="coder",
            workflow="generate_code",
            status=RunStatus.AWAITING_CONFIRMATION,
            current_stage="awaiting_user_confirmation",
            prompt="pending",
            estimate_seconds=10,
            plan_text="plan",
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
    )

    result = use_case.approve("run-2", chat_id=999)

    assert result is None
    assert dispatcher.dispatched_run_ids == []
