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


def tool_stage(tool_name: str) -> str:
    return f"tool:{tool_name}"