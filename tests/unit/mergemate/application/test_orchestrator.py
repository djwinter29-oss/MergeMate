from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from mergemate.application.execution_plan import DirectExecutionPlan, MultiStageExecutionPlan
from mergemate.application.orchestrator import AgentOrchestrator
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus


@dataclass(slots=True)
class WorkflowControlStub:
    max_review_iterations: int = 3


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)
    agents: dict[str, object] = field(
        default_factory=lambda: {
            "planner": SimpleNamespace(workflow="planning"),
            "architect": SimpleNamespace(workflow="design"),
            "coder": SimpleNamespace(workflow="generate_code"),
            "debugger": SimpleNamespace(workflow="debug_code"),
            "tester": SimpleNamespace(workflow="testing"),
            "reviewer": SimpleNamespace(workflow="review"),
        }
    )

    def resolve_agent_name_for_workflow(
        self,
        workflow: str,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        if preferred_agent_name is not None:
            agent = self.agents.get(preferred_agent_name)
            if agent is not None and agent.workflow == workflow:
                return preferred_agent_name
        for agent_name, agent in self.agents.items():
            if agent.workflow == workflow:
                return agent_name
        raise ValueError(workflow)


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
    def __init__(self, recent_messages=None) -> None:
        self.appended_messages = []
        self.recent_messages = recent_messages or []

    def load_recent_messages(self, chat_id: int):
        return list(self.recent_messages)

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


class ToolServiceStub:
    def __init__(self, runtime_context: str = "") -> None:
        self.runtime_context = runtime_context
        self.calls = []

    def build_runtime_tool_context(self, run_id: str, agent_name: str, *, resume_stage: str = "retrieve_context") -> str:
        self.calls.append((run_id, agent_name, resume_stage))
        return self.runtime_context


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
    def __init__(self, *, high_concerns: bool = False, max_iterations: int = 3) -> None:
        self.generate_code_calls = 0
        self.direct_calls = []
        self.high_concerns = high_concerns
        self.max_iterations = max_iterations
        self.design_calls = []
        self.test_calls = []
        self.review_calls = []
        self.replan_calls = []

    @staticmethod
    def uses_multi_stage_delivery(workflow: str) -> bool:
        return workflow == "generate_code"

    def build_execution_plan(self, workflow: str, *, agent_name: str):
        if workflow == "generate_code":
            return MultiStageExecutionPlan(agent_name=agent_name, max_iterations=self.max_iterations)
        return DirectExecutionPlan(agent_name=agent_name)

    async def create_design(self, plan_text: str, context_text: str) -> str:
        self.design_calls.append((plan_text, context_text))
        return "design"

    async def generate_code(
        self,
        plan_text: str,
        design_text: str,
        context_text: str,
        *,
        agent_name: str | None = None,
    ) -> str:
        self.generate_code_calls += 1
        return "implementation"

    async def generate_tests(self, plan_text: str, design_text: str, implementation_text: str) -> str:
        self.test_calls.append((plan_text, design_text, implementation_text))
        return "tests"

    async def review(self, plan_text: str, design_text: str, implementation_text: str, test_text: str) -> str:
        self.review_calls.append((plan_text, design_text, implementation_text, test_text))
        return "HIGH_CONCERNS: yes" if self.high_concerns else "HIGH_CONCERNS: no"

    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        self.replan_calls.append((prompt, prior_feedback))
        return "replanned"

    async def execute_direct(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.direct_calls.append((agent_name, system_prompt, user_prompt))
        return "direct result"

    @staticmethod
    def has_high_concerns(review_text: str) -> bool:
        return review_text.startswith("HIGH_CONCERNS: yes")


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
        tool_service=ToolServiceStub(),
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
        tool_service=ToolServiceStub(),
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
        tool_service=ToolServiceStub(),
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


@pytest.mark.asyncio
async def test_process_run_raises_when_run_is_missing() -> None:
    orchestrator = AgentOrchestrator(
        run_repository=RunRepositoryStub(_build_run()),
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=ToolServiceStub(),
        workflow_service=WorkflowServiceStub(),
        llm_gateway=None,
        settings=SettingsStub(),
    )

    with pytest.raises(ValueError, match="was not found"):
        await orchestrator.process_run("missing")


@pytest.mark.asyncio
async def test_process_run_returns_early_for_cancelled_or_unapproved_runs() -> None:
    cancelled_run = _build_run()
    cancelled_run.status = RunStatus.CANCELLED
    cancelled_repository = RunRepositoryStub(cancelled_run)
    cancelled = await AgentOrchestrator(
        run_repository=cancelled_repository,
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=ToolServiceStub(),
        workflow_service=WorkflowServiceStub(),
        llm_gateway=None,
        settings=SettingsStub(),
    ).process_run("run-1")
    assert cancelled.status == RunStatus.CANCELLED

    unapproved_run = _build_run()
    unapproved_run.approved = False
    unapproved = await AgentOrchestrator(
        run_repository=RunRepositoryStub(unapproved_run),
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=ToolServiceStub(),
        workflow_service=WorkflowServiceStub(),
        llm_gateway=None,
        settings=SettingsStub(),
    ).process_run("run-1")
    assert unapproved.approved is False


@pytest.mark.asyncio
async def test_process_run_trims_latest_duplicate_prompt_and_replans_on_review_concerns() -> None:
    repository = RunRepositoryStub(_build_run())
    context_service = ContextServiceStub(
        recent_messages=[
            {"role": "assistant", "content": "older"},
            {"role": "user", "content": "build a feature"},
        ]
    )
    workflow_service = WorkflowServiceStub(high_concerns=True, max_iterations=2)
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=context_service,
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=ToolServiceStub(),
        workflow_service=workflow_service,
        llm_gateway=None,
        settings=SettingsStub(WorkflowControlStub(max_review_iterations=2)),
    )

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.status == RunStatus.COMPLETED
    assert workflow_service.design_calls[0] == ("approved plan", "context")
    assert workflow_service.replan_calls == [("build a feature", "HIGH_CONCERNS: yes")]
    assert repository.run.plan_text == "replanned"
    assert repository.run.review_iterations == 2


@pytest.mark.asyncio
async def test_process_run_includes_runtime_tool_context_for_direct_plans() -> None:
    repository = RunRepositoryStub(_build_run(workflow="debug_code", agent_name="debugger"))
    tool_service = ToolServiceStub(runtime_context="tool output")
    workflow_service = WorkflowServiceStub()
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=tool_service,
        workflow_service=workflow_service,
        llm_gateway=None,
        settings=SettingsStub(),
    )

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.status == RunStatus.COMPLETED
    assert workflow_service.direct_calls == [("debugger", "system", "context\n\nRuntime tool context:\ntool output")]
    assert tool_service.calls == [("run-1", "debugger", "retrieve_context")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cancel_sequence", "expected_stage"),
    [
        ([True], "retrieve_context"),
        ([False, False, True], "implementation"),
        ([False, False, False, True], "testing"),
        ([False, False, False, False, True], "review"),
    ],
)
async def test_process_run_returns_when_cancelled_at_intermediate_checkpoints(cancel_sequence, expected_stage) -> None:
    repository = RunRepositoryStub(_build_run())
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=ToolServiceStub(),
        workflow_service=WorkflowServiceStub(),
        llm_gateway=None,
        settings=SettingsStub(),
    )

    sequence = iter(cancel_sequence)
    orchestrator._is_cancelled = lambda run_id: next(sequence, False)

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.current_stage == expected_stage


