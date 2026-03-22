"""Run repository contract."""

from typing import Protocol

from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus


class AgentRunRepository(Protocol):
    def create(self, run: AgentRun) -> None: ...

    def get(self, run_id: str) -> AgentRun | None: ...

    def list_for_chat(self, chat_id: int, limit: int = 5) -> list[AgentRun]: ...

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        current_stage: str | None = None,
        result_text: str | None = None,
        error_text: str | None = None,
    ) -> AgentRun | None: ...

    def update_plan(
        self,
        run_id: str,
        plan_text: str,
        prompt: str | None = None,
        *,
        current_stage: str | None = None,
    ) -> AgentRun | None: ...

    def approve(self, run_id: str) -> AgentRun | None: ...

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
    ) -> AgentRun | None: ...