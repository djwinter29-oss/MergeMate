# mypy: allow-untyped-defs
"""Conversation context service placeholder."""

from typing import Any, cast


class ContextService:
    def __init__(self, conversation_repository: Any) -> None:
        self._conversation_repository = conversation_repository

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self._conversation_repository.append_message(chat_id, role, content)

    def load_recent_messages(self, chat_id: int, limit: int = 8) -> list[dict[str, str]]:
        return cast(
            list[dict[str, str]], self._conversation_repository.list_messages(chat_id, limit=limit)
        )