@pytest.mark.asyncio
async def test_process_run_returns_when_cancelled_after_replanning() -> None:
    repository = RunRepositoryStub(_build_run())
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=ToolServiceStub(),
        workflow_service=WorkflowServiceStub(high_concerns=True, max_iterations=2),
        llm_gateway=None,
        settings=SettingsStub(WorkflowControlStub(max_review_iterations=2)),
    )

    sequence = iter([False, False, False, False, False, True])
    orchestrator._is_cancelled = lambda run_id: next(sequence, False)

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.current_stage == "internal_replanning"


@pytest.mark.asyncio
async def test_process_run_returns_latest_cancelled_run_after_loop() -> None:
    repository = RunRepositoryStub(_build_run())

    class CancellingWorkflowService(WorkflowServiceStub):
        async def review(self, plan_text: str, design_text: str, implementation_text: str, test_text: str) -> str:
            repository.run.status = RunStatus.CANCELLED
            return await super().review(plan_text, design_text, implementation_text, test_text)

    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=ToolServiceStub(),
        workflow_service=CancellingWorkflowService(),
        llm_gateway=None,
        settings=SettingsStub(),
    )
    orchestrator._is_cancelled = lambda run_id: False

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert run.status == RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_process_run_appends_runtime_tool_context_to_execution_context() -> None:
    repository = RunRepositoryStub(_build_run(workflow="debug_code", agent_name="debugger"))
    tool_service = ToolServiceStub("Enabled runtime tools:\n- git_repository\n\ngit_repository (ok):\nmain")
    workflow_service = WorkflowServiceStub()
    orchestrator = AgentOrchestrator(
        run_repository=repository,
        context_service=ContextServiceStub(),
        documentation_service=DocumentationServiceStub(),
        learning_service=LearningServiceStub(),
        prompt_service=PromptServiceStub(),
        tool_service=tool_service,
        workflow_service=workflow_service,
        llm_gateway=None,
        settings=SettingsStub(),
    )

    run = await orchestrator.process_run("run-1")

    assert run is not None
    assert tool_service.calls == [("run-1", "debugger", "retrieve_context")]
    assert workflow_service.direct_calls == [
        (
            "debugger",
            "system",
            "context\n\nRuntime tool context:\nEnabled runtime tools:\n- git_repository\n\ngit_repository (ok):\nmain",
        )
    ]