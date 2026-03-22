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