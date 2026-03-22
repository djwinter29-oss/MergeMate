"""Tool entities."""

from dataclasses import dataclass


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str