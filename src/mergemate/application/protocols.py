"""Service protocol definitions for structural subtyping of orchestrator dependencies.

All protocols use structural subtyping (Protocol) so that any class with matching
methods is automatically compatible without explicit inheritance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ContextServiceProtocol(Protocol):
    def append_message(self, chat_id: int, role: str, content: str) -> None: ...
    def load_recent_messages(self, chat_id: int, limit: int = 8) -> list[dict[str, str]]: ...


@runtime_checkable
class DocumentationServiceProtocol(Protocol):
    def write_architecture_design(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
        role_name: str | None = None,
    ) -> Path: ...

    def write_implementation(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        code_text: str,
        role_name: str | None = None,
    ) -> Path: ...

    def write_testing(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        test_text: str,
        role_name: str | None = None,
    ) -> Path: ...

    def write_review(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        review_text: str,
        role_name: str | None = None,
    ) -> Path: ...

    def write_lessons(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        lesson_text: str,
        role_name: str | None = None,
    ) -> Path: ...

    def write_planning(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        role_name: str | None = None,
    ) -> Path: ...


@runtime_checkable
class LearningServiceProtocol(Protocol):
    def remember_success(self, *, chat_id: int, workflow: str, prompt: str, result_text: str) -> None: ...
    def load_recent_learnings(self, chat_id: int) -> list[dict[str, str]]: ...


@runtime_checkable
class PlanningServiceProtocol(Protocol):
    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str: ...


@runtime_checkable
class PromptServiceProtocol(Protocol):
    def render(
        self,
        workflow: str,
        recent_messages: list[dict[str, str]],
        learned_items: list[dict[str, str]],
        user_prompt: str,
    ) -> tuple[str, str]: ...


@runtime_checkable
class ToolServiceProtocol(Protocol):
    def list_enabled_tools(self, agent_name: str) -> list[str]: ...
    def install_package(self, package_name: str) -> dict[str, str]: ...


@runtime_checkable
class WorkflowServiceProtocol(Protocol):
    def build_execution_plan(
        self, workflow: str, *, agent_name: str
    ) -> Any:  # DirectExecutionPlan | MultiStageExecutionPlan
        ...


@runtime_checkable
class LLMGatewayProtocol(Protocol):
    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str: ...