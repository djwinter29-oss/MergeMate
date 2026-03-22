"""Conversation context service placeholder."""


class ContextService:
    def __init__(self, conversation_repository) -> None:
        self._conversation_repository = conversation_repository

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self._conversation_repository.append_message(chat_id, role, content)

    def load_recent_messages(self, chat_id: int, limit: int = 8) -> list[dict[str, str]]:
        return self._conversation_repository.list_messages(chat_id, limit=limit)