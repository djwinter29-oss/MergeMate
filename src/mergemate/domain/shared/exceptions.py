"""Domain-specific exception hierarchy for MergeMate.

All exceptions raised by the application layer should inherit from
these base types instead of using raw ``ValueError`` / ``RuntimeError``.
"""


class MergeMateError(Exception):
    """Base exception for all MergeMate errors."""


# ── Configuration errors ──────────────────────────────────────────────


class ConfigurationError(ValueError):
    """Invalid or missing configuration."""


class AgentNotFoundError(ConfigurationError):
    """Referenced agent is not configured."""


class ProviderNotFoundError(ConfigurationError):
    """Referenced provider is not configured."""


class WorkflowNotFoundError(ConfigurationError):
    """No agent found for the requested workflow."""


# ── Run / execution errors ───────────────────────────────────────────


class RunError(ValueError):
    """Base for run-related errors."""


class RunNotFoundError(RunError):
    """Requested run does not exist."""


class RunSubmissionError(RunError):
    """Run submission or approval failed."""


class StageExecutionError(RunError):
    """A workflow stage failed during execution."""


class ParallelWorkerError(RunError):
    """All parallel workers for a stage failed."""


# ── Soul / permission errors ─────────────────────────────────────────


class SoulPermissionError(MergeMateError):
    """A role attempted to write to a directory its Soul does not permit."""


class SoulNotFoundError(MergeMateError):
    """Referenced Soul name is not registered."""


# ── LLM / provider errors ────────────────────────────────────────────


class ProviderError(ValueError):
    """Base for LLM provider errors."""


class ProviderResponseError(ProviderError):
    """Provider returned an unexpected or invalid response."""


class AllProvidersFailedError(ProviderError):
    """All parallel provider calls failed."""


# ── Persistence errors ───────────────────────────────────────────────


class PersistenceError(MergeMateError):
    """Base for persistence-layer errors."""


# ── Infrastructure errors ────────────────────────────────────────────


class JobQueueError(MergeMateError):
    """Background job could not be queued or dispatched."""


class WorkerStoppedError(JobQueueError):
    """Background worker is stopping and cannot accept new runs."""


# ── Interface errors ─────────────────────────────────────────────────


class InvalidWebhookModeError(MergeMateError):
    """Readiness probing requires webhook mode."""


# ── Compatibility mapping ────────────────────────────────────────────

# Map old exception patterns to new for incremental migration.
# These can be imported and raised in place of bare ValueError/RuntimeError.

# Old → New
# ValueError → ConfigurationError / RunNotFoundError (context-dependent)
# RuntimeError → ProviderResponseError / JobQueueError / ParallelWorkerError