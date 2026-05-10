"""Validation hook protocol and hook management system.

Validation hooks are an extension point that allows external code to inject
arbitrary stage-level validation logic without modifying the core workflow
engine.  In Phase 1, validation is advisory only — a failing hook produces
a warning log entry but does **not** abort the stage.

Usage::

    from mergemate.domain.workflows.validation import register_validation_hook

    async def check_api_key(stage_name: str, artifacts: dict[str, Any]) -> bool:
        return "api_key" in artifacts.get("config", {})

    register_validation_hook("design", check_api_key)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ── Type aliases ──────────────────────────────────────────────────────────────

StageValidationHook = Callable[[str, dict[str, Any]], Awaitable[bool]]
"""Signature: ``async def hook(stage_name, artifacts) -> bool``.

Return ``True`` to signal validation passed; ``False`` signals a problem.
"""


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class ValidationHook(Protocol):
    """Protocol for validation hook implementations.

    Any callable matching this signature can be registered as a hook,
    including classes with an ``async def __call__`` method or plain async
    functions (the ``StageValidationHook`` type alias accommodates both).
    """

    async def __call__(self, stage_name: str, artifacts: dict[str, Any]) -> bool:
        """Validate the current stage's artifacts.

        Args:
            stage_name:  Human-readable name of the stage being validated
                         (e.g. ``"design"``, ``"implementation"``).
            artifacts:   Accumulated artifacts dict produced by prior stages
                         and the current runtime context.

        Returns:
            ``True`` when the stage passes validation; ``False`` otherwise.
        """
        ...


# ── Module-level registry ────────────────────────────────────────────────────

_VALIDATION_HOOKS: dict[str, list[StageValidationHook]] = {}
"""Maps a stage-handler key to a list of registered validation hooks.

The key matches the ``handler`` attribute of ``WorkflowStage`` (e.g.
``"design"``, ``"implementation"``, ``"testing"``).  Hooks are called
in registration order.
"""


# ── Public API ────────────────────────────────────────────────────────────────


def register_validation_hook(
    stage_handler_key: str,
    hook: StageValidationHook,
) -> None:
    """Register a validation hook for the given stage-handler key.

    Hooks are stored per ``stage_handler_key`` in registration order.
    Multiple hooks for the same key are supported.

    Args:
        stage_handler_key:  Handler key this hook applies to (e.g. ``"design"``).
        hook:               Async callable matching ``StageValidationHook``.
    """
    _VALIDATION_HOOKS.setdefault(stage_handler_key, []).append(hook)
    logger.debug(
        "Registered validation hook %s for stage handler %r",
        getattr(hook, "__name__", hook),
        stage_handler_key,
    )


def get_validation_hooks(
    stage_handler_key: str,
) -> list[StageValidationHook]:
    """Return all validation hooks registered for the given handler key.

    Args:
        stage_handler_key:  Handler key to look up.

    Returns:
        A list of registered hooks (empty list if none are registered).
    """
    return list(_VALIDATION_HOOKS.get(stage_handler_key, []))


async def run_validation_hooks(
    stage_handler_key: str,
    stage_name: str,
    artifacts: dict[str, Any],
) -> bool:
    """Run all validation hooks registered for *stage_handler_key*.

    Hooks are called in registration order.  On the first hook that returns
    ``False``, a warning is logged and ``False`` is returned immediately
    (remaining hooks are **not** executed).

    .. note::

        In Phase 1 validation hooks are advisory.  The execution plan logs
        a warning on failure but continues the stage normally.

    Args:
        stage_handler_key:  Key passed to :func:`register_validation_hook`.
        stage_name:         Current stage name (passed to each hook).
        artifacts:          Current artifacts dict (passed to each hook).

    Returns:
        ``True`` if every hook passed; ``False`` if any hook failed.
    """
    hooks = _VALIDATION_HOOKS.get(stage_handler_key, [])
    if not hooks:
        return True

    for hook in hooks:
        try:
            ok = await hook(stage_name, artifacts)
        except Exception:
            logger.exception(
                "Validation hook %s raised an exception for stage %r (handler=%r) — "
                "treating as failure",
                getattr(hook, "__name__", hook),
                stage_name,
                stage_handler_key,
            )
            return False

        if not ok:
            logger.warning(
                "Validation hook %s rejected stage %r (handler=%r) — advisory only, continuing",
                getattr(hook, "__name__", hook),
                stage_name,
                stage_handler_key,
            )
            return False

    return True