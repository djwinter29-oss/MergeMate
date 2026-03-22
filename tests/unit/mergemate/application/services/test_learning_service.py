from mergemate.application.services.learning_service import LearningService


class LearningRepositoryStub:
    def __init__(self) -> None:
        self.recorded = []

    def record(self, chat_id: int, workflow: str, prompt: str, result_excerpt: str) -> None:
        self.recorded.append((chat_id, workflow, prompt, result_excerpt))

    def list_recent(self, chat_id: int, limit: int = 3):
        return [{"workflow": "generate_code", "prompt": "p", "result_excerpt": f"{chat_id}-{limit}"}]


def test_remember_success_truncates_and_records_when_enabled() -> None:
    repository = LearningRepositoryStub()
    service = LearningService(repository, enabled=True, max_context_items=2, max_result_chars=5)

    service.remember_success(chat_id=1, workflow="generate_code", prompt="prompt", result_text=" 123456 ")

    assert repository.recorded == [(1, "generate_code", "prompt", "12345")]


def test_remember_success_skips_when_disabled() -> None:
    repository = LearningRepositoryStub()
    service = LearningService(repository, enabled=False, max_context_items=2, max_result_chars=5)

    service.remember_success(chat_id=1, workflow="generate_code", prompt="prompt", result_text="value")

    assert repository.recorded == []


def test_load_recent_learnings_respects_enabled_flag_and_limit() -> None:
    repository = LearningRepositoryStub()
    enabled_service = LearningService(repository, enabled=True, max_context_items=4, max_result_chars=5)
    disabled_service = LearningService(repository, enabled=False, max_context_items=4, max_result_chars=5)

    assert enabled_service.load_recent_learnings(7) == [{"workflow": "generate_code", "prompt": "p", "result_excerpt": "7-4"}]
    assert disabled_service.load_recent_learnings(7) == []
