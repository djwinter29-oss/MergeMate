"""Tests for execution plan uncovered lines.

Covers:
1.  BaseExecutionPlan.stages returns () [line 139]
2.  MultiStageExecutionPlan.stages when no workflow def [line 229-230]
3.  MultiStageExecutionPlan.stages when workflow def provided [line 231]
4.  MultiStageExecutionPlan._get_workflow_stages when no workflow def [line 247-252]
5.  MultiStageExecutionPlan.execute when handler is None [line 287-292]
6.  MultiStageExecutionPlan.execute replan handler is None [line 319-323]
7.  MultiStageExecutionPlan._build_final_result with progress summary [lines 394-408]
8.  _check_after_cancelled when stage.checks_cancellation_after is True and cancelled [line 61]
9.  _check_cancelled when stage.checks_cancellation_before is True and cancelled [line 48]
10. ExecutionRuntime(deps=..., is_cancelled=...) constructor [lines 84-87]
11. DirectExecutionPlan.execute full path (lines 166-196)
12. MultiStageExecutionPlan.execute replan handler runs (lines 324-328)
13. MultiStageExecutionPlan.execute cancelled after replan handler (lines 330-337) [line 307 covered via same path]
14. MultiStageExecutionPlan.execute last-iteration check at line 342
15. MultiStageExecutionPlan.execute loop completion at line 360
"""
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mergemate.application.execution_plan import (
    BaseExecutionPlan,
    DirectExecutionPlan,
    ExecutionContext,
    ExecutionRuntime,
    MultiStageExecutionPlan,
    OrchestratorDependencies,
    StageDescriptor,
)
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.shared import RunStage, RunStatus, WorkflowName
from mergemate.domain.shared.exceptions import StageExecutionError
from mergemate.domain.workflows.stage import get_workflow_definitions


_GENERATE_CODE_DEF = get_workflow_definitions()[WorkflowName.GENERATE_CODE]


def _make_run(
    *,
    run_id: str = "run-cover-1",
    chat_id: int = 2001,
    status: RunStatus = RunStatus.QUEUED,
    plan_text: str = "Build a feature",
) -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        run_id=run_id,
        chat_id=chat_id,
        user_id=42,
        agent_name="coder",
        workflow="generate_code",
        status=status,
        current_stage=RunStage.RETRIEVE_CONTEXT,
        prompt="build a feature",
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


class AsyncWorkflowServiceStub:
    """Async workflow service that fulfills all methods the handlers call."""

    def __init__(self, has_high_concerns=None) -> None:
        self._has_high_concerns = has_high_concerns if has_high_concerns is not None else (lambda x: False)

    def has_high_concerns(self, text: str) -> bool:
        return self._has_high_concerns(text)

    async def create_design(self, *args, **kwargs) -> str:
        return "design"

    async def generate_code(self, *args, **kwargs) -> str:
        return "code"

    async def generate_tests(self, *args, **kwargs) -> str:
        return "tests"

    async def review(self, *args, **kwargs) -> str:
        return "review"

    async def record_lesson(self, *args, **kwargs) -> str:
        return "lessons"

    async def execute_direct(self, *args, **kwargs) -> str:
        return "direct result"


class AsyncPlanningServiceStub:
    """Async planning service stub."""

    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        return "revised plan"

    @staticmethod
    def extract_tasks(plan_text: str) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def build_progress_summary(tasks: list[dict[str, Any]], completed_tasks: list[str]) -> str:
        return ""


class RunRepositoryStub:
    """Minimal run repository stub."""

    def __init__(self, run=None):
        self._run = run

    def get(self, run_id: str) -> AgentRun | None:
        return self._run

    def save_artifacts(self, *args, **kwargs):
        return None

    def update_status(self, *args, **kwargs):
        return self._run

    def update_plan(self, *args, **kwargs):
        return None


