"""Integration tests for execution plans using an in-memory mock LLM.

Tests the MultiStageExecutionPlan.execute() and DirectExecutionPlan.execute()
methods through the real WorkflowService with a mock LLM gateway, verifying
the full lifecycle: context assembly, artifact persistence, cancellation
handling, and iteration/feedback loops.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mergemate.application.execution_plan import (
    DirectExecutionPlan,
    ExecutionContext,
    ExecutionRuntime,
    MultiStageExecutionPlan,
    OrchestratorDependencies,
)
from mergemate.application.services.workflow_service import WorkflowService
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.shared import RunStage, RunStatus
from mergemate.domain.shared import WorkflowName
from mergemate.domain.workflows.stage import get_workflow_definitions


# Shared workflow definition for multi-stage tests
_GENERATE_CODE_DEF = get_workflow_definitions()[WorkflowName.GENERATE_CODE]


# ---------------------------------------------------------------------------
# In-memory mock LLM -- records prompts and returns deterministic responses
# ---------------------------------------------------------------------------

class InMemoryMockLLM:
    """Mock LLM that returns deterministic responses based on the stage name.

    Records every call for assertion in tests.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self._response_index = 0

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"agent": agent_name, "system": system_prompt, "user": user_prompt})
        self._response_index += 1
        return f"MockLLM response #{self._response_index}"


class InMemoryMockLLMWithReview(InMemoryMockLLM):
    """Like InMemoryMockLLM but returns HIGH_CONCERNS: yes on the Nth review."""

    def __init__(self, high_concerns_on_review: int = 1) -> None:
        super().__init__()
        self._review_count = 0
        self._high_concerns_on_review = high_concerns_on_review

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        await super().generate(agent_name, system_prompt, user_prompt)
        if "review agent" in system_prompt.lower():
            self._review_count += 1
            if self._review_count <= self._high_concerns_on_review:
                return "HIGH_CONCERNS: yes\nReview iteration %d: needs work" % self._review_count
            return "HIGH_CONCERNS: no\nLooks good."
        return f"MockLLM stage response #{self._review_count + 1}"


# ---------------------------------------------------------------------------
# Stubs for ExecutionRuntime dependencies
# ---------------------------------------------------------------------------

class RunRepositorySpy:
    """Stores all mutations for verification."""

    def __init__(self, run: AgentRun) -> None:
        self.run = run
        self.save_artifacts_calls: list[dict[str, Any]] = []
        self.update_status_calls: list[dict[str, Any]] = []
        self.update_plan_calls: list[dict[str, Any]] = []
        self._get_count = 0

    def get(self, run_id: str) -> AgentRun | None:
        if self.run.run_id != run_id:
            return None
        self._get_count += 1
        return self.run

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
        self.save_artifacts_calls.append({
            "run_id": run_id,
            "current_stage": current_stage,
            "design_text": design_text,
            "test_text": test_text,
            "review_text": review_text,
            "result_text": result_text,
            "review_iterations": review_iterations,
        })
        if current_stage is not None:
            self.run.current_stage = current_stage
        if design_text is not None:
            self.run.design_text = design_text
        if test_text is not None:
            self.run.test_text = test_text
        if review_text is not None:
            self.run.review_text = review_text
        if result_text is not None:
            self.run.result_text = result_text
        if review_iterations is not None:
            self.run.review_iterations = review_iterations
        return self.run

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        expected_current_status: RunStatus | None = None,
        current_stage: str | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> AgentRun | None:
        self.update_status_calls.append({
            "run_id": run_id,
            "status": status,
            "current_stage": current_stage,
        })
        self.run.status = status
        if current_stage is not None:
            self.run.current_stage = current_stage
        if result_text is not None:
            self.run.result_text = result_text
        if error_text is not None:
            self.run.error_text = error_text
        return self.run

    def update_plan(
        self,
        run_id: str,
        plan_text: str,
        prompt: str | None = None,
        *,
        current_stage: str | None = None,
    ) -> AgentRun | None:
        self.update_plan_calls.append({
            "run_id": run_id,
            "plan_text": plan_text,
            "current_stage": current_stage,
        })
        self.run.plan_text = plan_text
        if current_stage is not None:
            self.run.current_stage = current_stage
        return self.run


