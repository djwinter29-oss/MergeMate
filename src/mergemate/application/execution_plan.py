"""Execution plan models for workflow delivery.

The execution plan is where stages are turned into actual work::

    MultiStageExecutionPlan(agent_name, max_iterations)
        .execute(runtime, execution)

iterates over the stages defined by a ``WorkflowDefinition``, dispatching
each stage to its registered handler.  Adding a new workflow means
defining stages in ``domain/workflows/stage.py`` — no other file needs
to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from mergemate.application.protocols import (
    ContextServiceProtocol,
    DocumentationServiceProtocol,
    LearningServiceProtocol,
    LLMGatewayProtocol,
    PlanningServiceProtocol,
    PromptServiceProtocol,
    ToolServiceProtocol,
    WorkflowServiceProtocol,
)
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.repository import AgentRunRepository
from mergemate.domain.shared import RunStage, RunStatus
from mergemate.domain.shared.exceptions import StageExecutionError
from mergemate.domain.workflows.handlers import get_stage_handler
from mergemate.domain.workflows.stage import WorkflowDefinition, WorkflowStage


def _check_cancelled(
    *,
    run_id: str,
    deps: OrchestratorDependencies,
    is_cancelled: Callable[[str], bool],
    stage: WorkflowStage | None = None,
) -> AgentRun | None:
    """If the run has been cancelled, return the updated run; otherwise None."""
    if stage is not None and not stage.checks_cancellation_before:
        return None
    if is_cancelled(run_id):
        return deps.run_repository.get(run_id)
    return None


def _check_after_cancelled(
    *,
    run_id: str,
    deps: OrchestratorDependencies,
    is_cancelled: Callable[[str], bool],
    stage: WorkflowStage,
) -> AgentRun | None:
    """Check if run was cancelled after a stage, return updated run if so."""
    if stage.checks_cancellation_after and is_cancelled(run_id):
        return deps.run_repository.get(run_id)
    return None


@dataclass(slots=True, frozen=True)
class StageDescriptor:
    """Legacy stage descriptor used by ``DirectExecutionPlan``.

    ``MultiStageExecutionPlan`` now derives its stage data from
    ``WorkflowStage`` objects.  This type is kept for backward
    compatibility only.
    """

    name: str
    current_stage: str | RunStage
    uses_tool_context: bool = False
    checks_cancellation_before: bool = False
    checks_cancellation_after: bool = False


@dataclass(slots=True, frozen=True)
class OrchestratorDependencies:
    """Bundled dependencies for AgentOrchestrator and ExecutionRuntime."""

    run_repository: AgentRunRepository
    context_service: ContextServiceProtocol
    documentation_service: DocumentationServiceProtocol
    learning_service: LearningServiceProtocol
    planning_service: PlanningServiceProtocol
    prompt_service: PromptServiceProtocol
    tool_service: ToolServiceProtocol
    workflow_service: WorkflowServiceProtocol
    llm_gateway: LLMGatewayProtocol
    settings: Any


@dataclass(slots=True)
class ExecutionRuntime:
    deps: OrchestratorDependencies
    is_cancelled: Callable[[str], bool]


@dataclass(slots=True)
class ExecutionContext:
    run: AgentRun
    system_prompt: str
    context_text: str


class BaseExecutionPlan:
    """Base execution plan — provides shared stage iteration logic."""

    def __init__(self, agent_name: str) -> None:
        self._agent_name = agent_name

    @property
    def stages(self) -> tuple[StageDescriptor, ...]:
        """Return the stage descriptors for this plan."""
        return ()

    @property
    def requires_tool_context(self) -> bool:
        return any(stage.uses_tool_context for stage in self.stages)


class DirectExecutionPlan(BaseExecutionPlan):
    """Single-stage execution plan — one LLM call, no sub-stages."""

    @property
    def stages(self) -> tuple[StageDescriptor, ...]:
        return (
            StageDescriptor(
                name="execution",
                current_stage=RunStage.EXECUTION,
                uses_tool_context=True,
            ),
        )

    async def execute(self, runtime: ExecutionRuntime, execution: ExecutionContext) -> Any:
        run = execution.run
        cancelled = _check_cancelled(
            run_id=run.run_id,
            deps=runtime.deps,
            is_cancelled=runtime.is_cancelled,
        )
        if cancelled is not None:
            return cancelled

        direct_result = await runtime.deps.workflow_service.execute_direct(
            self._agent_name,
            execution.system_prompt,
            execution.context_text,
        )
        cancelled = _check_cancelled(
            run_id=run.run_id,
            deps=runtime.deps,
            is_cancelled=runtime.is_cancelled,
        )
        if cancelled is not None:
            return cancelled

        runtime.deps.run_repository.save_artifacts(
            run.run_id,
            current_stage=self.stages[0].current_stage,
            result_text=direct_result,
        )
        runtime.deps.context_service.append_message(run.chat_id, "assistant", direct_result)
        await runtime.deps.learning_service.remember_success(
            chat_id=run.chat_id,
            workflow=run.workflow,
            prompt=run.prompt,
            result_text=direct_result,
        )
        completed_run = runtime.deps.run_repository.update_status(
            run.run_id,
            RunStatus.COMPLETED,
            current_stage=RunStage.COMPLETED,
            result_text=direct_result,
        )
        assert completed_run is not None
        return completed_run


class MultiStageExecutionPlan(BaseExecutionPlan):
    """Multi-stage execution plan driven by a ``WorkflowDefinition``.

    Stage instances are extracted from the ``workflow_definition`` and
    executed in order via their registered handlers.  The review loop
    condition (high-concerns check) is built into the iteration logic,
    and the ``replanning`` stage is only entered when the review stage
    determines that rework is needed.

    The stage list within a single iteration constitutes the "core"
    pipeline (e.g. design → implementation → testing → review).
    Between iterations, a replanning handler runs if the review
    identified concerns.
    """

    def __init__(
        self,
        agent_name: str,
        max_iterations: int,
        workflow_definition: WorkflowDefinition | None = None,
    ) -> None:
        super().__init__(agent_name)
        if max_iterations < 1:
            raise StageExecutionError("max_iterations must be at least 1")
        self._max_iterations = max_iterations
        self._workflow_definition = workflow_definition

    @property
    def stages(self) -> tuple[StageDescriptor, ...]:
        """Derive legacy ``StageDescriptor`` tuples from the workflow definition."""
        if self._workflow_definition is None:
            return ()
        return tuple(
            StageDescriptor(
                name=s.name,
                current_stage=s.current_stage,
                uses_tool_context=s.uses_tool_context,
                checks_cancellation_before=s.checks_cancellation_before,
                checks_cancellation_after=s.checks_cancellation_after,
            )
            for s in self._workflow_definition.stages
        )

    def _get_workflow_stages(self) -> tuple[WorkflowStage, ...]:
        """Return the ``WorkflowStage`` instances to execute.

        Raises ``ValueError`` if no workflow definition was provided.
        """
        if self._workflow_definition is None:
            raise StageExecutionError(
                "MultiStageExecutionPlan requires a workflow_definition. "
                "Pass it via the constructor or use WorkflowService.build_execution_plan()."
            )
        return self._workflow_definition.stages

    async def execute(self, runtime: ExecutionRuntime, execution: ExecutionContext) -> Any:
        run = execution.run
        workflow_stages = self._get_workflow_stages()

        # Separate the "replanning" stage — it runs between iterations, not
        # as part of the core pipeline within a single iteration.
        core_stages = tuple(s for s in workflow_stages if s.handler != "replanning")
        replan_stage = next((s for s in workflow_stages if s.handler == "replanning"), None)

        # Shared artifacts dict that handlers read from and write to.
        artifacts: dict[str, Any] = {
            "run_id": run.run_id,
            "run_prompt": run.prompt,
            "plan_text": run.plan_text or "No approved plan available.",
            "context_text": execution.context_text,
            "system_prompt": execution.system_prompt,
        }

        for iteration in range(1, self._max_iterations + 1):
            artifacts["_iteration"] = iteration

            # ── Execute core stages ──────────────────────────────────────
            for stage in core_stages:
                cancelled = _check_cancelled(
                    run_id=run.run_id,
                    deps=runtime.deps,
                    is_cancelled=runtime.is_cancelled,
                    stage=stage,
                )
                if cancelled is not None:
                    return cancelled

                handler = get_stage_handler(stage.handler)
                if handler is None:
                    raise StageExecutionError(
                        f"No handler registered for stage {stage.name!r} "
                        f"(handler key: {stage.handler!r}). "
                        f"Register a handler with @register_handler({stage.handler!r})."
                    )

                artifacts = await handler(
                    runtime,
                    artifacts,
                    agent_name=self._agent_name,
                )

                cancelled = _check_after_cancelled(
                    run_id=run.run_id,
                    deps=runtime.deps,
                    is_cancelled=runtime.is_cancelled,
                    stage=stage,
                )
                if cancelled is not None:
                    return cancelled

            # ── Review gate ──────────────────────────────────────────────
            review_text = artifacts.get("review_text", "")
            if not runtime.deps.workflow_service.has_high_concerns(review_text):
                break
            if iteration >= self._max_iterations:
                break

            # ── Replan between iterations ────────────────────────────────
            if replan_stage is not None:
                handler = get_stage_handler(replan_stage.handler)
                if handler is None:
                    raise StageExecutionError(
                        f"No handler registered for replanning stage "
                        f"(handler key: {replan_stage.handler!r})."
                    )
                artifacts = await handler(
                    runtime,
                    artifacts,
                    agent_name=self._agent_name,
                )

                cancelled = _check_after_cancelled(
                    run_id=run.run_id,
                    deps=runtime.deps,
                    is_cancelled=runtime.is_cancelled,
                    stage=replan_stage,
                )
                if cancelled is not None:
                    return cancelled

        # After the loop, check for cancellation one last time.
        latest_run = runtime.deps.run_repository.get(run.run_id)
        if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
            return latest_run

        # Build final result from accumulated artifacts.
        final_result = self._build_final_result(artifacts, latest_run)

        runtime.deps.context_service.append_message(run.chat_id, "assistant", final_result)
        await runtime.deps.learning_service.remember_success(
            chat_id=run.chat_id,
            workflow=run.workflow,
            prompt=run.prompt,
            result_text=final_result,
        )
        completed_run = runtime.deps.run_repository.update_status(
            run.run_id,
            RunStatus.COMPLETED,
            current_stage=RunStage.COMPLETED,
            result_text=final_result,
        )
        assert completed_run is not None
        return completed_run

    @staticmethod
    def _build_final_result(
        artifacts: dict[str, Any],
        latest_run: Any,
    ) -> str:
        """Assemble the user-facing result string from accumulated artifacts."""
        plan_text = artifacts.get("plan_text", "")
        design_text = artifacts.get("design_text", "")
        implementation_text = artifacts.get("implementation_text", "")
        test_text = artifacts.get("test_text", "")
        review_text = artifacts.get("review_text", "")
        design_doc = artifacts.get("_design_document_path", "")
        test_doc = artifacts.get("_test_document_path", "")
        review_doc = artifacts.get("_review_document_path", "")
        lesson_doc = artifacts.get("_lesson_document_path", "")

        base = (
            f"Approved plan:\n{plan_text}\n\n"
            f"Design document:\n{design_doc}\n\n"
            f"Test plan document:\n{test_doc}\n\n"
            f"Review report:\n{review_doc}\n\n"
            f"Lesson document:\n{lesson_doc}\n\n"
            f"Design:\n{design_text}\n\n"
            f"Implementation:\n{implementation_text}\n\n"
            f"Tests:\n{test_text}\n\n"
            f"Review:\n{review_text}"
        ).strip()

        # ── Progress summary from task breakdown ──────────────────────
        from mergemate.application.services.planning_service import PlanningService

        tasks = PlanningService.extract_tasks(plan_text)
        if tasks:
            completed_roles: list[str] = []
            if artifacts.get("design_text"):
                completed_roles.append("architect")
            if artifacts.get("implementation_text"):
                completed_roles.append("coder")
            if artifacts.get("test_text"):
                completed_roles.append("tester")
            if artifacts.get("review_text"):
                completed_roles.append("reviewer")
            if artifacts.get("lesson_text"):
                completed_roles.append("chronicler")
            progress = PlanningService.build_progress_summary(tasks, completed_roles)
            return base + "\n\n" + progress

        return base
