"""Tool entities."""

from dataclasses import dataclass


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str


@dataclass(slots=True, frozen=True)
class ToolMetadata:
    name: str
    runtime_mode: str = "manual"
    default_action: str | None = None
    read_only: bool = False
    blocks_run_state: str | None = None
    context_key: str | None = None
    auth_action: str | None = None
    platform: str | None = None