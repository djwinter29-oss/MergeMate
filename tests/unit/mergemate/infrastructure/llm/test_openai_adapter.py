import pytest

from mergemate.infrastructure.llm import openai_adapter
from mergemate.infrastructure.llm.openai_adapter import OpenAIAdapter


@pytest.mark.asyncio
async def test_generate_returns_fallback_when_api_key_missing() -> None:
    adapter = OpenAIAdapter(
        model="gpt-5.4",
        api_key=None,
        timeout_seconds=30,
        provider_url="https://example.invalid/v1/chat/completions",
        api_key_header="Authorization",
        api_key_prefix="Bearer",
        extra_headers={},
    )

    prompt = "x" * 1300
    result = await adapter.generate("system prompt", prompt)

    assert "Provider is not configured yet" in result
    assert "Request summary:" in result
    assert prompt[:1200] in result
    assert prompt[:1250] not in result


@pytest.mark.asyncio
async def test_generate_posts_openai_compatible_request(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class ResponseStub:
        def raise_for_status(self) -> None:
            captured["status_checked"] = True

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "  final answer  "}}]}

    class AsyncClientStub:
        def __init__(self, *, timeout: int) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            captured["entered"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            captured["exited"] = True

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> ResponseStub:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return ResponseStub()

    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", AsyncClientStub)

    adapter = OpenAIAdapter(
        model="gpt-5.4",
        api_key="secret-key",
        timeout_seconds=45,
        provider_url="https://api.example.com/v1/chat/completions",
        api_key_header="Authorization",
        api_key_prefix="Bearer",
        extra_headers={"X-Trace": "enabled"},
    )

    result = await adapter.generate("system prompt", "user prompt")

    assert result == "final answer"
    assert captured["timeout"] == 45
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["status_checked"] is True
    assert captured["entered"] is True
    assert captured["exited"] is True
    assert captured["headers"] == {
        "Authorization": "Bearer secret-key",
        "Content-Type": "application/json",
        "X-Trace": "enabled",
    }
    assert captured["json"] == {
        "model": "gpt-5.4",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ],
    }


@pytest.mark.asyncio
async def test_generate_supports_unprefixed_api_key_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_headers: dict[str, str] = {}

    class ResponseStub:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": "ok"}}]}

    class AsyncClientStub:
        def __init__(self, *, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> ResponseStub:
            captured_headers.update(headers)
            return ResponseStub()

    monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", AsyncClientStub)

    adapter = OpenAIAdapter(
        model="gpt-4.1",
        api_key="raw-key",
        timeout_seconds=60,
        provider_url="https://azure.example.com/openai/deployments/reviewer/chat/completions",
        api_key_header="api-key",
        api_key_prefix="",
        extra_headers={},
    )

    result = await adapter.generate("system", "user")

    assert result == "ok"
    assert captured_headers["api-key"] == "raw-key"
