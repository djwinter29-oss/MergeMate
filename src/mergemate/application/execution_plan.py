"""Execution plan models for workflow delivery."""

from dataclasses import dataclass
from typing import Any, Callable

from mergemate.domain.runs.value_objects import RunStatus


@dataclass(slots=True, frozen=True)
class StageDescriptor:
    name: str
    current_stage: str
    uses_tool_context: bool = False
    checks_cancellation_before: bool = False
    checks_cancellation_after: bool = False


@dataclass(slots=True)
class ExecutionContext:
    run: Any
    system_prompt: str
    context_text: str


@dataclass(slots=True)
class ExecutionRuntime:
    run_repository: Any
    context_service: Any
    documentation_service: Any
    learning_service: Any
    workflow_service: Any
    settings: Any
    is_cancelled: Callable[[str], bool]


class DirectExecutionPlan:
    stages = (
        StageDescriptor(
            name="execution",
            current_stage="execution",
            uses_tool_context=True,
        ),
    )

    def __init__(self, agent_name: str) -> None:
        self._agent_name = agent_name

    @property
    def requires_tool_context(self) -> bool:
        return any(stage.uses_tool_context for stage in self.stages)

    async def execute(self, runtime: ExecutionRuntime, execution: ExecutionContext):
        run = execution.run
        if runtime.is_cancelled(run.run_id):
            return runtime.run_repository.get(run.run_id)
        direct_result = await runtime.workflow_service.execute_direct(
            self._agent_name,
            execution.system_prompt,
            execution.context_text,
        )
        if runtime.is_cancelled(run.run_id):
            return runtime.run_repository.get(run.run_id)
        runtime.run_repository.save_artifacts(
            run.run_id,
            current_stage=self.stages[0].current_stage,
            result_text=direct_result,
        )
        runtime.context_service.append_message(run.chat_id, "assistant", direct_result)
        runtime.learning_service.remember_success(
            chat_id=run.chat_id,
            workflow=run.workflow,
            prompt=run.prompt,
            result_text=direct_result,
        )
        completed_run = runtime.run_repository.update_status(
            run.run_id,
            RunStatus.COMPLETED,
            current_stage="completed",
            result_text=direct_result,
        )
        assert completed_run is not None
        return completed_run


