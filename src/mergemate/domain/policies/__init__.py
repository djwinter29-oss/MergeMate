"""Workflow policies — business logic for workflow classification and routing.

These functions were historically co-located with the WorkflowName enum in
domain/shared/enums.py. Moving them to a separate policies subpackage makes
the distinction between pure data (enums) and decision-making logic (policies)
explicit, and resolves the import concern where config/ was importing logic
functions from the domain layer.
"""

from mergemate.domain.shared.enums import (
    PROMPT_FILE_BY_WORKFLOW,
    USER_FACING_WORKFLOWS,
    WorkflowName,
)
from mergemate.domain.workflows.stage import get_workflow_definitions  # noqa: F401


# ── Derive multi-stage workflows from definitions (single source of truth) ──

_MULTI_STAGE_WORKFLOWS = frozenset(
    get_workflow_definitions().keys(),
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
    return workflow_name in _MULTI_STAGE_WORKFLOWS


def is_user_facing_workflow(workflow: str | WorkflowName) -> bool:
    workflow_name = resolve_workflow_name(workflow)
    return workflow_name in USER_FACING_WORKFLOWS


def workflow_prompt_file(workflow: str | WorkflowName) -> str:
    workflow_name = resolve_workflow_name(workflow)
    if workflow_name is None:
        return "base.md"
    return PROMPT_FILE_BY_WORKFLOW.get(workflow_name, "base.md")


__all__ = [
    "resolve_workflow_name",
    "uses_multi_stage_delivery",
    "is_user_facing_workflow",
    "workflow_prompt_file",
    "get_workflow_definitions",
]