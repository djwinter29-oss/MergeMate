"""Workflow policies — business logic for workflow classification and routing.

These functions were historically co-located with the WorkflowName enum in
domain/shared/enums.py. Moving them to a separate policies subpackage makes
the distinction between pure data (enums) and decision-making logic (policies)
explicit, and resolves the import concern where config/ was importing logic
functions from the domain layer.
"""

from mergemate.domain.shared.enums import (
    USER_FACING_WORKFLOWS,
    WorkflowName,
)
from mergemate.domain.workflows.registry import get_workflow

_PROMPT_FILE_BY_WORKFLOW: dict[WorkflowName, str] = {
    WorkflowName.GENERATE_CODE: "code_generation.md",
    WorkflowName.DEBUG_CODE: "debugging.md",
    WorkflowName.EXPLAIN_CODE: "explanation.md",
}


def resolve_workflow_name(workflow: str | WorkflowName) -> WorkflowName | None:
    if isinstance(workflow, WorkflowName):
        return workflow
    try:
        return WorkflowName(workflow)
    except ValueError:
        return None


def uses_multi_stage_delivery(workflow: str | WorkflowName) -> bool:
    """Check whether *workflow* has a multi-stage delivery definition.

    Tries ``WorkflowName`` resolution first (for known built-in workflows).
    If that fails the workflow may come from a plugin, so falls back to
    querying the registry with the raw string.
    """
    workflow_name = resolve_workflow_name(workflow)
    if workflow_name is not None:
        return get_workflow(workflow_name.value) is not None
    # Plugin workflows that aren't in the WorkflowName enum — try raw string.
    if isinstance(workflow, str):
        return get_workflow(workflow) is not None
    return False


def is_user_facing_workflow(workflow: str | WorkflowName) -> bool:
    workflow_name = resolve_workflow_name(workflow)
    return workflow_name in USER_FACING_WORKFLOWS


def workflow_prompt_file(workflow: str | WorkflowName) -> str:
    workflow_name = resolve_workflow_name(workflow)
    if workflow_name is None:
        return "base.md"
    return _PROMPT_FILE_BY_WORKFLOW.get(workflow_name, "base.md")


__all__ = [
    "resolve_workflow_name",
    "uses_multi_stage_delivery",
    "is_user_facing_workflow",
    "workflow_prompt_file",
    "get_workflow",
]
