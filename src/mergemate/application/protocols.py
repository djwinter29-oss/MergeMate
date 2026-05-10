"""Protocol interfaces for application-layer services.

Each Protocol defines the public contract that the orchestration and execution
layers depend on.  Concrete implementations (e.g. ``ContextService``,
``DocumentationService``) satisfy these protocols structurally — no explicit
inheritance required, as long as their public method signatures match.

These protocols replace the bare ``Any`` annotations in
``OrchestratorDependencies`` and ``ExecutionRuntime``, giving static type
checkers and readers a precise view of what each dependency provides without
requiring changes to the concrete service classes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:

    from mergemate.application.execution_plan import (
        DirectExecutionPlan,
        MultiStageExecutionPlan,
    )
    from mergemate.domain.shared import RunStage

# ---------------------------------------------------------------------------
# Repository Protocols
# ---------------------------------------------------------------------------

# ``AgentRunRepository`` is already defined as a Protocol in
# ``mergemate.domain.runs.repository`` — that definition is the authoritative
# contract.  We re-export it here for convenience so that
# ``OrchestratorDependencies`` can reference ``AgentRunRepository`` without
# crossing domain→application import boundaries for every protocol.
#
# NOTE: If ``AgentRunRepository`` ever diverges from what the orchestration
# layer actually calls (e.g. only a subset of methods is used), consider
# defining a narrower ``IRunRepository`` protocol here instead.  For now
# the full domain protocol matches usage.

# ---------------------------------------------------------------------------
# Service Protocols
# ---------------------------------------------------------------------------


class ContextServiceProtocol(Protocol):
    """Contract for conversation-context lookup and persistence."""

    def append_message(self, chat_id: int, role: str, content: str) -> None: ...

    def load_recent_messages(self, chat_id: int, limit: int = 8) -> list[dict[str, str]]: ...


class DocumentationServiceProtocol(Protocol):
    """Contract for writing workflow documents under ``docs/``."""

    def write_architecture_design(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
        role_name: str | None = None,
    ) -> Path: ...

    def write_test_plan(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
        test_text: str,
        role_name: str | None = None,
    ) -> Path: ...

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
    ) -> Path: ...

    def write_lesson(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        lesson_text: str,
        role_name: str | None = None,
    ) -> Path: ...


class LearningServiceProtocol(Protocol):
    """Contract for learning-memory (successful run recall)."""

    def remember_success(
        self,
        *,
        chat_id: int,
        workflow: str,
        prompt: str,
        result_text: str,
    ) -> None: ...

    def load_recent_learnings(self, chat_id: int) -> list[dict[str, str]]: ...


class PlanningServiceProtocol(Protocol):
    """Contract for prompt-based plan generation and revision."""

    async def draft_plan(
        self,
        prompt: str,
        prior_feedback: str | None = None,
    ) -> str: ...

    async def revise_plan(self, existing_prompt: str, feedback: str) -> tuple[str, str]: ...


class PromptServiceProtocol(Protocol):
    """Contract for prompt assembly (system + context)."""

    def render(
        self,
        workflow: str,
        recent_messages: list[dict[str, str]],
        learned_items: list[dict[str, str]],
        user_prompt: str,
    ) -> tuple[str, str]: ...


class ToolServiceProtocol(Protocol):
    """Contract for tool discovery, invocation, and context building."""

    def list_enabled_tools(self, agent_name: str) -> list[str]: ...

    def execute_enabled_tool(
        self,
        agent_name: str,
        tool_name: str,
        payload: dict[str, str],
        *,
        run_id: str | None = None,
        resume_stage: str | RunStage = ...,
    ) -> dict[str, str]: ...

    def install_package(self, package_name: str) -> dict[str, str]: ...

    async def build_runtime_tool_context_async(
        self,
        run_id: str,
        agent_name: str,
        *,
        resume_stage: str | RunStage = ...,
    ) -> str: ...

    def get_repository_context(
        self,
        platform: str | None = None,
    ) -> dict[str, dict[str, str]]: ...

    def get_platform_auth_status(self, platform: str) -> dict[str, str]: ...


class WorkflowServiceProtocol(Protocol):
    """Contract for execution-plan building and stage orchestration."""

    def build_execution_plan(
        self,
        workflow: str,
        *,
        agent_name: str,
    ) -> DirectExecutionPlan | MultiStageExecutionPlan: ...

    async def create_design(self, plan_text: str, context_text: str) -> str: ...

    async def generate_code(
        self,
        plan_text: str,
        design_text: str,
        context_text: str,
        *,
        agent_name: str | None = None,
    ) -> str: ...

    async def execute_direct(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...

    async def generate_tests(
        self,
        plan_text: str,
        design_text: str,
        implementation_text: str,
    ) -> str: ...

    async def review(
        self,
        plan_text: str,
        design_text: str,
        implementation_text: str,
        test_text: str,
    ) -> str: ...

    async def record_lesson(
        self,
        *,
        plan_text: str = "",
        design_text: str = "",
        implementation_text: str = "",
        test_text: str = "",
        review_text: str = "",
        result_text: str = "",
        error_text: str = "",
        agent_name: str = "",
    ) -> str: ...

    @staticmethod
    def has_high_concerns(review_text: str) -> bool: ...


class LLMGatewayProtocol(Protocol):
    """Contract for LLM text generation (single or parallel)."""

    async def generate(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...