"""Learning memory service backed by persisted successful runs."""


class LearningService:
    def __init__(self, learning_repository, enabled: bool, max_context_items: int, max_result_chars: int) -> None:
        self._learning_repository = learning_repository
        self._enabled = enabled
        self._max_context_items = max_context_items
        self._max_result_chars = max_result_chars

    def remember_success(self, *, chat_id: int, workflow: str, prompt: str, result_text: str) -> None:
        if not self._enabled:
            return
        excerpt = result_text.strip()[: self._max_result_chars]
        self._learning_repository.record(chat_id, workflow, prompt, excerpt)

    def load_recent_learnings(self, chat_id: int) -> list[dict[str, str]]:
        if not self._enabled:
            return []
        return self._learning_repository.list_recent(chat_id, limit=self._max_context_items)