class ContextServiceSpy:
    def __init__(self) -> None:
        self.appended: list[tuple[int, str, str]] = []

    def load_recent_messages(self, chat_id: int) -> list[dict[str, str]]:
        return []

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self.appended.append((chat_id, role, content))


class DocumentationServiceSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write_architecture_design(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
    ) -> Path:
        self.calls.append({
            "kind": "architecture",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "design_text": design_text,
        })
        return Path(f"/tmp/docs/architecture/{plan_text[:10].replace(' ', '-')}.md")

    def write_test_plan(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
        test_text: str,
    ) -> Path:
        self.calls.append({
            "kind": "testing",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "design_text": design_text,
            "test_text": test_text,
        })
        return Path(f"/tmp/docs/testing/{plan_text[:10].replace(' ', '-')}-test-plan.md")

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
    ) -> Path:
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
        return Path(f"/tmp/docs/reviews/{plan_text[:10].replace(' ', '-')}-review-report.md")


class LearningServiceSpy:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def load_recent_learnings(self, chat_id: int) -> list[dict[str, str]]:
        return []

    def remember_success(self, **payload: Any) -> None:
        self.saved.append(payload)


class PlanningServiceSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        self.calls.append((prompt, prior_feedback))
        return f"Revised plan based on: {prompt[:30]}..."


