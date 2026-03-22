"""Conversation repository contract."""

from typing import Protocol

from mergemate.domain.conversations.entities import Conversation


class ConversationRepository(Protocol):
    def save(self, conversation: Conversation) -> None: ...

    def get(self, chat_id: int) -> Conversation | None: ...