"""Conversation entities."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class Conversation:
    chat_id: int
    messages: list[str] = field(default_factory=list)