# ---------------------------------------------------------------------------
# Settings and helpers
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WorkflowControlStub:
    max_review_iterations: int = 3


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)

    def resolve_agent_name_for_workflow(
        self,
        workflow: str,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        agents = {
            "planning": "planner",
            "design": "architect",
            "generate_code": "coder",
            "testing": "tester",
            "review": "reviewer",
        }
        return preferred_agent_name or agents.get(workflow, "coder")


def _make_run(
    *,
    run_id: str = "run-exec-plan-1",
    chat_id: int = 1001,
    workflow: str = "generate_code",
    agent_name: str = "coder",
    status: RunStatus = RunStatus.QUEUED,
    plan_text: str = "Build a login system with OAuth",
) -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        run_id=run_id,
        chat_id=chat_id,
        user_id=42,
        agent_name=agent_name,
        workflow=workflow,
        status=status,
        current_stage=RunStage.RETRIEVE_CONTEXT,
        prompt="build login system",
        estimate_seconds=60,
        plan_text=plan_text,
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


def _make_multistage_plan(agent_name: str = "coder", max_iterations: int = 3) -> MultiStageExecutionPlan:
    """Convenience: build a MultiStageExecutionPlan for the generate_code workflow."""
    return MultiStageExecutionPlan(
        agent_name=agent_name,
        max_iterations=max_iterations,
        workflow_definition=_GENERATE_CODE_DEF,
    )


def _make_deps(
    llm_gateway: Any,
    *,
    repository=None,
    context_service=None,
    documentation_service=None,
    learning_service=None,
    planning_service=None,
    workflow_service=None,
    settings=None,
) -> OrchestratorDependencies:
    """Build an OrchestratorDependencies for plan integration tests."""
    return OrchestratorDependencies(
        run_repository=repository or RunRepositorySpy(_make_run()),
        context_service=context_service or ContextServiceSpy(),
        documentation_service=documentation_service or DocumentationServiceSpy(),
        learning_service=learning_service or LearningServiceSpy(),
        planning_service=planning_service or PlanningServiceSpy(),
        prompt_service=None,
        tool_service=None,
        workflow_service=workflow_service or WorkflowService(llm_gateway, settings or SettingsStub()),
        llm_gateway=llm_gateway,
        settings=settings or SettingsStub(),
    )


def _make_runtime_from_deps(
    deps: OrchestratorDependencies,
    *,
    is_cancelled=lambda _run_id: False,
) -> ExecutionRuntime:
    """Build an ExecutionRuntime from a deps object (integration test helper)."""
    return ExecutionRuntime(deps=deps, is_cancelled=is_cancelled)


# ---------------------------------------------------------------------------
# Tests: MultiStageExecutionPlan.execute()
# ---------------------------------------------------------------------------

class TestMultiStageExecutionPlanIntegration:
    """Integration tests for MultiStageExecutionPlan.execute().

    Tests exercise the real WorkflowService with a mock LLM, verifying:
    - All 5 stages run in order (design, implementation, testing, review, replan)
    - Artifacts (design, test, review docs) are written
    - Completion status and result_text are set
    - Cancellation stops execution mid-pipeline
    - Replanning loop runs on high concerns
    - Context is appended and learning is recorded
    """

    @pytest.mark.asyncio
    async def test_execute_completes_all_stages(self) -> None:
        """Verify all 5 stages execute and the run completes successfully."""
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run()
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = _make_multistage_plan()
        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=lambda _: False,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="You are a coding assistant.",
            context_text="User wants a login feature.",
        )

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert result.status == RunStatus.COMPLETED
        assert result.current_stage == RunStage.COMPLETED

        # All 5 stages should have been called: design, impl, test, review
        # (no replanning since review says "no high concerns")
        assert len(mock_llm.calls) == 4, (
            f"Expected 4 LLM calls (design, code, test, review), got {len(mock_llm.calls)}"
        )

        # All 3 document artifacts should be written
        assert len(docs.calls) == 3
        assert docs.calls[0]["kind"] == "architecture"
        assert docs.calls[1]["kind"] == "testing"
        assert docs.calls[2]["kind"] == "review"

        # Context message should have been appended
        assert len(context.appended) == 1
        assert context.appended[0][1] == "assistant"
        assert "Approved plan:" in context.appended[0][2]

        # Learning should have been recorded
        assert len(learning.saved) == 1
        assert learning.saved[0]["workflow"] == "generate_code"

        # Status should have been updated to COMPLETED
        status_calls = repo.update_status_calls
        assert any(c["status"] == RunStatus.COMPLETED for c in status_calls)

        # save_artifacts should have been called for design, implementation,
        # testing, and review stages
        saved_stages = {c["current_stage"] for c in repo.save_artifacts_calls if c["current_stage"]}
        assert RunStage.DESIGN in saved_stages
        assert RunStage.IMPLEMENTATION in saved_stages
        assert RunStage.TESTING in saved_stages
        assert RunStage.REVIEW in saved_stages

    @pytest.mark.asyncio
    async def test_execute_replans_on_high_concerns(self) -> None:
        """When the review returns HIGH_CONCERNS: yes, the plan should replan
        and iterate through the design/code/test/review cycle again.
        """
        mock_llm = InMemoryMockLLMWithReview(high_concerns_on_review=1)
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run()
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = _make_multistage_plan()
        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=lambda _: False,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="You are a coding assistant.",
            context_text="User wants a login feature.",
        )

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert result.status == RunStatus.COMPLETED

        # 2 iterations: one with HIGH_CONCERNS, one without
        # Per iteration: design + code + test + review = 4 LLM calls
        # So 8 calls for 2 iterations
        assert len(mock_llm.calls) == 8, (
            f"Expected 8 LLM calls (2 iterations x 4 stages), got {len(mock_llm.calls)}"
        )

        # Planning service should have been called once for replanning
        assert len(planning.calls) == 1
        assert planning.calls[0][1] is not None  # prior_feedback should be set

        # Plan should have been updated via repository
        assert len(repo.update_plan_calls) == 1

        # 2 iterations of artifacts per stage should be written
        # (iteration 1: architecture, testing, review; iteration 2: same)
        assert len(docs.calls) == 6

    @pytest.mark.asyncio
    async def test_execute_limited_iterations(self) -> None:
        """With max_iterations=1 and HIGH_CONCERNS: yes, the plan should
        complete without replanning (one iteration only).
        """
        mock_llm = InMemoryMockLLMWithReview(high_concerns_on_review=5)
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run()
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = _make_multistage_plan(max_iterations=1)
        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(workflow_control=WorkflowControlStub(max_review_iterations=1)),
            is_cancelled=lambda _: False,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="You are a coding assistant.",
            context_text="User wants a login feature.",
        )

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert result.status == RunStatus.COMPLETED

        # Only 1 iteration: 4 LLM calls
        assert len(mock_llm.calls) == 4

        # No replanning occurred
        assert len(planning.calls) == 0

    @pytest.mark.asyncio
    async def test_execute_stops_on_cancellation_before_design(self) -> None:
        """If cancelled before the design stage, the plan should abort
        immediately without making any LLM calls.
        """
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run()
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = _make_multistage_plan()
        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=lambda _: True,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="You are a coding assistant.",
            context_text="User wants a login feature.",
        )

        result = await plan.execute(runtime, execution)

        # Should return early with the run as-is (no LLM calls made)
        assert result is not None
        assert len(mock_llm.calls) == 0
        assert len(context.appended) == 0
        assert len(learning.saved) == 0

    @pytest.mark.asyncio
    async def test_execute_cancellation_after_design_stops_pipeline(self) -> None:
        """If cancelled after the design stage (checks_cancellation_after),
        the plan should stop before implementation.
        """
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run()
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = _make_multistage_plan()
        call_count = 0

        def _is_cancelled(_run_id: str) -> bool:
            nonlocal call_count
            call_count += 1
            return call_count >= 2

        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=_is_cancelled,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="You are a coding assistant.",
            context_text="User wants a login feature.",
        )

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert len(mock_llm.calls) == 1

    @pytest.mark.asyncio
    async def test_execute_returns_cancelled_run_if_cancelled_during_iteration(self) -> None:
        """If the run is cancelled mid-iteration (status changed externally),
        the plan should detect it and return the cancelled run.
        """
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run()
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = _make_multistage_plan()
        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=lambda _: False,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="You are a coding assistant.",
            context_text="User wants a login feature.",
        )

        class CancellingWorkflowService(WorkflowService):
            async def generate_tests(
                self,
                plan_text: str,
                design_text: str,
                implementation_text: str,
            ) -> str:
                run.status = RunStatus.CANCELLED
                return await super().generate_tests(plan_text, design_text, implementation_text)

        runtime.workflow_service = CancellingWorkflowService(llm_gateway, SettingsStub())

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert result.status == RunStatus.CANCELLED


