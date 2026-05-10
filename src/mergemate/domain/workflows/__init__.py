"""Workflow definitions — stage types, workflow configuration, and validation hooks."""
from mergemate.domain.workflows.handlers import (
    StageHandler,
    get_stage_handler,
    register_handler,
)
from mergemate.domain.workflows.stage import (
    WorkflowDefinition,
    WorkflowStage,
    get_workflow_definitions,
)
from mergemate.domain.workflows.validation import (
    StageValidationHook,
    ValidationHook,
    get_validation_hooks,
    register_validation_hook,
    run_validation_hooks,
)

__all__ = [
    "StageHandler",
    "StageValidationHook",
    "ValidationHook",
    "WorkflowDefinition",
    "WorkflowStage",
    "get_stage_handler",
    "get_validation_hooks",
    "get_workflow_definitions",
    "register_handler",
    "register_validation_hook",
    "run_validation_hooks",
]