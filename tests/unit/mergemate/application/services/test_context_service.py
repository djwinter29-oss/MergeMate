from mergemate.application.services.context_service import ContextService


class ConversationRepositoryStub:
    def __init__(self) -> None:
        self.appended = []

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self.appended.append((chat_id, role, content))

    def list_messages(self, chat_id: int, limit: int = 8):
        return [{"role": "user", "content": f"message-{chat_id}-{limit}"}]


def test_append_message_delegates_to_repository() -> None:
    repository = ConversationRepositoryStub()
    service = ContextService(repository)

    service.append_message(1, "assistant", "hello")

    assert repository.appended == [(1, "assistant", "hello")]


def test_load_recent_messages_delegates_limit() -> None:
    repository = ConversationRepositoryStub()
    service = ContextService(repository)

    result = service.load_recent_messages(9, limit=3)

    assert result == [{"role": "user", "content": "message-9-3"}]
