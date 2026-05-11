import pytest
from mergemate.application.services.learning_service import LearningService


class LearningRepositoryStub:
    def __init__(self) -> None:
        self.recorded = []
        self.grouped_calls = []

    def record(
        self,
        chat_id: int,
        workflow: str,
        prompt: str,
        result_excerpt: str,
        learning_lessons: str | None = None,
    ) -> None:
        self.recorded.append((chat_id, workflow, prompt, result_excerpt, learning_lessons))

    def list_recent(self, chat_id: int, limit: int = 3):
        return [{"workflow": "generate_code", "prompt": "p", "result_excerpt": f"{chat_id}-{limit}", "learning_lessons": None}]

    def list_grouped_by_workflow(
        self,
        chat_id: int,
        current_workflow: str,
        same_workflow_limit: int = 3,
        other_workflow_limit: int = 1,
    ):
        self.grouped_calls.append(
            (chat_id, current_workflow, same_workflow_limit, other_workflow_limit)
        )
        return [
            {
                "workflow": current_workflow,
                "prompt": "grouped",
                "result_excerpt": "excerpt",
                "learning_lessons": "{}",
            }
        ]


@pytest.mark.asyncio
async def test_remember_success_truncates_and_records_when_enabled() -> None:
    repository = LearningRepositoryStub()
    service = LearningService(repository, enabled=True, max_context_items=2, max_result_chars=5)

    await service.remember_success(chat_id=1, workflow="generate_code", prompt="prompt", result_text=" 123456 ")

    # learning_lessons is "{}" because llm_gateway is None
    assert repository.recorded == [(1, "generate_code", "prompt", "12345", "{}")]


@pytest.mark.asyncio
async def test_remember_success_skips_when_disabled() -> None:
    repository = LearningRepositoryStub()
    service = LearningService(repository, enabled=False, max_context_items=2, max_result_chars=5)

    await service.remember_success(chat_id=1, workflow="generate_code", prompt="prompt", result_text="value")

    assert repository.recorded == []


def test_load_recent_learnings_respects_enabled_flag_and_limit() -> None:
    repository = LearningRepositoryStub()
    enabled_service = LearningService(repository, enabled=True, max_context_items=4, max_result_chars=5)
    disabled_service = LearningService(repository, enabled=False, max_context_items=4, max_result_chars=5)

    assert enabled_service.load_recent_learnings(7) == [{"workflow": "generate_code", "prompt": "p", "result_excerpt": "7-4", "learning_lessons": None}]
    assert disabled_service.load_recent_learnings(7) == []


def test_load_grouped_learnings_delegates_and_honors_enabled_flag() -> None:
    repository = LearningRepositoryStub()
    enabled_service = LearningService(repository, enabled=True, max_context_items=4, max_result_chars=5)
    disabled_service = LearningService(repository, enabled=False, max_context_items=4, max_result_chars=5)

    assert enabled_service.load_grouped_learnings(7, current_workflow="generate_code") == [
        {
            "workflow": "generate_code",
            "prompt": "grouped",
            "result_excerpt": "excerpt",
            "learning_lessons": "{}",
        }
    ]
    assert repository.grouped_calls == [(7, "generate_code", 4, 1)]

    repository.grouped_calls.clear()
    assert disabled_service.load_grouped_learnings(7, current_workflow="generate_code") == []
    assert repository.grouped_calls == []


class AsyncMockGateway:
    """Simulates an LLM gateway."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((agent_name, system_prompt, user_prompt))
        return '{"technical_points": ["tp1"], "pitfalls": ["pit1"], "patterns": ["pat1"], "conclusion": "done"}'


class StaticAsyncMockGateway:
    """Simulates an LLM gateway that returns a fixed payload."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str, str]] = []

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((agent_name, system_prompt, user_prompt))
        return self.response


class FailingAsyncMockGateway:
    """Simulates an LLM gateway that raises an exception."""

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        msg = "LLM timeout"
        raise RuntimeError(msg)


@pytest.mark.asyncio
async def test_extract_lessons_returns_json_with_4_keys_when_llm_succeeds() -> None:
    """_extract_lessons() returns JSON dict with 4 keys when LLM succeeds."""
    gateway = AsyncMockGateway()
    service = LearningService(
        LearningRepositoryStub(),
        enabled=True,
        max_context_items=2,
        max_result_chars=5,
        llm_gateway=gateway,
        extraction_agent_name="lessons-extractor",
    )

    result = await service._extract_lessons("Some result text here")

    import json

    parsed = json.loads(result)
    assert isinstance(parsed, dict)
    assert "technical_points" in parsed
    assert "pitfalls" in parsed
    assert "patterns" in parsed
    assert "conclusion" in parsed
    assert parsed["technical_points"] == ["tp1"]
    assert parsed["conclusion"] == "done"
    assert len(gateway.calls) == 1
    assert gateway.calls[0][0] == "lessons-extractor"


@pytest.mark.asyncio
async def test_extract_lessons_fills_missing_keys_from_partial_json() -> None:
    gateway = StaticAsyncMockGateway('{"technical_points": ["tp1"]}')
    service = LearningService(
        LearningRepositoryStub(),
        enabled=True,
        max_context_items=2,
        max_result_chars=5,
        llm_gateway=gateway,
        extraction_agent_name="lessons-extractor",
    )

    result = await service._extract_lessons("Some result text")

    import json

    parsed = json.loads(result)
    assert parsed["technical_points"] == ["tp1"]
    assert parsed["pitfalls"] == []
    assert parsed["patterns"] == []
    assert parsed["conclusion"] == ""
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_extract_lessons_returns_empty_json_when_llm_returns_non_object_json() -> None:
    gateway = StaticAsyncMockGateway('["not", "a", "dict"]')
    service = LearningService(
        LearningRepositoryStub(),
        enabled=True,
        max_context_items=2,
        max_result_chars=5,
        llm_gateway=gateway,
        extraction_agent_name="lessons-extractor",
    )

    result = await service._extract_lessons("Some result text")

    assert result == "{}"
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_extract_lessons_returns_empty_json_when_llm_fails() -> None:
    """_extract_lessons() returns \"{}\" when LLM raises exception."""
    gateway = FailingAsyncMockGateway()
    service = LearningService(
        LearningRepositoryStub(),
        enabled=True,
        max_context_items=2,
        max_result_chars=5,
        llm_gateway=gateway,
    )

    result = await service._extract_lessons("Some result text")

    assert result == "{}"


@pytest.mark.asyncio
async def test_extract_lessons_returns_empty_json_when_gateway_none() -> None:
    """_extract_lessons() returns \"{}\" when llm_gateway is None."""
    service = LearningService(
        LearningRepositoryStub(),
        enabled=True,
        max_context_items=2,
        max_result_chars=5,
        llm_gateway=None,
    )

    result = await service._extract_lessons("Some result text")

    assert result == "{}"