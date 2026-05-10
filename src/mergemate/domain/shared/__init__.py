"""Shared domain helpers."""

from __future__ import annotations

import warnings as _warnings

from .enums import (
    MULTI_STAGE_WORKFLOWS,
    PROMPT_FILE_BY_WORKFLOW,
    USER_FACING_WORKFLOWS,
    WorkflowName,
)
from .exceptions import (
    AgentNotFoundError,
    AllProvidersFailedError,
    ConfigurationError,
    InvalidWebhookModeError,
    JobQueueError,
    MergeMateError,
    ParallelWorkerError,
    PersistenceError,
    ProviderError,
    ProviderNotFoundError,
    ProviderResponseError,
    RunError,
    RunNotFoundError,
    RunSubmissionError,
    SoulNotFoundError,
    SoulPermissionError,
    StageExecutionError,
    WorkerStoppedError,
    WorkflowNotFoundError,
    WorkflowRegistrationError,
)
from .value_objects import (
    RunJobStatus,
    RunJobType,
    RunStage,
    RunStatus,
    tool_stage,
)

# ── Deprecated re-exports from domain/policies ────────────────────────────
# These business-logic functions lived in enums.py and were migrated to
# mergemate.domain.policies.  The imports below provide a grace period for
# any code that hasn't been updated yet.  New code should import directly
# from mergemate.domain.policies.
#
# Use lazy imports to avoid circular imports (policies → shared.enums → shared).

def _get_policies() -> object:
    import importlib
    return importlib.import_module("mergemate.domain.policies")


def is_user_facing_workflow(*args: object, **kwargs: object) -> bool:
    _warnings.warn(
        "Import is_user_facing_workflow from mergemate.domain.policies instead of "
        "mergemate.domain.shared",
        DeprecationWarning,
        stacklevel=2,
    )
    return _get_policies().is_user_facing_workflow(*args, **kwargs)  # type: ignore[arg-type]


def resolve_workflow_name(*args: object, **kwargs: object) -> object:
    _warnings.warn(
        "Import resolve_workflow_name from mergemate.domain.policies instead of "
        "mergemate.domain.shared",
        DeprecationWarning,
        stacklevel=2,
    )
    return _get_policies().resolve_workflow_name(*args, **kwargs)  # type: ignore[arg-type]


def uses_multi_stage_delivery(*args: object, **kwargs: object) -> bool:
    _warnings.warn(
        "Import uses_multi_stage_delivery from mergemate.domain.policies instead of "
        "mergemate.domain.shared",
        DeprecationWarning,
        stacklevel=2,
    )
    return _get_policies().uses_multi_stage_delivery(*args, **kwargs)  # type: ignore[arg-type]


def workflow_prompt_file(*args: object, **kwargs: object) -> str:
    _warnings.warn(
        "Import workflow_prompt_file from mergemate.domain.policies instead of "
        "mergemate.domain.shared",
        DeprecationWarning,
        stacklevel=2,
    )
    return _get_policies().workflow_prompt_file(*args, **kwargs)  # type: ignore[arg-type]


__all__ = [
    "AgentNotFoundError",
    "AllProvidersFailedError",
    "ConfigurationError",
    "InvalidWebhookModeError",
    "JobQueueError",
    "MergeMateError",
    "MULTI_STAGE_WORKFLOWS",
    "ParallelWorkerError",
    "PersistenceError",
    "PROMPT_FILE_BY_WORKFLOW",
    "ProviderError",
    "ProviderNotFoundError",
    "ProviderResponseError",
    "RunError",
    "RunJobStatus",
    "RunJobType",
    "RunNotFoundError",
    "RunStage",
    "RunStatus",
    "RunSubmissionError",
    "SoulNotFoundError",
    "SoulPermissionError",
    "StageExecutionError",
    "USER_FACING_WORKFLOWS",
    "WorkerStoppedError",
    "WorkflowName",
    "WorkflowNotFoundError",
    "WorkflowRegistrationError",
    "tool_stage",
    "is_user_facing_workflow",
    "resolve_workflow_name",
    "uses_multi_stage_delivery",
    "workflow_prompt_file",
]