# ---------------------------------------------------------------------------
# Tests: DirectExecutionPlan.execute()
# ---------------------------------------------------------------------------

class TestDirectExecutionPlanIntegration:
    """Integration tests for DirectExecutionPlan.execute().

    The direct plan has a single stage that delegates to workflow_service.execute_direct().
    """

    @pytest.mark.asyncio
    async def test_direct_execution_completes(self) -> None:
        """A direct execution plan should complete the run and persist results."""
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run(workflow="debug_code", agent_name="debugger")
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = DirectExecutionPlan(agent_name="debugger")
        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=lambda _: False,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="Debug the following code.",
            context_text="Code: x = 1 / 0",
        )

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert result.status == RunStatus.COMPLETED
        assert result.result_text is not None

        # 1 LLM call for the direct execution
        assert len(mock_llm.calls) == 1
        assert "Debug the following code." in mock_llm.calls[0]["system"]

        # Context message appended
        assert len(context.appended) == 1
        assert context.appended[0][1] == "assistant"

        # Learning recorded
        assert len(learning.saved) == 1

    @pytest.mark.asyncio
    async def test_direct_execution_cancelled_before(self) -> None:
        """If cancelled before execution, no LLM call should be made."""
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run(workflow="debug_code", agent_name="debugger")
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = DirectExecutionPlan(agent_name="debugger")
        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=lambda _: True,
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="Debug the following code.",
            context_text="Code: x = 1 / 0",
        )

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert len(mock_llm.calls) == 0
        assert len(context.appended) == 0
        assert len(learning.saved) == 0

    @pytest.mark.asyncio
    async def test_direct_execution_cancelled_after_call(self) -> None:
        """If cancelled after the LLM call but before persistence, no
        learning or context append should happen.
        """
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        run = _make_run(workflow="debug_code", agent_name="debugger")
        repo = RunRepositorySpy(run)
        context = ContextServiceSpy()
        docs = DocumentationServiceSpy()
        learning = LearningServiceSpy()
        planning = PlanningServiceSpy()
        workflow_service = WorkflowService(llm_gateway, SettingsStub())

        plan = DirectExecutionPlan(agent_name="debugger")
        sequence = iter([False, True])

        runtime = ExecutionRuntime(
            run_repository=repo,
            context_service=context,
            documentation_service=docs,
            learning_service=learning,
            planning_service=planning,
            workflow_service=workflow_service,
            settings=SettingsStub(),
            is_cancelled=lambda _: next(sequence, False),
        )
        execution = ExecutionContext(
            run=run,
            system_prompt="Debug the following code.",
            context_text="Code: x = 1 / 0",
        )

        result = await plan.execute(runtime, execution)

        assert result is not None
        assert len(mock_llm.calls) == 1
        assert len(context.appended) == 0
        assert len(learning.saved) == 0


