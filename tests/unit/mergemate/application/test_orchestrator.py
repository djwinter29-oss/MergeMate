from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from mergemate.application.orchestrator import AgentOrchestrator
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus


@dataclass(slots=True)
class WorkflowControlStub:
    max_review_iterations: int = 3


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)


class RunRepositoryStub:
    def __init__(self, run: AgentRun, *, cancel_on_design: bool = False) -> None:
        self.run = run
        self.cancel_on_design = cancel_on_design

    def get(self, run_id: str) -> AgentRun | None:
        if self.run.run_id != run_id:
            return None
        return self.run

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        current_stage: str | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> AgentRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        run.status = status
        if current_stage is not None:
            run.current_stage = current_stage
        if result_text is not None:
            run.result_text = result_text
        if error_text is not None:
            run.error_text = error_text
        return run

    def save_artifacts(
        self,
        run_id: str,
        *,
        current_stage: str | None = None,
        design_text: str | None = None,
        test_text: str | None = None,
        review_text: str | None = None,
        result_text: str | None = None,
        review_iterations: int | None = None,
    ) -> AgentRun | None:
        run = self.get(run_id)
        if run is None:
            return None
        if current_stage is not None:
            run.current_stage = current_stage
        if design_text is not None:
            run.design_text = design_text
            if self.cancel_on_design:
                run.status = RunStatus.CANCELLED
        if test_text is not None:
            run.test_text = test_text
        if review_text is not None:
            run.review_text = review_text
        if result_text is not None:
            run.result_text = result_text
        if review_iterations is not None:
            run.review_iterations = review_iterations
        return run

    def update_plan(self, run_id: str, plan_text: str, prompt: str | None = None, *, current_stage: str | None = None):
        run = self.get(run_id)
        if run is None:
            return None
        run.plan_text = plan_text
        if prompt is not None:
            run.prompt = prompt
        if current_stage is not None:
            run.current_stage = current_stage
        return run


class ContextServiceStub:
    def __init__(self) -> None:
        self.appended_messages = []

    def load_recent_messages(self, chat_id: int):
        return []

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self.appended_messages.append((chat_id, role, content))


class LearningServiceStub:
    def __init__(self) -> None:
        self.saved = []

    def load_recent_learnings(self, chat_id: int):
        return []

    def remember_success(self, **payload) -> None:
        self.saved.append(payload)


class PromptServiceStub:
    def render(self, workflow: str, recent_messages, learned_items, prompt: str):
        return ("system", "context")


class DocumentationServiceStub:
    def __init__(self) -> None:
        self.calls = []

    def write_architecture_design(self, *, run_id: str, iteration: int, plan_text: str, design_text: str):
        self.calls.append({
            "kind": "architecture",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "design_text": design_text,
        })
        return f"docs/architecture/{plan_text.replace(' ', '-').lower()}.md"

    def write_test_plan(self, *, run_id: str, iteration: int, plan_text: str, design_text: str, test_text: str):
        self.calls.append({
            "kind": "testing",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "design_text": design_text,
            "test_text": test_text,
        })
        return f"docs/testing/{plan_text.replace(' ', '-').lower()}-test-plan.md"

    def write_review_report(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
        implementation_text: str,
        test_text: str,
        review_text: str,
    ):
        self.calls.append({
            "kind": "review",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "design_text": design_text,
            "implementation_text": implementation_text,
            "test_text": test_text,
            "review_text": review_text,
        })
        return f"docs/reviews/{plan_text.replace(' ', '-').lower()}-review-report.md"


class WorkflowServiceStub:
    def __init__(self) -> None:
        self.generate_code_calls = 0
        self.direct_calls = []

    @staticmethod
    def uses_multi_stage_delivery(workflow: str) -> bool:
        return workflow == "generate_code"

    async def create_design(self, plan_text: str, context_text: str) -> str:
        return "design"

    async def generate_code(self, plan_text: str, design_text: str, context_text: str) -> str:
        self.generate_code_calls += 1
        return "implementation"

    async def generate_tests(self, plan_text: str, design_text: str, implementation_text: str) -> str:
        return "tests"

    async def review(self, plan_text: str, design_text: str, implementation_text: str, test_text: str) -> str:
        return "HIGH_CONCERNS: no"

    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        return "replanned"

    async def execute_direct(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.direct_calls.append((agent_name, system_prompt, user_prompt))
        return "direct result"

    @staticmethod
    def has_high_concerns(review_text: str) -> bool:
        return False


def _build_run(*, workflow: str = "generate_code", agent_name: str = "coder") -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        run_id="run-1",
        chat_id=123,
        user_id=456,
        agent_name=agent_name,
        workflow=workflow,
        status=RunStatus.QUEUED,
        current_stage="queued_for_execution",
        prompt="build a feature",
        estimate_seconds=30,
        plan_text="approved plan",
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=True,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_process_run_stops_after_cancellation_between_steps() -> None:
    repository = RunRepositoryStub(_build_run(), cancel_on_design=True)
    context_service = ContextServiceStub()
    documentation_service = DocumentationServiceStub()
    learning_service = LearningServiceStub()
    workflow_service = WorkflowServiceStub()
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=context_service,
        documentation_service=documentation_service,
        learning_service=learning_service,
        prompt_service=PromptServiceStub(),
        workflow_service=workflow_service,
        llm_gateway=None,
        settings=SettingsStub(),
    )

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.status == RunStatus.CANCELLED
    assert run.current_stage == "design"
    assert workflow_service.generate_code_calls == 0
    assert context_service.appended_messages == []
    assert len(documentation_service.calls) == 1
    assert documentation_service.calls[0]["kind"] == "architecture"
    assert learning_service.saved == []


@pytest.mark.asyncio
async def test_process_run_writes_all_document_artifacts() -> None:
    repository = RunRepositoryStub(_build_run())
    context_service = ContextServiceStub()
    documentation_service = DocumentationServiceStub()
    learning_service = LearningServiceStub()
    workflow_service = WorkflowServiceStub()
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=context_service,
        documentation_service=documentation_service,
        learning_service=learning_service,
        prompt_service=PromptServiceStub(),
        workflow_service=workflow_service,
        llm_gateway=None,
        settings=SettingsStub(),
    )

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.status == RunStatus.COMPLETED
    assert [call["kind"] for call in documentation_service.calls] == ["architecture", "testing", "review"]
    assert context_service.appended_messages
    final_message = context_service.appended_messages[0][2]
    assert "Design document:" in final_message
    assert "Test plan document:" in final_message
    assert "Review report:" in final_message
    assert learning_service.saved


@pytest.mark.asyncio
async def test_process_run_executes_non_generate_workflow_directly() -> None:
    repository = RunRepositoryStub(_build_run(workflow="debug_code", agent_name="debugger"))
    context_service = ContextServiceStub()
    documentation_service = DocumentationServiceStub()
    learning_service = LearningServiceStub()
    workflow_service = WorkflowServiceStub()
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=context_service,
        documentation_service=documentation_service,
        learning_service=learning_service,
        prompt_service=PromptServiceStub(),
        workflow_service=workflow_service,
        llm_gateway=None,
        settings=SettingsStub(),
    )

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.status == RunStatus.COMPLETED
    assert workflow_service.direct_calls == [("debugger", "system", "context")]
    assert workflow_service.generate_code_calls == 0
    assert documentation_service.calls == []
    assert context_service.appended_messages == [(123, "assistant", "direct result")]
    assert learning_service.saved