class MultiStageExecutionPlan:
    stages = (
        StageDescriptor(
            name="design",
            current_stage="design",
            uses_tool_context=True,
            checks_cancellation_before=True,
            checks_cancellation_after=True,
        ),
        StageDescriptor(
            name="implementation",
            current_stage="implementation",
            uses_tool_context=True,
            checks_cancellation_after=True,
        ),
        StageDescriptor(
            name="testing",
            current_stage="testing",
            checks_cancellation_after=True,
        ),
        StageDescriptor(
            name="review",
            current_stage="review",
            checks_cancellation_after=True,
        ),
        StageDescriptor(
            name="replanning",
            current_stage="internal_replanning",
            checks_cancellation_after=True,
        ),
    )

    def __init__(self, agent_name: str, max_iterations: int) -> None:
        self._agent_name = agent_name
        self._max_iterations = max_iterations

    @property
    def requires_tool_context(self) -> bool:
        return any(stage.uses_tool_context for stage in self.stages)

    async def execute(self, runtime: ExecutionRuntime, execution: ExecutionContext):
        run = execution.run
        current_plan = run.plan_text or "No approved plan available."
        implementation_text = ""
        test_text = ""
        review_text = ""
        design_document_path = ""
        test_document_path = ""
        review_document_path = ""

        design_stage, implementation_stage, testing_stage, review_stage, replanning_stage = self.stages

        for iteration in range(1, self._max_iterations + 1):
            if design_stage.checks_cancellation_before and runtime.is_cancelled(run.run_id):
                return runtime.run_repository.get(run.run_id)

            design_text = await runtime.workflow_service.create_design(current_plan, execution.context_text)
            design_document_path = str(
                runtime.documentation_service.write_architecture_design(
                    run_id=run.run_id,
                    iteration=iteration,
                    plan_text=current_plan,
                    design_text=design_text,
                )
            )
            runtime.run_repository.save_artifacts(
                run.run_id,
                current_stage=design_stage.current_stage,
                design_text=design_text,
                review_iterations=iteration,
            )
            if design_stage.checks_cancellation_after and runtime.is_cancelled(run.run_id):
                return runtime.run_repository.get(run.run_id)

            implementation_text = await runtime.workflow_service.generate_code(
                current_plan,
                design_text,
                execution.context_text,
                agent_name=self._agent_name,
            )
            runtime.run_repository.save_artifacts(
                run.run_id,
                current_stage=implementation_stage.current_stage,
                result_text=implementation_text,
                review_iterations=iteration,
            )
            if implementation_stage.checks_cancellation_after and runtime.is_cancelled(run.run_id):
                return runtime.run_repository.get(run.run_id)

            test_text = await runtime.workflow_service.generate_tests(current_plan, design_text, implementation_text)
            test_document_path = str(
                runtime.documentation_service.write_test_plan(
                    run_id=run.run_id,
                    iteration=iteration,
                    plan_text=current_plan,
                    design_text=design_text,
                    test_text=test_text,
                )
            )
            runtime.run_repository.save_artifacts(
                run.run_id,
                current_stage=testing_stage.current_stage,
                test_text=test_text,
                review_iterations=iteration,
            )
            if testing_stage.checks_cancellation_after and runtime.is_cancelled(run.run_id):
                return runtime.run_repository.get(run.run_id)

            review_text = await runtime.workflow_service.review(
                current_plan,
                design_text,
                implementation_text,
                test_text,
            )
            review_document_path = str(
                runtime.documentation_service.write_review_report(
                    run_id=run.run_id,
                    iteration=iteration,
                    plan_text=current_plan,
                    design_text=design_text,
                    implementation_text=implementation_text,
                    test_text=test_text,
                    review_text=review_text,
                )
            )
            runtime.run_repository.save_artifacts(
                run.run_id,
                current_stage=review_stage.current_stage,
                review_text=review_text,
                review_iterations=iteration,
            )
            if review_stage.checks_cancellation_after and runtime.is_cancelled(run.run_id):
                return runtime.run_repository.get(run.run_id)

            if not runtime.workflow_service.has_high_concerns(review_text):
                break
            if iteration >= self._max_iterations:
                break

            current_plan = await runtime.workflow_service.draft_plan(run.prompt, prior_feedback=review_text)
            runtime.run_repository.update_plan(
                run.run_id,
                current_plan,
                current_stage=replanning_stage.current_stage,
            )
            if replanning_stage.checks_cancellation_after and runtime.is_cancelled(run.run_id):
                return runtime.run_repository.get(run.run_id)

        latest_run = runtime.run_repository.get(run.run_id)
        if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
            return latest_run

        final_result = (
            f"Approved plan:\n{current_plan}\n\n"
            f"Design document:\n{design_document_path}\n\n"
            f"Test plan document:\n{test_document_path}\n\n"
            f"Review report:\n{review_document_path}\n\n"
            f"Design:\n{latest_run.design_text if latest_run and latest_run.design_text else ''}\n\n"
            f"Implementation:\n{implementation_text}\n\n"
            f"Tests:\n{test_text}\n\n"
            f"Review:\n{review_text}"
        ).strip()

        runtime.context_service.append_message(run.chat_id, "assistant", final_result)
        runtime.learning_service.remember_success(
            chat_id=run.chat_id,
            workflow=run.workflow,
            prompt=run.prompt,
            result_text=final_result,
        )
        completed_run = runtime.run_repository.update_status(
            run.run_id,
            RunStatus.COMPLETED,
            current_stage="completed",
            result_text=final_result,
        )
        assert completed_run is not None
        return completed_run