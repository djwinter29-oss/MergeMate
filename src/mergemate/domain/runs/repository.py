"""Run repository contract."""

from dataclasses import dataclass
from typing import Protocol

from mergemate.domain.runs.entities import AgentRun, RunJob
from mergemate.domain.runs.value_objects import RunJobType, RunStage, RunStatus


@dataclass(slots=True)
class ApprovalDecision:
    run: AgentRun | None
    transitioned: bool


@dataclass(slots=True)
class StatusUpdateDecision:
    run: AgentRun | None
    transitioned: bool


@dataclass(slots=True)
class QueuedRunJobDecision:
    job: RunJob | None
    created: bool


class AgentRunRepository(Protocol):
    def create(self, run: AgentRun) -> None: ...

    def get(self, run_id: str) -> AgentRun | None: ...

    def list_for_chat(self, chat_id: int, limit: int = 5) -> list[AgentRun]: ...

    def try_update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        expected_current_status: RunStatus | None = None,
        current_stage: str | RunStage | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> StatusUpdateDecision: ...

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        expected_current_status: RunStatus | None = None,
        current_stage: str | RunStage | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> AgentRun | None: ...

    def update_plan(
        self,
        run_id: str,
        plan_text: str,
        prompt: str | None = None,
        *,
        current_stage: str | RunStage | None = None,
    ) -> AgentRun | None: ...

    def approve(self, run_id: str) -> ApprovalDecision: ...

    def save_artifacts(
        self,
        run_id: str,
        *,
        current_stage: str | RunStage | None = None,
        design_text: str | None = None,
        test_text: str | None = None,
        review_text: str | None = None,
        result_text: str | None = None,
        review_iterations: int | None = None,
    ) -> AgentRun | None: ...


class RunJobRepository(Protocol):
    def ensure_queued_job(
        self,
        run_id: str,
        *,
        job_type: RunJobType = RunJobType.EXECUTE_RUN,
    ) -> QueuedRunJobDecision: ...

    def get(self, job_id: str) -> RunJob | None: ...

    def get_active_for_run(
        self,
        run_id: str,
        *,
        job_type: RunJobType | None = None,
    ) -> RunJob | None: ...

    def claim_job(self, job_id: str, *, worker_id: str, lease_seconds: int) -> RunJob | None: ...

    def heartbeat_job(self, job_id: str, *, worker_id: str, lease_seconds: int) -> RunJob | None: ...

    def complete_job(self, job_id: str) -> RunJob | None: ...

    def fail_job(self, job_id: str, error_text: str) -> RunJob | None: ...