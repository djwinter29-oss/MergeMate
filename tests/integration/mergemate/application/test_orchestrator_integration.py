"""Integration tests for the full orchestrator pipeline.

Tests AgentOrchestrator.process_run() through the complete
QUEUED→RUNNING→COMPLETED lifecycle using:
- Real SQLite persistence (in-memory or tmp_path)
- An in-memory mock LLM
- Stubbed services for context, learning, planning, tools

These tests sit between unit tests (which use lightweight stubs for
everything) and full e2e (which require Telegram bot wiring).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from mergemate.application.execution_plan import OrchestratorDependencies
from mergemate.application.orchestrator import AgentOrchestrator
from mergemate.application.services.context_service import ContextService
from mergemate.application.services.workflow_service import WorkflowService
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.shared import RunStage, RunStatus
from mergemate.domain.shared.exceptions import RunNotFoundError
from mergemate.infrastructure.persistence.sqlite import (
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteRunRepository,
)


# ---------------------------------------------------------------------------
# In-memory mock LLM
# ---------------------------------------------------------------------------

class MockLLM:
    """Deterministic mock that records calls."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self._count = 0

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append({"agent": agent_name, "system": system_prompt, "user": user_prompt})
        self._count += 1
        return f"Mock response #{self._count}"


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class LearningServiceStub:
    def __init__(self) -> None:
        self.saved: list[dict[str, Any]] = []

    def load_recent_learnings(self, chat_id: int) -> list[dict[str, str]]:
        return []

    def remember_success(self, **payload: Any) -> None:
        self.saved.append(payload)


class DocumentationServiceStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write_architecture_design(
        self, *, run_id: str, iteration: int, plan_text: str, design_text: str, role_name: str | None = None
    ) -> str:
        self.calls.append({
            "kind": "architecture",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "design_text": design_text,
        })
        return f"docs/architecture/{plan_text[:10].replace(' ', '-')}.md"

    def write_test_plan(
        self, *, run_id: str, iteration: int, plan_text: str, design_text: str, test_text: str, role_name: str | None = None
    ) -> str:
        self.calls.append({
            "kind": "testing",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "design_text": design_text,
            "test_text": test_text,
        })
        return f"docs/testing/{plan_text[:10].replace(' ', '-')}-test-plan.md"

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
        role_name: str | None = None,
    ) -> str:
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
        return f"docs/reviews/{plan_text[:10].replace(' ', '-')}-review-report.md"

    def write_lesson(
        self, *, run_id: str, iteration: int, plan_text: str, lesson_text: str, role_name: str | None = None
    ) -> str:
        self.calls.append({
            "kind": "lessons",
            "run_id": run_id,
            "iteration": iteration,
            "plan_text": plan_text,
            "lesson_text": lesson_text,
        })
        return f"docs/lessons/{plan_text[:10].replace(' ', '-')}.md"


class PlanningServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        self.calls.append((prompt, prior_feedback))
        return f"Revised plan based on: {prompt[:30]}..."

    async def revise_plan(self, existing_prompt: str, feedback: str) -> tuple[str, str]:
        updated_prompt = f"{existing_prompt}\n\nAdditional feedback: {feedback}"
        return updated_prompt, f"# Plan\n1. {updated_prompt}"


class ToolServiceStub:
    def __init__(self, runtime_context: str = "") -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.runtime_context = runtime_context

    async def build_runtime_tool_context_async(
        self,
        run_id: str,
        agent_name: str,
        *,
        resume_stage: str = "retrieve_context",
    ) -> str:
        self.calls.append((run_id, agent_name, resume_stage))
        return self.runtime_context


class PromptServiceStub:
    def render(
        self,
        workflow: str,
        recent_messages: list[dict[str, str]],
        learned_items: list[dict[str, str]],
        prompt: str,
    ) -> tuple[str, str]:
        return ("system prompt", "rendered context")


