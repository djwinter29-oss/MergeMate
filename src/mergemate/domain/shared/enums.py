"""Shared enums — workflow names and workflow-related data constants only.

Business logic functions (resolve_workflow_name, uses_multi_stage_delivery,
is_user_facing_workflow, workflow_prompt_file) have been moved to
``mergemate.domain.policies``. Import them from there instead.
"""

import warnings
from enum import StrEnum
from typing import Any


class WorkflowName(StrEnum):
    PLANNING = "planning"
    DESIGN = "design"
    GENERATE_CODE = "generate_code"
    DEBUG_CODE = "debug_code"
    EXPLAIN_CODE = "explain_code"
    TESTING = "testing"
    REVIEW = "review"
    LEARNING = "learning"


USER_FACING_WORKFLOWS = frozenset(
    {
        WorkflowName.GENERATE_CODE,
        WorkflowName.DEBUG_CODE,
        WorkflowName.EXPLAIN_CODE,
    }
)

_DEPRECATED_EXPORTS: dict[str, Any] = {
    "MULTI_STAGE_WORKFLOWS": frozenset({WorkflowName.GENERATE_CODE}),
    "PROMPT_FILE_BY_WORKFLOW": {
        WorkflowName.GENERATE_CODE: "code_generation.md",
        WorkflowName.DEBUG_CODE: "debugging.md",
        WorkflowName.EXPLAIN_CODE: "explanation.md",
    },
}


def __getattr__(name: str) -> Any:
    """Lazily expose deprecated compatibility aliases.

    The values are still available for backward compatibility, but we only
    emit the deprecation warning when callers actually access the alias.
    """

    if name in _DEPRECATED_EXPORTS:
        warnings.warn(
            f"{name} is deprecated. Use domain/workflows/registry or "
            "domain/policies helpers instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        value = _DEPRECATED_EXPORTS[name]
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