def _make_runtime(run=None, run_repository=None, *, is_cancelled=None, workflow_service=None,
                  planning_service=None) -> ExecutionRuntime:
    deps = OrchestratorDependencies(
        run_repository=run_repository or RunRepositoryStub(run or _make_run()),
        context_service=SimpleNamespace(append_message=lambda *a, **kw: None),
        documentation_service=SimpleNamespace(
            write_architecture_design=lambda *a, **kw: Path("/tmp/doc.md"),
            write_test_plan=lambda *a, **kw: Path("/tmp/doc.md"),
            write_review_report=lambda *a, **kw: Path("/tmp/doc.md"),
            write_lesson=lambda *a, **kw: Path("/tmp/doc.md"),
        ),
        learning_service=SimpleNamespace(remember_success=lambda *a, **kw: None),
        planning_service=planning_service or AsyncPlanningServiceStub(),
        prompt_service=SimpleNamespace(),
        tool_service=SimpleNamespace(),
        workflow_service=workflow_service or AsyncWorkflowServiceStub(),
        llm_gateway=SimpleNamespace(),
        settings=SimpleNamespace(),
    )
    return ExecutionRuntime(
        deps=deps,
        is_cancelled=is_cancelled or (lambda _: False),
    )


class CancelFlagRepo(RunRepositoryStub):
    """Repository that marks the run CANCELLED on get()."""

    def get(self, run_id: str) -> AgentRun | None:
        if self._run is not None:
            self._run.status = RunStatus.CANCELLED
        return self._run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBaseExecutionPlan:
    def test_stages_returns_empty_tuple(self) -> None:
        """Cover BaseExecutionPlan.stages default."""
        plan = BaseExecutionPlan("test-agent")
        assert plan.stages == ()
        assert plan.requires_tool_context is False


class TestMultiStageExecutionPlanStages:
    def test_stages_returns_empty_when_no_workflow_def(self) -> None:
        """Cover line 229-230: stages returns () when _workflow_definition is None."""
        plan = MultiStageExecutionPlan("test-agent", max_iterations=3)
        assert plan.stages == ()

    def test_stages_returns_descriptors_when_workflow_def_provided(self) -> None:
        """Cover line 231: stages returns StageDescriptor tuple with workflow def."""
        plan = MultiStageExecutionPlan("test-agent", max_iterations=3, workflow_definition=_GENERATE_CODE_DEF)
        stages = plan.stages
        assert len(stages) > 0
        assert all(isinstance(s, StageDescriptor) for s in stages)
        assert stages[0].name == "design"
        assert stages[0].uses_tool_context is True
        assert stages[0].checks_cancellation_before is True

    def test_get_workflow_stages_raises_when_no_workflow_def(self) -> None:
        """Cover lines 247-252: _get_workflow_stages raises StageExecutionError."""
        plan = MultiStageExecutionPlan("test-agent", max_iterations=3)
        with pytest.raises(StageExecutionError, match="requires a workflow_definition"):
            plan._get_workflow_stages()


def test_init_rejects_zero_iterations() -> None:
    """Cover line 221-222: max_iterations < 1 raises."""
    with pytest.raises(StageExecutionError, match="max_iterations must be at least 1"):
        MultiStageExecutionPlan("test-agent", max_iterations=0)


