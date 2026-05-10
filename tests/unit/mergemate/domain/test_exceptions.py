"""Tests for domain exception hierarchy — isinstance verification."""

import inspect

import pytest

from mergemate.domain.shared import exceptions as exc_mod
from mergemate.domain.shared.exceptions import (
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
)


def _all_exception_classes() -> list[type]:
    """Return all exception classes defined in the exceptions module."""
    return [
        obj
        for _, obj in inspect.getmembers(exc_mod, inspect.isclass)
        if issubclass(obj, Exception) and obj.__module__ == exc_mod.__name__
    ]


ALL_EXCEPTIONS = _all_exception_classes()


# ── Exception hierarchy: every exception must be an isinstance match ──────


@pytest.mark.parametrize(
    ("exc_cls", "expected_base"),
    [
        # Root
        (MergeMateError, Exception),
        # Configuration errors — all branch from ConfigurationError → ValueError
        (ConfigurationError, ValueError),
        (AgentNotFoundError, ConfigurationError),
        (AgentNotFoundError, ValueError),
        (ProviderNotFoundError, ConfigurationError),
        (ProviderNotFoundError, ValueError),
        (WorkflowNotFoundError, ConfigurationError),
        # Run errors — all branch from RunError → ValueError
        (RunError, ValueError),
        (RunNotFoundError, RunError),
        (RunNotFoundError, ValueError),
        (RunSubmissionError, RunError),
        (StageExecutionError, RunError),
        (ParallelWorkerError, RunError),
        # Soul errors — branch from MergeMateError directly
        (SoulPermissionError, MergeMateError),
        (SoulNotFoundError, MergeMateError),
        # Provider errors — all branch from ProviderError → ValueError
        (ProviderError, ValueError),
        (ProviderResponseError, ProviderError),
        (ProviderResponseError, ValueError),
        (AllProvidersFailedError, ProviderError),
        (AllProvidersFailedError, ValueError),
        # Persistence
        (PersistenceError, MergeMateError),
        # Infrastructure errors
        (JobQueueError, MergeMateError),
        (WorkerStoppedError, JobQueueError),
        (WorkerStoppedError, MergeMateError),
        # Interface errors
        (InvalidWebhookModeError, MergeMateError),
    ],
)
def test_isinstance_hierarchy(exc_cls: type, expected_base: type) -> None:
    """Every exception class correctly inherits from its expected base."""
    instance = exc_cls("test message")
    assert isinstance(instance, expected_base), (
        f"{exc_cls.__name__}('test') is not isinstance of {expected_base.__name__}"
    )


# ── Direct instantiation and string representation ───────────────────────


@pytest.mark.parametrize("exc_cls", ALL_EXCEPTIONS)
def test_exception_message_is_preserved(exc_cls: type) -> None:
    """Every exception stores and returns its message."""
    instance = exc_cls("something went wrong")
    assert str(instance) == "something went wrong"
    assert instance.args[0] == "something went wrong"


# ── No leaf inherits from the wrong branch ──────────────────────────────


def test_configuration_error_not_a_run_error() -> None:
    """Configuration errors are not RunErrors."""
    assert not issubclass(ConfigurationError, RunError)
    assert not issubclass(AgentNotFoundError, RunError)
    assert not issubclass(ProviderNotFoundError, RunError)
    assert not issubclass(WorkflowNotFoundError, RunError)


def test_run_error_not_configuration_error() -> None:
    """Run errors are not ConfigurationError."""
    assert not issubclass(RunError, ConfigurationError)
    assert not issubclass(RunNotFoundError, ConfigurationError)
    assert not issubclass(StageExecutionError, ConfigurationError)
    assert not issubclass(ParallelWorkerError, ConfigurationError)


def test_soul_errors_are_not_value_error() -> None:
    """Soul permission errors are MergeMateError directly, not ValueError."""
    assert not issubclass(SoulPermissionError, ValueError)
    assert not issubclass(SoulNotFoundError, ValueError)


def test_job_queue_error_is_not_value_error() -> None:
    """JobQueueError and WorkerStoppedError are MergeMateError directly."""
    assert not issubclass(JobQueueError, ValueError)
    assert not issubclass(WorkerStoppedError, ValueError)


def test_invalid_webhook_mode_error_is_not_value_error() -> None:
    """InvalidWebhookModeError is MergeMateError, not ValueError."""
    assert not issubclass(InvalidWebhookModeError, ValueError)


def test_persistence_error_is_not_value_error() -> None:
    """PersistenceError is MergeMateError, not ValueError."""
    assert not issubclass(PersistenceError, ValueError)


# ── All exception classes are importable from the module ──────────────────


def test_exception_classes_list() -> None:
    """All expected exception classes are importable from the exceptions module."""
    expected_classes = {
        "MergeMateError",
        "ConfigurationError",
        "AgentNotFoundError",
        "ProviderNotFoundError",
        "WorkflowNotFoundError",
        "RunError",
        "RunNotFoundError",
        "RunSubmissionError",
        "StageExecutionError",
        "ParallelWorkerError",
        "SoulPermissionError",
        "SoulNotFoundError",
        "ProviderError",
        "ProviderResponseError",
        "AllProvidersFailedError",
        "PersistenceError",
        "JobQueueError",
        "WorkerStoppedError",
        "InvalidWebhookModeError",
        "WorkflowRegistrationError",
    }
    imported_names = {c.__name__ for c in ALL_EXCEPTIONS}
    assert imported_names == expected_classes