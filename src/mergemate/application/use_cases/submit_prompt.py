"""Submit a prompt and return an immediate acknowledgement."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from mergemate.application.jobs.dispatcher import RunDispatcher
from mergemate.application.jobs.estimator import estimate_duration
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunJobType, RunStage, RunStatus


@dataclass(slots=True)
class SubmitPromptResult:
    run_id: str
    status: str
    estimate_seconds: int
    plan_text: str | None


@dataclass(slots=True)
class ApproveRunResult:
    run_id: str
    dispatched: bool
    status: str
    error_text: str | None = None


class PromptSubmissionError(RuntimeError):
    def __init__(self, run_id: str, error_text: str) -> None:
        super().__init__(error_text)
        self.run_id = run_id
        self.error_text = error_text


class SubmitPromptUseCase:
    def __init__(
        self,
        run_repository,
        context_service,
        dispatcher: RunDispatcher,
        planning_service,
        settings,
    ) -> None:
        self._run_repository = run_repository
        self._context_service = context_service
        self._dispatcher = dispatcher
        self._planning_service = planning_service
        self._settings = settings

    async def execute(
        self,
        *,
        chat_id: int,
        user_id: int,
        agent_name: str,
        workflow: str,
        prompt: str,
    ) -> SubmitPromptResult:
        now = datetime.now(UTC)
        estimate_seconds = estimate_duration(workflow)
        require_confirmation = self._settings.workflow_control.require_confirmation
        initial_status = (
            RunStatus.AWAITING_CONFIRMATION if require_confirmation else RunStatus.QUEUED
        )
        run = AgentRun(
            run_id=uuid4().hex,
            chat_id=chat_id,
            user_id=user_id,
            agent_name=agent_name,
            workflow=workflow,
            status=initial_status,
            current_stage=RunStage.PLANNING,
            prompt=prompt,
            estimate_seconds=estimate_seconds,
            plan_text=None,
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
        self._run_repository.create(run)
        self._context_service.append_message(chat_id, "user", prompt)
        self._dispatch_or_fail(
            run.run_id,
            job_type=RunJobType.PLAN_RUN,
            raise_on_error=True,
        )
        return SubmitPromptResult(
            run_id=run.run_id,
            status=initial_status.value,
            estimate_seconds=estimate_seconds,
            plan_text=None,
        )

    async def complete_planning(
        self,
        run_id: str,
        *,
        on_finished: object | None = None,
    ) -> SubmitPromptResult | None:
        run = self._run_repository.get(run_id)
        if run is None:
            return None
        try:
            plan_text = await self._planning_service.draft_plan(run.prompt)
        except Exception as exc:
            error_text = str(exc)
            self._run_repository.update_status(
                run_id,
                RunStatus.FAILED,
                current_stage=RunStage.PLANNING,
                error_text=error_text,
            )
            raise PromptSubmissionError(run_id, error_text) from exc

        if run.status == RunStatus.AWAITING_CONFIRMATION:
            self._run_repository.update_plan(run_id, plan_text)
            final_status = RunStatus.AWAITING_CONFIRMATION.value
        else:
            self._run_repository.update_plan(
                run_id,
                plan_text,
                current_stage=RunStage.QUEUED_FOR_EXECUTION,
            )
            approval = self._run_repository.approve(run_id)
            if approval.run is None:
                raise PromptSubmissionError(run_id, "Run approval failed before dispatch.")
            self._dispatch_or_fail(run_id, job_type=RunJobType.EXECUTE_RUN, raise_on_error=True)
            final_status = RunStatus.QUEUED.value
        return SubmitPromptResult(
            run_id=run_id,
            status=final_status,
            estimate_seconds=run.estimate_seconds,
            plan_text=plan_text,
        )

    async def revise_plan(self, run_id: str, feedback: str) -> SubmitPromptResult | None:
        return await self.revise_plan_for_chat(run_id, feedback)

    async def revise_plan_for_chat(
        self,
        run_id: str,
        feedback: str,
        *,
        chat_id: int | None = None,
    ) -> SubmitPromptResult | None:
        existing = self._run_repository.get(run_id)
        if existing is None:
            return None
        if chat_id is not None and existing.chat_id != chat_id:
            return None
        try:
            updated_prompt, plan_text = await self._planning_service.revise_plan(
                existing.prompt,
                feedback,
            )
        except Exception as exc:
            error_text = str(exc)
            self._run_repository.update_status(
                run_id,
                existing.status,
                current_stage=existing.current_stage,
                error_text=error_text,
            )
            raise PromptSubmissionError(run_id, error_text) from exc
        updated_run = self._run_repository.update_plan(run_id, plan_text, prompt=updated_prompt)
        if updated_run is None:
            return None
        self._context_service.append_message(existing.chat_id, "user", feedback)
        return SubmitPromptResult(
            run_id=updated_run.run_id,
            status=updated_run.status.value,
            estimate_seconds=updated_run.estimate_seconds,
            plan_text=plan_text,
        )

    def approve(
        self,
        run_id: str,
        *,
        chat_id: int | None = None,
        on_finished=None,
    ) -> ApproveRunResult | None:
        existing = self._run_repository.get(run_id)
        if existing is None:
            return None
        if chat_id is not None and existing.chat_id != chat_id:
            return None
        if existing.status in RunStatus.terminal_statuses():
            return ApproveRunResult(run_id=existing.run_id, dispatched=False, status=existing.status.value)
        if existing.plan_text is None:
            return ApproveRunResult(
                run_id=existing.run_id,
                dispatched=False,
                status=existing.status.value,
                error_text="Run planning is still in progress and cannot be approved yet.",
            )
        if existing.approved or existing.status != RunStatus.AWAITING_CONFIRMATION:
            return ApproveRunResult(run_id=existing.run_id, dispatched=False, status=existing.status.value)

        approval = self._run_repository.approve(run_id)
        approved_run = approval.run
        if approved_run is None:
            return None
        if not approval.transitioned:
            return ApproveRunResult(run_id=approved_run.run_id, dispatched=False, status=approved_run.status.value)
        error_text = self._dispatch_or_fail(run_id, job_type=RunJobType.EXECUTE_RUN, raise_on_error=False)
        if error_text is not None:
            return ApproveRunResult(
                run_id=run_id,
                dispatched=False,
                status=RunStatus.FAILED.value,
                error_text=error_text,
            )
        return ApproveRunResult(run_id=approved_run.run_id, dispatched=True, status=approved_run.status.value)

    def _dispatch_or_fail(
        self,
        run_id: str,
        *,
        job_type: RunJobType,
        raise_on_error: bool,
    ) -> str | None:
        try:
            self._dispatcher.dispatch_run(run_id, job_type=job_type)
        except RuntimeError as exc:
            error_text = str(exc)
            current_stage = (
                RunStage.PLANNING if job_type == RunJobType.PLAN_RUN else RunStage.QUEUED_FOR_EXECUTION
            )
            self._run_repository.update_status(
                run_id,
                RunStatus.FAILED,
                current_stage=current_stage,
                error_text=error_text,
            )
            if raise_on_error:
                raise PromptSubmissionError(run_id, error_text) from exc
            return error_text
        return None