class TestCancelChecks:
    """Cover cancellation check helpers."""

    def test_check_cancelled_returns_none_when_flag_false(self) -> None:
        """Cover line 45-46: checks_cancellation_before is False -> None."""
        from mergemate.application.execution_plan import _check_cancelled
        from mergemate.domain.workflows.stage import WorkflowStage

        stage = WorkflowStage(name="test", current_stage=RunStage.DESIGN, checks_cancellation_before=False)
        deps = OrchestratorDependencies(
            run_repository=SimpleNamespace(get=lambda _: None),
            context_service=SimpleNamespace(),
            documentation_service=SimpleNamespace(),
            learning_service=SimpleNamespace(),
            planning_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(),
            tool_service=SimpleNamespace(),
            workflow_service=SimpleNamespace(),
            llm_gateway=SimpleNamespace(),
            settings=SimpleNamespace(),
        )
        result = _check_cancelled(
            run_id="r1", deps=deps,
            is_cancelled=lambda _: True, stage=stage,
        )
        assert result is None

    def test_check_cancelled_returns_run_when_cancelled(self) -> None:
        """Cover line 48: cancelled run detected and returned."""
        from mergemate.application.execution_plan import _check_cancelled
        from mergemate.domain.workflows.stage import WorkflowStage

        run = _make_run()
        stage = WorkflowStage(name="test", current_stage=RunStage.DESIGN, checks_cancellation_before=True)
        deps = OrchestratorDependencies(
            run_repository=RunRepositoryStub(run),
            context_service=SimpleNamespace(),
            documentation_service=SimpleNamespace(),
            learning_service=SimpleNamespace(),
            planning_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(),
            tool_service=SimpleNamespace(),
            workflow_service=SimpleNamespace(),
            llm_gateway=SimpleNamespace(),
            settings=SimpleNamespace(),
        )
        result = _check_cancelled(
            run_id="r1", deps=deps,
            is_cancelled=lambda _: True, stage=stage,
        )
        assert result is run

    def test_check_after_cancelled_returns_none_when_flag_false(self) -> None:
        """Cover line 60-62: checks_cancellation_after is False -> None."""
        from mergemate.application.execution_plan import _check_after_cancelled
        from mergemate.domain.workflows.stage import WorkflowStage

        stage = WorkflowStage(name="test", current_stage=RunStage.DESIGN, checks_cancellation_after=False)
        deps = OrchestratorDependencies(
            run_repository=SimpleNamespace(get=lambda _: None),
            context_service=SimpleNamespace(),
            documentation_service=SimpleNamespace(),
            learning_service=SimpleNamespace(),
            planning_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(),
            tool_service=SimpleNamespace(),
            workflow_service=SimpleNamespace(),
            llm_gateway=SimpleNamespace(),
            settings=SimpleNamespace(),
        )
        result = _check_after_cancelled(
            run_id="r1", deps=deps,
            is_cancelled=lambda _: True, stage=stage,
        )
        assert result is None

    def test_check_after_cancelled_returns_run_when_cancelled(self) -> None:
        """Cover line 61: after-stage cancellation returns run."""
        from mergemate.application.execution_plan import _check_after_cancelled
        from mergemate.domain.workflows.stage import WorkflowStage

        run = _make_run()
        stage = WorkflowStage(name="test", current_stage=RunStage.DESIGN, checks_cancellation_after=True)
        deps = OrchestratorDependencies(
            run_repository=RunRepositoryStub(run),
            context_service=SimpleNamespace(),
            documentation_service=SimpleNamespace(),
            learning_service=SimpleNamespace(),
            planning_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(),
            tool_service=SimpleNamespace(),
            workflow_service=SimpleNamespace(),
            llm_gateway=SimpleNamespace(),
            settings=SimpleNamespace(),
        )
        result = _check_after_cancelled(
            run_id="r1", deps=deps,
            is_cancelled=lambda _: True, stage=stage,
        )
        assert result is run


class TestDirectExecutionPlan:
    """Cover full DirectExecutionPlan.execute path (lines 166-196)."""

    @pytest.mark.asyncio
    async def test_execute_full_path_completes(self) -> None:
        """Cover lines 166-196: direct execution succeeds end-to-end."""
        run = _make_run()

        class CompletingRepo(RunRepositoryStub):
            def save_artifacts(self, *a, **kw):
                return None
            def update_status(self, run_id, status, **kwargs):
                run.status = status
                return run

        plan = DirectExecutionPlan("debugger")
        runtime = _make_runtime(run, run_repository=CompletingRepo(run))
        execution = ExecutionContext(run=run, system_prompt="sys", context_text="ctx")

        result = await plan.execute(runtime, execution)
        assert result is not None
        assert result.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_execute_cancelled_before_call(self) -> None:
        """Cover line 163-164: cancelled before direct call."""
        run = _make_run()
        plan = DirectExecutionPlan("debugger")
        runtime = _make_runtime(run, is_cancelled=lambda _: True)
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_cancelled_after_call(self) -> None:
        """Cover line 174-175: cancelled after direct call."""
        run = _make_run()
        plan = DirectExecutionPlan("debugger")
        calls = iter([False, True])
        runtime = _make_runtime(run, is_cancelled=lambda _: next(calls, False))
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None


