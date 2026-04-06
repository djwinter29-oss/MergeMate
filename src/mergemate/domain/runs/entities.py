"""Run entities."""

from dataclasses import dataclass
from datetime import datetime

from mergemate.domain.runs.value_objects import RunJobStatus, RunJobType, RunStage, RunStatus


@dataclass(slots=True)
class AgentRun:
    run_id: str
    chat_id: int
    user_id: int
    agent_name: str
    workflow: str
    status: RunStatus
    current_stage: str | RunStage
    prompt: str
    estimate_seconds: int
    plan_text: str | None
    design_text: str | None
    test_text: str | None
    review_text: str | None
    review_iterations: int
    approved: bool
    result_text: str | None
    error_text: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class RunJob:
    job_id: str
    run_id: str
    job_type: RunJobType
    status: RunJobStatus
    attempt_count: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None
    error_text: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime