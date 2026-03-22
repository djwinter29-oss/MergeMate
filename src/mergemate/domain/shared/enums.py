"""Shared enums."""

from enum import StrEnum


class WorkflowName(StrEnum):
    GENERATE_CODE = "generate_code"
    DEBUG_CODE = "debug_code"
    EXPLAIN_CODE = "explain_code"