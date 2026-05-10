"""Shared enums and workflow helpers."""

from enum import StrEnum

import warnings as _warnings


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

_warnings.warn(
    "MULTI_STAGE_WORKFLOWS is deprecated. Use domain/workflows/registry "
    "or domain/policies/uses_multi_stage_delivery() instead.",
    DeprecationWarning,
    stacklevel=2,
)

PROMPT_FILE_BY_WORKFLOW = {
    WorkflowName.GENERATE_CODE: "code_generation.md",
    WorkflowName.DEBUG_CODE: "debugging.md",
    WorkflowName.EXPLAIN_CODE: "explanation.md",
}

_warnings.warn(
    "PROMPT_FILE_BY_WORKFLOW is deprecated. Use domain/workflows/registry "
    "to look up prompt files by workflow name instead.",
    DeprecationWarning,
    stacklevel=2,
)


def resolve_workflow_name(workflow: str | WorkflowName) -> WorkflowName | None:
    if isinstance(workflow, WorkflowName):
        return workflow
    try:
        return WorkflowName(workflow)
    except ValueError:
        return None


def uses_multi_stage_delivery(workflow: str | WorkflowName) -> bool:
    workflow_name = resolve_workflow_name(workflow)
    return workflow_name in MULTI_STAGE_WORKFLOWS


def is_user_facing_workflow(workflow: str | WorkflowName) -> bool:
    workflow_name = resolve_workflow_name(workflow)
    return workflow_name in USER_FACING_WORKFLOWS


def workflow_prompt_file(workflow: str | WorkflowName) -> str:
    workflow_name = resolve_workflow_name(workflow)
    if workflow_name is None:
        return "base.md"
    return PROMPT_FILE_BY_WORKFLOW.get(workflow_name, "base.md")
