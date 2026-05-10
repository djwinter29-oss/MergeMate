"""Service Protocols for structural (duck-typing) type checking.

All concrete service classes satisfy these Protocols via structural subtyping
— no explicit ``__subclasshook__`` or inheritance is needed.  This file
exists so that ``OrchestratorDependencies`` and ``ExecutionRuntime`` can be
type-annotated instead of using ``Any``.

Defined here:
    - ContextServiceProtocol
    - DocumentationServiceProtocol
    - LearningServiceProtocol
    - PlanningServiceProtocol
    - PromptServiceProtocol
    - ToolServiceProtocol
    - WorkflowServiceProtocol
    - LLMGatewayProtocol

See Also
--------
docs/architecture/service-protocols.md : Full design rationale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mergemate.domain.shared import RunStage


# ── ContextService ────────────────────────────────────────────────────────────


class ContextServiceProtocol(Protocol):
    """Protocol for ``ContextService`` — conversation history I/O."""

    def append_message(self, chat_id: int, role: str, content: str) -> None: ...

    def load_recent_messages(
        self,
        chat_id: int,
        limit: int = 8,
    ) -> list[dict[str, str]]: ...


# ── DocumentationService ──────────────────────────────────────────────────────


class DocumentationServiceProtocol(Protocol):
    """Protocol for ``DocumentationService`` — persist workflow docs."""

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


# ── LearningService ───────────────────────────────────────────────────────────


class LearningServiceProtocol(Protocol):
    """Protocol for ``LearningService`` — memory / lesson persistence."""

    async def remember_success(
        self,
        *,
        chat_id: int,
        workflow: str,
        prompt: str,
        result_text: str,
    ) -> None: ...

    def load_recent_learnings(
        self,
        chat_id: int,
    ) -> list[dict[str, str]]: ...

    def load_grouped_learnings(
        self,
        chat_id: int,
        current_workflow: str,
    ) -> list[dict[str, str]]: ...

    def load_repo_knowledge(
        self,
        chat_id: int,
        repo_name: str | None = None,
    ) -> list[dict[str, str]]: ...


# ── PlanningService ───────────────────────────────────────────────────────────


class PlanningServiceProtocol(Protocol):
    """Protocol for ``PlanningService`` — plan drafting and revision."""

    async def draft_plan(
        self,
        prompt: str,
        prior_feedback: str | None = None,
    ) -> str: ...

    async def revise_plan(
        self,
        existing_prompt: str,
        feedback: str,
    ) -> tuple[str, str]: ...


# ── PromptService ─────────────────────────────────────────────────────────────


class PromptServiceProtocol(Protocol):
    """Protocol for ``PromptService`` — system/user prompt assembly."""

    def render(
        self,
        workflow: str,
        recent_messages: list[dict[str, str]],
        learned_items: list[dict[str, str]],
        user_prompt: str,
        repo_knowledge: list[dict[str, str]] | None = None,
    ) -> tuple[str, str]: ...


# ── ToolService ───────────────────────────────────────────────────────────────


class ToolServiceProtocol(Protocol):
    """Protocol for ``ToolService`` — tool selection and invocation."""

    def list_enabled_tools(self, agent_name: str) -> list[str]: ...

    def execute_enabled_tool(
        self,
        agent_name: str,
        tool_name: str,
        payload: dict[str, str],
        *,
        run_id: str | None = None,
        resume_stage: str | RunStage = RunStage.RETRIEVE_CONTEXT,
    ) -> dict[str, str]: ...

    def install_package(self, package_name: str) -> dict[str, str]: ...

    async def build_runtime_tool_context_async(
        self,
        run_id: str,
        agent_name: str,
        *,
        resume_stage: str | RunStage = RunStage.RETRIEVE_CONTEXT,
    ) -> str: ...

    def get_repository_context(
        self,
        platform: str | None = None,
    ) -> dict[str, dict[str, str]]: ...

    def get_platform_auth_status(self, platform: str) -> dict[str, str]: ...


# ── WorkflowService ────────────────────────────────────────────────────────────


class WorkflowServiceProtocol(Protocol):
    """Protocol for ``WorkflowService`` — workflow orchestration prompts.

    Satisfied by the concrete ``WorkflowService`` via structural subtyping.
    """

    def build_execution_plan(
        self,
        workflow: str,
        *,
        agent_name: str,
    ) -> DirectExecutionPlan | MultiStageExecutionPlan: ...

    async def create_design(
        self,
        plan_text: str,
        context_text: str,
    ) -> str: ...

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


# ── LLMGateway ────────────────────────────────────────────────────────────────


class LLMGatewayProtocol(Protocol):
    """Protocol for ``ParallelLLMGateway`` — LLM text generation."""

    async def generate(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str: ...


# ── Forward references for WorkflowServiceProtocol return types ────────────────


# ``build_execution_plan`` returns types defined in ``execution_plan.py``.
# With ``from __future__ import annotations`` these are strings and never
# resolved at runtime, so there is no circular import issue.
# mypy resolves them via usual module-level import — we use ``TYPE_CHECKING``
# block to keep mypy happy without a runtime cycle.
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    from mergemate.application.execution_plan import (  # noqa: F401
        DirectExecutionPlan,
        MultiStageExecutionPlan,
    )