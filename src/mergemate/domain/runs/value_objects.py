"""Run-related value objects."""

from enum import StrEnum


class RunStatus(StrEnum):
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @classmethod
    def terminal_statuses(cls) -> frozenset["RunStatus"]:
        """Statuses that represent a terminal (final) run state."""
        return frozenset({cls.COMPLETED, cls.FAILED, cls.CANCELLED})

    @classmethod
    def skip_process_statuses(cls) -> frozenset["RunStatus"]:
        """Statuses for which a run should not be re-processed."""
        return frozenset({
            cls.COMPLETED, cls.FAILED, cls.CANCELLED,
            cls.RUNNING, cls.WAITING_TOOL,
        })


class RunStage(StrEnum):
    PLANNING = "planning"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    QUEUED_FOR_EXECUTION = "queued_for_execution"
    RETRIEVE_CONTEXT = "retrieve_context"
    EXECUTION = "execution"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    TESTING = "testing"
    REVIEW = "review"
    INTERNAL_REPLANNING = "internal_replanning"
    COMPLETED = "completed"


class RunJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunJobType(StrEnum):
    PLAN_RUN = "plan_run"
    EXECUTE_RUN = "execute_run"


def tool_stage(tool_name: str) -> str:
    return f"tool:{tool_name}"