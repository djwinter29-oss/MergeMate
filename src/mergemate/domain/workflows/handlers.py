"""Stage handler protocol and built-in handler registry.

Each ``WorkflowStage`` declares a ``handler`` key that maps to an
execution function in this module.  The ``MultiStageExecutionPlan``
uses ``get_stage_handler(stage.handler)`` to dispatch execution logic
generically — no hardcoded stage chains.

Handler function signature::

    async def handler_fn(
        runtime: HandlerContext,
        artifacts: dict[str, Any],
        *,
        agent_name: str,
    ) -> dict[str, Any]:
        ...

The ``artifacts`` dict carries accumulated outputs from prior stages
(e.g. ``{"plan_text": ..., "design_text": ..., "context_text": ...}``).
The handler mutates it and returns it.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


# ── Public API ─────────────────────────────────────────────────────────────

__all__ = [
    "StageHandler",
    "HandlerContext",
    "get_stage_handler",
    "register_handler",
]


# ── Handler Context Protocol ────────────────────────────────────────────────


@runtime_checkable
class HandlerContext(Protocol):
    """Minimal protocol satisfied by ``ExecutionRuntime``.

    Domain-layer handlers depend on this protocol rather than on the
    concrete ``ExecutionRuntime`` type, keeping the ``domain`` package
    free of ``application`` imports.
    """

    @property
    def deps(self) -> Any:
        """Dependency container (``OrchestratorDependencies``)."""
        ...


# ── Handler Protocol ───────────────────────────────────────────────────────


class StageHandler(Protocol):
    """Protocol for async stage handler functions."""

    async def __call__(
        self,
        runtime: HandlerContext,
        artifacts: dict[str, Any],
        *,
        agent_name: str,
    ) -> dict[str, Any]: ...


# ── Handler registry ───────────────────────────────────────────────────────

_HANDLERS: dict[str, StageHandler] = {}


def register_handler(key: str) -> Callable[[StageHandler], StageHandler]:
    """Decorator that registers an async handler function under *key*."""

    def _decorator(fn: StageHandler) -> StageHandler:
        _HANDLERS[key] = fn
        return fn

    return _decorator


def get_stage_handler(key: str) -> StageHandler | None:
    """Look up a handler by its registered key.

    Returns ``None`` when the key is unknown (the execution plan will
    raise a clear error).
    """
    return _HANDLERS.get(key)


# ── Built-in handlers ──────────────────────────────────────────────────────


@register_handler("design")
async def _handle_design(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    *,
    agent_name: str,
) -> dict[str, Any]:
    """Architecture design stage: produce a design from the plan + context."""
    design_text = await runtime.deps.workflow_service.create_design(
        artifacts["plan_text"],
        artifacts["context_text"],
    )
    _save_document(
        runtime, artifacts, "architecture", design_text=design_text, agent_name=agent_name
    )
    _persist_artifacts(
        runtime,
        artifacts,
        current_stage="design",
        design_text=design_text,
        review_iterations=artifacts.get("_iteration", 0),
    )
    artifacts["design_text"] = design_text
    return artifacts


@register_handler("implementation")
async def _handle_implementation(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    *,
    agent_name: str,
) -> dict[str, Any]:
    """Code generation stage: implement based on plan + design + context."""
    implementation_text = await runtime.deps.workflow_service.generate_code(
        artifacts["plan_text"],
        artifacts.get("design_text", ""),
        artifacts["context_text"],
        agent_name=agent_name,
    )
    _persist_artifacts(
        runtime,
        artifacts,
        current_stage="implementation",
        result_text=implementation_text,
        review_iterations=artifacts.get("_iteration", 0),
    )
    artifacts["implementation_text"] = implementation_text
    return artifacts


@register_handler("testing")
async def _handle_testing(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    *,
    agent_name: str,
) -> dict[str, Any]:
    """Test generation stage: produce tests from plan + design + implementation."""
    test_text = await runtime.deps.workflow_service.generate_tests(
        artifacts["plan_text"],
        artifacts.get("design_text", ""),
        artifacts.get("implementation_text", ""),
    )
    _save_document(runtime, artifacts, "testing", test_text=test_text, agent_name=agent_name)
    _persist_artifacts(
        runtime,
        artifacts,
        current_stage="testing",
        test_text=test_text,
        review_iterations=artifacts.get("_iteration", 0),
    )
    artifacts["test_text"] = test_text
    return artifacts


@register_handler("review")
async def _handle_review(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    *,
    agent_name: str,
) -> dict[str, Any]:
    """Code review stage: evaluate design + implementation + tests."""
    review_text = await runtime.deps.workflow_service.review(
        artifacts["plan_text"],
        artifacts.get("design_text", ""),
        artifacts.get("implementation_text", ""),
        artifacts.get("test_text", ""),
    )
    _save_document(runtime, artifacts, "review", review_text=review_text, agent_name=agent_name)
    _persist_artifacts(
        runtime,
        artifacts,
        current_stage="review",
        review_text=review_text,
        review_iterations=artifacts.get("_iteration", 0),
    )
    artifacts["review_text"] = review_text
    return artifacts


@register_handler("replanning")
async def _handle_replanning(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    *,
    agent_name: str,
) -> dict[str, Any]:
    """Replanning stage: generate a revised plan from review feedback."""
    prior_feedback = artifacts.get("review_text", "")
    new_plan = await runtime.deps.planning_service.draft_plan(
        artifacts["run_prompt"],
        prior_feedback=prior_feedback,
    )
    runtime.deps.run_repository.update_plan(
        artifacts["run_id"],
        new_plan,
        current_stage="internal_replanning",
    )
    artifacts["plan_text"] = new_plan
    return artifacts


@register_handler("chronicle")
async def _handle_chronicle(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    *,
    agent_name: str,
) -> dict[str, Any]:
    """Chronicle stage: record lessons learned from the workflow run."""
    lesson_text = await runtime.deps.workflow_service.record_lesson(
        plan_text=artifacts.get("plan_text", ""),
        design_text=artifacts.get("design_text", ""),
        implementation_text=artifacts.get("implementation_text", ""),
        test_text=artifacts.get("test_text", ""),
        review_text=artifacts.get("review_text", ""),
        result_text=artifacts.get("result_text", ""),
        agent_name=agent_name,
    )
    _save_document(runtime, artifacts, "lessons", lesson_text=lesson_text, agent_name=agent_name)
    _persist_artifacts(
        runtime,
        artifacts,
        current_stage="chronicle",
        lesson_text=lesson_text,
        review_iterations=artifacts.get("_iteration", 0),
    )
    artifacts["lesson_text"] = lesson_text
    return artifacts


@register_handler("direct")
async def _handle_direct(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    *,
    agent_name: str,
) -> dict[str, Any]:
    """Direct execution stage: single-shot LLM call without sub-stages."""
    direct_result = await runtime.deps.workflow_service.execute_direct(
        agent_name,
        artifacts.get("system_prompt", ""),
        artifacts.get("context_text", ""),
    )
    _persist_artifacts(
        runtime,
        artifacts,
        current_stage="execution",
        result_text=direct_result,
    )
    artifacts["result_text"] = direct_result
    artifacts["_is_direct"] = True
    return artifacts


# ── Document kind registry ────────────────────────────────────────────

DocumentSaver = Callable[..., None]
_DOCUMENT_KINDS: dict[str, DocumentSaver] = {}


def register_document_kind(kind: str) -> Callable[[DocumentSaver], DocumentSaver]:
    """Decorator that registers a document-saver function under *kind*."""

    def _decorator(fn: DocumentSaver) -> DocumentSaver:
        if kind in _DOCUMENT_KINDS:
            warnings.warn(
                f"Document kind {kind!r} already registered by "
                f"{_DOCUMENT_KINDS[kind].__module__}.{_DOCUMENT_KINDS[kind].__qualname__}; "
                f"overwriting with {fn.__module__}.{fn.__qualname__}.",
                stacklevel=2,
            )
        _DOCUMENT_KINDS[kind] = fn
        return fn

    return _decorator


# ── Document kind savers ─────────────────────────────────────────────────


@register_document_kind("architecture")
def _save_architecture_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_architecture_design(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            design_text=extra.get("design_text", ""),
            role_name=agent_name,
        ),
        "_design_document_path",
    )


@register_document_kind("testing")
def _save_testing_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_test_plan(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            design_text=extra.get("design_text", ""),
            test_text=extra.get("test_text", ""),
            role_name=agent_name,
        ),
        "_test_document_path",
    )


@register_document_kind("review")
def _save_review_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_review_report(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            design_text=extra.get("design_text", ""),
            implementation_text=extra.get("implementation_text", ""),
            test_text=extra.get("test_text", ""),
            review_text=extra.get("review_text", ""),
            role_name=agent_name,
        ),
        "_review_document_path",
    )


@register_document_kind("lessons")
def _save_lessons_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_lesson(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            lesson_text=extra.get("lesson_text", ""),
            role_name=agent_name,
        ),
        "_lesson_document_path",
    )


# ── Helpers ────────────────────────────────────────────────────────────────


def _persist_artifacts(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    **kwargs: Any,
) -> None:
    """Persist stage artifacts through the run repository."""
    runtime.deps.run_repository.save_artifacts(
        artifacts["run_id"],
        **kwargs,
    )


def _save_to_artifacts(
    artifacts: dict[str, Any],
    path: Path,
    artifact_key: str,
) -> None:
    """Store a document path in artifacts under the appropriate key."""
    artifacts[artifact_key] = str(path)


def _save_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    """Write a documentation artifact and store its path in ``artifacts``.

    Dispatches to the registered saver via ``_DOCUMENT_KINDS``.
    New document kinds register themselves with ``@register_document_kind``
    instead of adding branches here.
    """
    saver = _DOCUMENT_KINDS.get(kind)
    if saver is None:
        raise ValueError(
            f"Unknown document kind {kind!r}. Registered kinds: {sorted(_DOCUMENT_KINDS)}"
        )
    saver(runtime, artifacts, kind, agent_name=agent_name, **extra)
