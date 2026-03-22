"""Agent entities."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentDefinition:
    name: str
    workflow: str
    tools: list[str] = field(default_factory=list)