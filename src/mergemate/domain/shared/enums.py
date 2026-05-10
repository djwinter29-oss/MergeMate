"""Shared enums — workflow names and workflow-related data constants only.

Business logic functions (resolve_workflow_name, uses_multi_stage_delivery,
is_user_facing_workflow, workflow_prompt_file) have been moved to
``mergemate.domain.policies``. Import them from there instead.
"""

import warnings
from enum import StrEnum


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

MULTI_STAGE_WORKFLOWS = frozenset({WorkflowName.GENERATE_CODE})
warnings.warn(
    "MULTI_STAGE_WORKFLOWS is deprecated. Use "
    "domain/workflows/registry or "
    "domain/policies/uses_multi_stage_delivery() instead.",
    DeprecationWarning,
    stacklevel=2,
)

PROMPT_FILE_BY_WORKFLOW = {
    WorkflowName.GENERATE_CODE: "code_generation.md",
    WorkflowName.DEBUG_CODE: "debugging.md",
    WorkflowName.EXPLAIN_CODE: "explanation.md",
}
warnings.warn(
    "PROMPT_FILE_BY_WORKFLOW is deprecated. Use "
    "domain/workflows/registry or "
    "domain/policies/resolve_prompt_file() instead.",
    DeprecationWarning,
    stacklevel=2,
)

