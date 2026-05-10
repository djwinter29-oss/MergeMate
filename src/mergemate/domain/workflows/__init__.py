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

# ── Auto-register built-in workflows into the live registry at import time ─
# This ensures that uses_multi_stage_delivery() and other policy functions
# that query the registry find the built-in workflows without explicit
# bootstrap wiring.  Plugin workflows registered later via entry points or
# config are appended on top.

from mergemate.domain.workflows.stage import _BUILTIN_WORKFLOWS as _builtin_wfs  # noqa: E402

for _wf_name, _wf_def in _builtin_wfs.items():
    try:
        register_workflow(_wf_name.value, _wf_def)
    except KeyError:
        pass  # Already registered by an earlier import — not an error.
