"""Workflow definitions — stage types, workflow configuration,
handler registry, and validation hooks.

Public symbols
--------------
**From registry.py:**
    register_workflow, get_workflow, get_all_workflows, known_workflow_names

**From validation.py:**
    ValidationHook, StageValidationHook, register_validation_hook,
    run_validation_hooks, get_validation_hooks

**From handlers.py:**
    StageHandler, register_handler, get_stage_handler
"""

from __future__ import annotations

from mergemate.domain.workflows.handlers import (
    StageHandler,
    get_stage_handler,
    register_handler,
)
from mergemate.domain.workflows.registry import (
    get_all_workflows,
    get_workflow,
    known_workflow_names,
    register_workflow,
)
from mergemate.domain.workflows.validation import (
    StageValidationHook,
    ValidationHook,
    get_validation_hooks,
    register_validation_hook,
    run_validation_hooks,
)

__all__ = [
    # registry
    "register_workflow",
    "get_workflow",
    "get_all_workflows",
    "known_workflow_names",
    # validation
    "ValidationHook",
    "StageValidationHook",
    "register_validation_hook",
    "run_validation_hooks",
    "get_validation_hooks",
    # handlers
    "StageHandler",
    "register_handler",
    "get_stage_handler",
]

# ── Register built-in workflows ────────────────────────────────────────────
# Deferred to after all submodules are imported to avoid circular imports
# between stage.py (defines WorkflowDefinition) and registry.py (imports it).

from mergemate.domain.workflows.stage import _register_builtin_workflows  # type: ignore[attr-defined]  # noqa: E402

_register_builtin_workflows()
