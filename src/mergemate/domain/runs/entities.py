"""Run entities."""

from dataclasses import dataclass
from datetime import datetime

from mergemate.domain.runs.value_objects import RunStatus


@dataclass(slots=True)
class AgentRun:
    run_id: str
    chat_id: int
    user_id: int
    agent_name: str
    workflow: str
    status: RunStatus
    current_stage: str
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