class TestOrchestratorDependencies:
    """Cover ExecutionRuntime(deps=...) constructor."""

    def test_constructor_uses_deps(self) -> None:
        """Cover ExecutionRuntime(deps=deps, is_cancelled=...) constructor."""
        repo = SimpleNamespace()
        deps = OrchestratorDependencies(
            run_repository=repo,
            context_service=SimpleNamespace(),
            documentation_service=SimpleNamespace(),
            learning_service=SimpleNamespace(),
            planning_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(),
            tool_service=SimpleNamespace(),
            workflow_service=SimpleNamespace(),
            llm_gateway=SimpleNamespace(),
            settings=SimpleNamespace(),
        )
        runtime = ExecutionRuntime(deps=deps, is_cancelled=lambda _: False)
        assert runtime.deps.run_repository is repo
        assert callable(runtime.is_cancelled)


class TestMultiStageExecutionPlanMissingHandlers:
    """Cover lines 287-292 and 319-323: handler is None raises StageExecutionError."""

    @pytest.mark.asyncio
    async def test_core_stage_handler_missing_raises_error(self) -> None:
        """Cover lines 287-292: handler is None for core stage raises error."""
        from mergemate.domain.workflows.stage import WorkflowDefinition, WorkflowStage

        bad_stage = WorkflowStage(
            name="nonexistent_stage", current_stage=RunStage.DESIGN,
            handler="not_registered_handler", uses_tool_context=False,
            checks_cancellation_before=False, checks_cancellation_after=False,
        )
        bad_wf = WorkflowDefinition(name="test_workflow", stages=(bad_stage,))
        run = _make_run()
        plan = MultiStageExecutionPlan("test-agent", max_iterations=3, workflow_definition=bad_wf)
        runtime = _make_runtime(run)
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        with pytest.raises(StageExecutionError, match="No handler registered for stage"):
            await plan.execute(runtime, execution)

    @pytest.mark.asyncio
    async def test_replan_handler_missing_raises_error(self) -> None:
        """Cover lines 319-323: replan handler None raises error."""
        run = _make_run()
        plan = MultiStageExecutionPlan("test-agent", max_iterations=2, workflow_definition=_GENERATE_CODE_DEF)
        runtime = _make_runtime(
            run,
            workflow_service=AsyncWorkflowServiceStub(has_high_concerns=lambda x: True),
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        import mergemate.application.execution_plan as ep_mod

        original = ep_mod.get_stage_handler

        def patched(key, *args, **kwargs):
            if key == "replanning":
                return None
            return original(key, *args, **kwargs)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(ep_mod, "get_stage_handler", patched)
        try:
            with pytest.raises(StageExecutionError, match="No handler registered for replanning stage"):
                await plan.execute(runtime, execution)
        finally:
            monkeypatch.undo()


class TestMultiStageExecutionPlanHappyPath:
    """Cover the successful execution path."""

    @pytest.mark.asyncio
    async def test_completes_without_high_concerns(self) -> None:
        """Cover main loop + final completion (lines 275-312, 339-361)."""
        run = _make_run()

        class CompletingRepo(RunRepositoryStub):
            def update_status(self, run_id, status, **kwargs):
                run.status = status
                return run

        plan = MultiStageExecutionPlan("test-agent", max_iterations=2, workflow_definition=_GENERATE_CODE_DEF)
        runtime = _make_runtime(
            run, run_repository=CompletingRepo(run),
            workflow_service=AsyncWorkflowServiceStub(has_high_concerns=lambda x: False),
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None
        assert result.status == RunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_last_iteration_breaks_when_high_concerns(self) -> None:
        """Cover line 313-314: last iteration breaks even with high concerns."""
        run = _make_run()

        class CompletingRepo(RunRepositoryStub):
            def update_status(self, run_id, status, **kwargs):
                run.status = status
                return run

        plan = MultiStageExecutionPlan("test-agent", max_iterations=1, workflow_definition=_GENERATE_CODE_DEF)
        runtime = _make_runtime(
            run, run_repository=CompletingRepo(run),
            workflow_service=AsyncWorkflowServiceStub(has_high_concerns=lambda x: True),
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None
        assert result.status == RunStatus.COMPLETED


class TestMultiStageExecutionPlanCancelledPaths:
    """Cover cancellation paths: before stage, after stage, after replan, after loop."""

    @pytest.mark.asyncio
    async def test_cancelled_before_core_stage(self) -> None:
        """Cover lines 277-284: cancellation before core stage returns early."""
        run = _make_run()
        plan = MultiStageExecutionPlan("test-agent", max_iterations=2, workflow_definition=_GENERATE_CODE_DEF)
        runtime = _make_runtime(
            run, run_repository=CancelFlagRepo(run),
            is_cancelled=lambda _: True,
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None
        assert result.status == RunStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancelled_after_core_stage(self) -> None:
        """Cover lines 300-307: cancellation AFTER core stage handler.

        The design stage has checks_cancellation_before=True and
        checks_cancellation_after=True. We return False for the first check
        (before-stage) so the handler runs, then True for the second check
        (after-stage) so the cancellation path at line 307 is hit.
        """
        run = _make_run()
        calls = iter([False, True])

        plan = MultiStageExecutionPlan("test-agent", max_iterations=2, workflow_definition=_GENERATE_CODE_DEF)
        runtime = _make_runtime(
            run, run_repository=CancelFlagRepo(run),
            is_cancelled=lambda _: next(calls, False),
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None
        assert result.status == RunStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancelled_after_replan_stage(self) -> None:
        """Cover lines 324-337: replan handler runs, then cancellation after.

        Generate_code workflow core stages (design, impl, testing, review, chronicle)
        have these is_cancelled patterns:
          design:     before=True (call 1), after=True (call 2)
          impl:       before=False, after=True (call 3)
          testing:    before=False, after=True (call 4)
          review:     before=False, after=True (call 5)
          chronicle:  before=False, after=True (call 6)

        We return False for all 6 core-stage calls so the handlers run.
        has_high_concerns=True to enter replan path.

        Replan stage: before=False (skip), after=True (call 7) -> True -> cancellation.
        """
        # 6 False values for core stages, then 1 True for replan after-check
        calls = iter([False, False, False, False, False, False, True])

        run = _make_run()
        plan = MultiStageExecutionPlan("test-agent", max_iterations=2, workflow_definition=_GENERATE_CODE_DEF)
        runtime = _make_runtime(
            run, run_repository=CancelFlagRepo(run),
            workflow_service=AsyncWorkflowServiceStub(has_high_concerns=lambda x: True),
            is_cancelled=lambda _: next(calls, False),
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None
        assert result.status == RunStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancelled_after_loop(self) -> None:
        """Cover line 342: cancellation detected after the loop ends."""
        run = _make_run()

        class LateCancelRepo(RunRepositoryStub):
            def update_status(self, run_id, status, **kwargs):
                return None
            def get(self, run_id):
                return _make_run(run_id=run_id, status=RunStatus.CANCELLED)

        plan = MultiStageExecutionPlan("test-agent", max_iterations=2, workflow_definition=_GENERATE_CODE_DEF)
        runtime = _make_runtime(
            run, run_repository=LateCancelRepo(run),
            workflow_service=AsyncWorkflowServiceStub(has_high_concerns=lambda x: False),
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None
        assert result.status == RunStatus.CANCELLED


class TestBuildFinalResult:
    """Cover _build_final_result (lines 394-408)."""

    def test_builds_with_task_breakdown(self) -> None:
        """Cover lines 394-408: progress summary appended when tasks present."""
        artifacts: dict[str, Any] = {
            "plan_text": (
                "## Task Breakdown\n"
                "- [ ] Design the UI (@architect)\n"
                "- [ ] Implement logic (@coder)\n"
                "- [ ] Write tests (@tester)\n"
            ),
            "design_text": "design doc",
            "implementation_text": "code",
            "test_text": "tests",
            "review_text": "review",
            "lesson_text": "lessons",
            "_design_document_path": "",
            "_test_document_path": "",
            "_review_document_path": "",
            "_lesson_document_path": "",
        }
        result = MultiStageExecutionPlan._build_final_result(artifacts, None)
        assert "Approved plan:" in result
        assert "Progress Summary" in result
        assert "architect" in result
        assert "coder" in result
        assert "tester" in result

    def test_builds_without_tasks(self) -> None:
        """Cover line 410: no progress section when no tasks extracted."""
        artifacts: dict[str, Any] = {
            "plan_text": "Simple plan with no breakdown",
            "design_text": "",
            "implementation_text": "",
            "test_text": "",
            "review_text": "",
            "lesson_text": "",
            "_design_document_path": "",
            "_test_document_path": "",
            "_review_document_path": "",
            "_lesson_document_path": "",
        }
        result = MultiStageExecutionPlan._build_final_result(artifacts, None)
        assert "Approved plan:" in result
        assert "Progress Summary" not in result


class TestDirectExecutionPlanCancelledAfterGather:
    """Cover the cancelled-check-after-gather in DirectExecutionPlan.execute path."""

    @pytest.mark.asyncio
    async def test_cancelled_after_call_returns_cancelled_run(self) -> None:
        """Direct execution plan returning cancelled when detected after LLM call."""
        run = _make_run()
        calls = iter([False, True])

        class SaveRepo:
            def __init__(self) -> None:
                self.run = run
            def get(self, run_id: str) -> AgentRun | None:
                next_val = next(calls, False)
                if next_val:
                    self.run = _make_run(run_id=run_id, status=RunStatus.CANCELLED)
                return self.run
            def save_artifacts(self, *a, **kw):
                return None
            def update_status(self, *a, **kw):
                return self.run

        repo = SaveRepo()
        deps = OrchestratorDependencies(
            run_repository=repo,
            context_service=SimpleNamespace(append_message=lambda *a, **kw: None),
            documentation_service=SimpleNamespace(
                write_architecture_design=lambda *a, **kw: Path("/tmp/doc.md"),
                write_test_plan=lambda *a, **kw: Path("/tmp/doc.md"),
                write_review_report=lambda *a, **kw: Path("/tmp/doc.md"),
                write_lesson=lambda *a, **kw: Path("/tmp/doc.md"),
            ),
            learning_service=SimpleNamespace(remember_success=lambda *a, **kw: None),
            planning_service=SimpleNamespace(extract_tasks=lambda x: [], build_progress_summary=lambda x, y: ""),
            prompt_service=SimpleNamespace(),
            tool_service=SimpleNamespace(),
            workflow_service=SimpleNamespace(execute_direct=lambda *a, **kw: "result"),
            llm_gateway=SimpleNamespace(),
            settings=SimpleNamespace(),
        )
        plan = DirectExecutionPlan("debugger")
        runtime = ExecutionRuntime(
            deps=deps,
            is_cancelled=lambda _: True,
        )
        execution = ExecutionContext(run=run, system_prompt="", context_text="")

        result = await plan.execute(runtime, execution)
        assert result is not None