# ---------------------------------------------------------------------------
# Tests: Execution plan construction via WorkflowService
# ---------------------------------------------------------------------------

class TestWorkflowServicePlanConstruction:
    """Verify that WorkflowService.build_execution_plan returns the correct
    plan type based on the workflow.
    """

    @pytest.mark.asyncio
    async def test_generate_code_uses_multi_stage(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        service = WorkflowService(llm_gateway, SettingsStub())

        plan = service.build_execution_plan("generate_code", agent_name="coder")
        assert isinstance(plan, MultiStageExecutionPlan)
        assert plan.requires_tool_context is True

    @pytest.mark.asyncio
    async def test_debug_code_uses_direct(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        service = WorkflowService(llm_gateway, SettingsStub())

        plan = service.build_execution_plan("debug_code", agent_name="debugger")
        assert isinstance(plan, DirectExecutionPlan)
        assert plan.requires_tool_context is True

    @pytest.mark.asyncio
    async def test_explain_code_uses_direct(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        service = WorkflowService(llm_gateway, SettingsStub())

        plan = service.build_execution_plan("explain_code", agent_name="explainer")
        assert isinstance(plan, DirectExecutionPlan)

    @pytest.mark.asyncio
    async def test_max_iterations_from_settings(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        settings = SettingsStub(workflow_control=WorkflowControlStub(max_review_iterations=7))
        service = WorkflowService(llm_gateway, settings)

        plan = service.build_execution_plan("generate_code", agent_name="coder")
        assert isinstance(plan, MultiStageExecutionPlan)
        assert plan._max_iterations == 7


# ---------------------------------------------------------------------------
# Tests: has_high_concerns and WorkflowService method contracts
# ---------------------------------------------------------------------------

class TestWorkflowServiceStageMethods:
    """Verifies the WorkflowService stage methods route correctly through
    the mock LLM.
    """

    @pytest.mark.asyncio
    async def test_create_design_forwards_prompt(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        service = WorkflowService(llm_gateway, SettingsStub())

        result = await service.create_design(plan_text="plan", context_text="ctx")

        assert "MockLLM" in result
        assert len(mock_llm.calls) == 1
        assert "architect agent" in mock_llm.calls[0]["system"]
        assert "plan" in mock_llm.calls[0]["user"]

    @pytest.mark.asyncio
    async def test_generate_code_forwards_prompt(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        service = WorkflowService(llm_gateway, SettingsStub())

        result = await service.generate_code(
            plan_text="plan",
            design_text="design",
            context_text="ctx",
            agent_name="coder",
        )

        assert "MockLLM" in result
        assert len(mock_llm.calls) == 1
        assert "coding agent" in mock_llm.calls[0]["system"]

    @pytest.mark.asyncio
    async def test_generate_tests_forwards_prompt(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        service = WorkflowService(llm_gateway, SettingsStub())

        result = await service.generate_tests(
            plan_text="plan",
            design_text="design",
            implementation_text="impl",
        )

        assert "MockLLM" in result
        assert len(mock_llm.calls) == 1
        assert "test agent" in mock_llm.calls[0]["system"]

    @pytest.mark.asyncio
    async def test_review_forwards_prompt(self) -> None:
        mock_llm = InMemoryMockLLM()
        llm_gateway = SimpleNamespace(generate=mock_llm.generate)
        service = WorkflowService(llm_gateway, SettingsStub())

        result = await service.review(
            plan_text="plan",
            design_text="design",
            implementation_text="impl",
            test_text="tests",
        )

        assert "MockLLM" in result
        assert len(mock_llm.calls) == 1
        assert "review agent" in mock_llm.calls[0]["system"]

    def test_has_high_concerns_yes(self) -> None:
        assert WorkflowService.has_high_concerns("HIGH_CONCERNS: yes\nNeeds work.") is True

    def test_has_high_concerns_no(self) -> None:
        assert WorkflowService.has_high_concerns("HIGH_CONCERNS: no\nLooks good.") is False

    def test_has_high_concerns_empty(self) -> None:
        assert WorkflowService.has_high_concerns("") is False

    def test_has_high_concerns_leading_whitespace(self) -> None:
        assert WorkflowService.has_high_concerns("  HIGH_CONCERNS: yes") is True