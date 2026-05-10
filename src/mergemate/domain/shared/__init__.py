"""Shared domain helpers."""

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

# NOTE: Business logic functions (is_user_facing_workflow, resolve_workflow_name,
# uses_multi_stage_delivery, workflow_prompt_file) moved to domain/policies/.
# Import from there instead: from mergemate.domain.policies import ...
#
# NOTE: MULTI_STAGE_WORKFLOWS is now derived from get_workflow_definitions()
# in domain/policies/__init__.py.  The value re-exported here is kept for
# backward compatibility but reflects the frozen state at import time.  New
# code should use policies.uses_multi_stage_delivery() or policies imports.

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
]
