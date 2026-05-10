"""Post-stage validation hooks for workflow execution.

Validation hooks provide a mechanism to inspect stage outputs
after a handler completes.  They are registered per handler key
(e.g. ``"implementation"``, ``"testing"``) and called in
registration order.  If any hook returns ``False``, the stage
fails validation.

Usage::

    from mergemate.domain.workflows.validation import register_validation_hook

    async def no_empty_artifacts(stage_name: str, artifacts: dict) -> bool:
        return bool(artifacts.get("result_text", "").strip())

    register_validation_hook("implementation", no_empty_artifacts)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ValidationHook(Protocol):
    """Post-stage validation protocol.

    ``stage_name`` is the human-readable name from ``WorkflowStage.name``.
    ``artifacts`` is the shared artifacts dict (read-only view).
    Returns ``True`` if the stage output is acceptable.
    If ``False``, the execution plan may retry the stage or abort
    depending on plan policy.
    """

    async def __call__(
        self,
        stage_name: str,
        artifacts: dict[str, Any],
    ) -> bool: ...


# Type alias for registration
StageValidationHook = Callable[[str, dict[str, Any]], Awaitable[bool]]


_VALIDATION_HOOKS: dict[str, list[StageValidationHook]] = {}


def register_validation_hook(stage_handler_key: str, hook: StageValidationHook) -> None:
    """Register a validation hook for all stages using *stage_handler_key*.

    ``stage_handler_key`` is the ``WorkflowStage.handler`` value
    (e.g. ``"implementation"``, ``"testing"``).

    Hooks are called in registration order.  All hooks must return
    ``True`` for the stage to pass validation.

    Can be called from entry-point execution at startup.
    """
    _VALIDATION_HOOKS.setdefault(stage_handler_key, []).append(hook)


def get_validation_hooks(stage_handler_key: str) -> list[StageValidationHook]:
    """Return hooks registered for a given handler key, in order."""
    return list(_VALIDATION_HOOKS.get(stage_handler_key, []))


async def run_validation_hooks(
    stage_handler_key: str,
    stage_name: str,
    artifacts: dict[str, Any],
) -> bool:
    """Run all hooks for *stage_handler_key*.

    Returns ``True`` when all hooks pass; ``False`` (and stops) on
    the first hook that returns ``False``.
    """
    for hook in _VALIDATION_HOOKS.get(stage_handler_key, []):
        if not await hook(stage_name, artifacts):
            return False
    return True