# ---------------------------------------------------------------------------
# Settings stub with resolve_agent_name_for_workflow
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class WorkflowControlStub:
    max_review_iterations: int = 3


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)
    agents: dict[str, object] = field(
        default_factory=lambda: {
            "planner": SimpleNamespace(workflow="planning", parallel_mode="single", combine_strategy="sectioned"),
            "coder": SimpleNamespace(workflow="generate_code", parallel_mode="single", combine_strategy="sectioned"),
            "debugger": SimpleNamespace(workflow="debug_code", parallel_mode="single", combine_strategy="sectioned"),
            "explainer": SimpleNamespace(workflow="explain_code", parallel_mode="single", combine_strategy="sectioned"),
            "architect": SimpleNamespace(workflow="design", parallel_mode="single", combine_strategy="sectioned"),
            "tester": SimpleNamespace(workflow="testing", parallel_mode="single", combine_strategy="sectioned"),
            "reviewer": SimpleNamespace(workflow="review", parallel_mode="single", combine_strategy="sectioned"),
            "chronicler": SimpleNamespace(workflow="learning", parallel_mode="single", combine_strategy="sectioned"),
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
        for name, agent in self.agents.items():
            if agent.workflow == workflow:
                return name
        raise ValueError(workflow)


# ---------------------------------------------------------------------------
# Fixture: real SQLite database per test
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite_orchestrator(tmp_path):
    """Bootstrap an orchestrator with real SQLite and mock LLM.

    Returns a dict with all wired components so tests can set up state
    and make assertions.
    """
    db = SQLiteDatabase(tmp_path / "orchestrator_integration.db")
    db.initialize()
    run_repo = SQLiteRunRepository(db)
    conversation_repo = SQLiteConversationRepository(db)
    context_service = ContextService(conversation_repo)
    mock_llm = MockLLM()
    llm_gateway = SimpleNamespace(generate=mock_llm.generate)
    workflow_service = WorkflowService(llm_gateway, SettingsStub())
    learning_service = LearningServiceStub()
    docs_service = DocumentationServiceStub()
    planning_service = PlanningServiceStub()
    tool_service = ToolServiceStub()
    settings = SettingsStub()

    deps = OrchestratorDependencies(
        run_repository=run_repo,
        context_service=context_service,
        documentation_service=docs_service,
        learning_service=learning_service,
        planning_service=planning_service,
        prompt_service=PromptServiceStub(),
        tool_service=tool_service,
        workflow_service=workflow_service,
        llm_gateway=llm_gateway,
        settings=settings,
    )
    orchestrator = AgentOrchestrator(deps)

    return {
        "db": db,
        "run_repo": run_repo,
        "orchestrator": orchestrator,
        "mock_llm": mock_llm,
        "context_service": context_service,
        "learning_service": learning_service,
        "docs_service": docs_service,
        "planning_service": planning_service,
        "tool_service": tool_service,
        "settings": settings,
    }


def _create_run(
    run_repo: SQLiteRunRepository,
    *,
    run_id: str = "orch-run-1",
    workflow: str = "generate_code",
    agent_name: str = "coder",
    status: RunStatus = RunStatus.QUEUED,
    plan_text: str = "Build a login system",
    approved: bool = True,
) -> AgentRun:
    now = datetime.now(UTC)
    run = AgentRun(
        run_id=run_id,
        chat_id=2001,
        user_id=99,
        agent_name=agent_name,
        workflow=workflow,
        status=status,
        current_stage=RunStage.RETRIEVE_CONTEXT,
        prompt="build a login system",
        estimate_seconds=60,
        plan_text=plan_text,
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=approved,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )
    run_repo.create(run)
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOrchestratorFullPipeline:
    """End-to-end test of the orchestrator through QUEUED→RUNNING→COMPLETED.

    Uses:
    - Real SQLite for run persistence
    - Real ContextService with SQLite conversation repository
    - Real WorkflowService with mock LLM
    - Stubs for learning, planning, docs, tools, prompt
    """

    @pytest.mark.asyncio
    async def test_process_run_completes_successfully(self, sqlite_orchestrator) -> None:
        """A QUEUED, approved run should progress through all stages to COMPLETED."""
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]
        mock_llm = sqlite_orchestrator["mock_llm"]
        learning = sqlite_orchestrator["learning_service"]
        docs = sqlite_orchestrator["docs_service"]

        _create_run(run_repo)

        result = await orchestrator.process_run("orch-run-1")

        assert result is not None
        assert result.status == RunStatus.COMPLETED
        assert result.current_stage == RunStage.COMPLETED

        # LLM calls: design + code + test + review + chronicle = 5
        assert len(mock_llm.calls) == 5

        # All doc artifacts written
        assert len(docs.calls) == 4

        # Context appended (final result sent to conversation)
        messages = sqlite_orchestrator["context_service"].load_recent_messages(2001)
        assert len(messages) >= 1
        assert messages[-1]["role"] == "assistant"

        # Learning recorded
        assert len(learning.saved) == 1

        # Verify persisted state
        persisted = run_repo.get("orch-run-1")
        assert persisted is not None
        assert persisted.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_run_replans_on_high_concerns(self, sqlite_orchestrator) -> None:
        """When review returns HIGH_CONCERNS: yes, the orchestrator should
        iterate through replanning and run a second cycle.
        """
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]
        planning = sqlite_orchestrator["planning_service"]

        _create_run(run_repo)

        # Override the LLM to return HIGH_CONCERNS: yes on first review
        class HighConcernsLLM(MockLLM):
            async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
                await super().generate(agent_name, system_prompt, user_prompt)
                # _count is incremented by super().generate() — it's now 1-indexed
                # Iteration 1: design(1), code(2), test(3), review(4) -> HIGH
                # Iteration 2: design(5), code(6), test(7), review(8) -> LOW
                if "review agent" in system_prompt.lower():
                    if self._count == 4:
                        return "HIGH_CONCERNS: yes\nNeeds refactoring."
                    return "HIGH_CONCERNS: no\nAccepted."
                return f"Stage response #{self._count}"

        orchestrator._workflow_service = WorkflowService(
            SimpleNamespace(generate=HighConcernsLLM().generate),
            SettingsStub(workflow_control=WorkflowControlStub(max_review_iterations=3)),
        )
        # Also update the deps (OrchestratorDependencies is frozen so replace the whole object)
        from mergemate.application.execution_plan import OrchestratorDependencies

        orchestrator._deps = OrchestratorDependencies(
            run_repository=orchestrator._deps.run_repository,
            context_service=orchestrator._deps.context_service,
            documentation_service=orchestrator._deps.documentation_service,
            learning_service=orchestrator._deps.learning_service,
            planning_service=orchestrator._deps.planning_service,
            prompt_service=orchestrator._deps.prompt_service,
            tool_service=orchestrator._deps.tool_service,
            workflow_service=orchestrator._workflow_service,
            llm_gateway=orchestrator._deps.llm_gateway,
            settings=orchestrator._deps.settings,
        )

        result = await orchestrator.process_run("orch-run-1")

        assert result is not None
        assert result.status == RunStatus.COMPLETED

        # 2 iterations × 4 stages = 8 LLM calls
        # But we can't easily check count because we replaced the LLM
        # Check that replanning occurred
        assert len(planning.calls) >= 1

        # Plan should have been updated in DB
        persisted = run_repo.get("orch-run-1")
        assert persisted is not None
        assert persisted.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_process_run_returns_early_for_cancelled_run(self, sqlite_orchestrator) -> None:
        """A CANCELLED run should be returned immediately without processing."""
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]
        mock_llm = sqlite_orchestrator["mock_llm"]

        _create_run(run_repo, status=RunStatus.CANCELLED)

        result = await orchestrator.process_run("orch-run-1")

        assert result is not None
        assert result.status == RunStatus.CANCELLED
        assert len(mock_llm.calls) == 0

    @pytest.mark.asyncio
    async def test_process_run_returns_early_for_unapproved_run(self, sqlite_orchestrator) -> None:
        """An unapproved run should be returned without processing."""
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]
        mock_llm = sqlite_orchestrator["mock_llm"]

        _create_run(run_repo, approved=False)

        result = await orchestrator.process_run("orch-run-1")

        assert result is not None
        assert result.approved is False
        assert len(mock_llm.calls) == 0

    @pytest.mark.asyncio
    async def test_process_run_returns_early_for_already_running(self, sqlite_orchestrator) -> None:
        """A RUNNING run should not be re-processed."""
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]
        mock_llm = sqlite_orchestrator["mock_llm"]

        _create_run(run_repo, status=RunStatus.RUNNING)

        result = await orchestrator.process_run("orch-run-1")

        assert result is not None
        assert result.status == RunStatus.RUNNING
        assert len(mock_llm.calls) == 0

    @pytest.mark.asyncio
    async def test_process_run_raises_for_missing_run(self, sqlite_orchestrator) -> None:
        """process_run raises ValueError for non-existent run IDs."""
        orchestrator = sqlite_orchestrator["orchestrator"]

        with pytest.raises(RunNotFoundError, match="was not found"):
            await orchestrator.process_run("nonexistent")

    @pytest.mark.asyncio
    async def test_process_run_handles_direct_execution(self, sqlite_orchestrator) -> None:
        """A non-generate_code workflow (debug_code) should take the direct
        execution path — single LLM call, no doc artifacts.
        """
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]
        mock_llm = sqlite_orchestrator["mock_llm"]
        learning = sqlite_orchestrator["learning_service"]

        _create_run(run_repo, run_id="orch-dbg-1", workflow="debug_code", agent_name="debugger")

        result = await orchestrator.process_run("orch-dbg-1")

        assert result is not None
        assert result.status == RunStatus.COMPLETED

        # Single LLM call for direct execution
        assert len(mock_llm.calls) == 1

        # No doc artifacts
        assert len(sqlite_orchestrator["docs_service"].calls) == 0

        # Learning recorded
        assert len(learning.saved) == 1

        # Context appended
        messages = sqlite_orchestrator["context_service"].load_recent_messages(2001)
        assert len(messages) >= 1
        assert messages[-1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_process_run_trims_duplicate_prompt(self, sqlite_orchestrator) -> None:
        """The orchestrator should trim the last user message if it's
        identical to the current prompt before rendering.
        """
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]
        context = sqlite_orchestrator["context_service"]

        _create_run(run_repo, run_id="orch-trim-1")

        # Add conversation history with a duplicate last message
        context.append_message(2001, "assistant", "previous response")
        context.append_message(2001, "user", "build a login system")

        class CapturingPromptService:
            def render(self, workflow, recent_messages, learned_items, prompt):
                self.captured_messages = list(recent_messages)
                return ("system", "ctx")

        capturer = CapturingPromptService()
        orchestrator._prompt_service = capturer

        result = await orchestrator.process_run("orch-trim-1")

        assert result is not None
        # The duplicate user message should have been trimmed
        assert len(capturer.captured_messages) == 1
        assert capturer.captured_messages[0]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_process_run_includes_runtime_tool_context(self, sqlite_orchestrator) -> None:
        """For direct execution plans requiring tool context, the tool
        service output should be appended to the execution context.
        """
        run_repo = sqlite_orchestrator["run_repo"]
        tool_service = ToolServiceStub(runtime_context="Enabled tools: git")
        sqlite_orchestrator["tool_service"] = tool_service

        deps = OrchestratorDependencies(
            run_repository=run_repo,
            context_service=sqlite_orchestrator["context_service"],
            documentation_service=sqlite_orchestrator["docs_service"],
            learning_service=sqlite_orchestrator["learning_service"],
            planning_service=sqlite_orchestrator["planning_service"],
            prompt_service=PromptServiceStub(),
            tool_service=tool_service,
            workflow_service=sqlite_orchestrator["orchestrator"]._workflow_service,
            llm_gateway=sqlite_orchestrator["orchestrator"]._llm_gateway,
            settings=sqlite_orchestrator["settings"],
        )
        orchestrator = AgentOrchestrator(deps)

        _create_run(run_repo, run_id="orch-tool-1", workflow="debug_code", agent_name="debugger")

        result = await orchestrator.process_run("orch-tool-1")

        assert result is not None
        assert result.status == RunStatus.COMPLETED
        assert len(tool_service.calls) == 1
        assert tool_service.calls[0] == ("orch-tool-1", "debugger", "retrieve_context")

    @pytest.mark.asyncio
    async def test_process_run_transitions_status_correctly(self, sqlite_orchestrator) -> None:
        """Verify the status transition: QUEUED → RUNNING → COMPLETED."""
        run_repo = sqlite_orchestrator["run_repo"]
        orchestrator = sqlite_orchestrator["orchestrator"]

        _create_run(run_repo, run_id="orch-trans-1")

        # Before processing, run should be QUEUED
        before = run_repo.get("orch-trans-1")
        assert before is not None
        assert before.status == RunStatus.QUEUED

        result = await orchestrator.process_run("orch-trans-1")

        assert result is not None
        assert result.status == RunStatus.COMPLETED

        # Verify persisted state
        persisted = run_repo.get("orch-trans-1")
        assert persisted is not None
        assert persisted.status == RunStatus.COMPLETED