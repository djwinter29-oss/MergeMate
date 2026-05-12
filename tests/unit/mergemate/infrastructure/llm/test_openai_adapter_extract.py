"""Tests for openai_adapter — covering all error paths in _extract_message_content."""

import pytest

from mergemate.domain.shared.exceptions import ProviderResponseError
from mergemate.infrastructure.llm.openai_adapter import _extract_message_content


class TestExtractMessageContent:
    """Cover all branch paths in _extract_message_content (lines 14, 17, 20, 78)."""

    def test_line_14_choice_not_dict(self) -> None:
        """Line 14: choices[0] is not a dict."""
        data = {"choices": ["not_a_dict"]}
        with pytest.raises(ProviderResponseError, match="choices\\[0\\] was not an object"):
            _extract_message_content(data)

    def test_line_17_message_missing(self) -> None:
        """Line 17: choices[0].message is missing or not dict."""
        data = {"choices": [{"no_message": True}]}
        with pytest.raises(ProviderResponseError, match="choices\\[0\\]\\.message was missing"):
            _extract_message_content(data)

    def test_line_20_content_not_string(self) -> None:
        """Line 20: choices[0].message.content is not a string."""
        data = {"choices": [{"message": {"content": 42}}]}
        with pytest.raises(
            ProviderResponseError, match="choices\\[0\\]\\.message\\.content was not text"
        ):
            _extract_message_content(data)

    @pytest.mark.asyncio
    async def test_line_78_response_not_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 78: top-level response data is not a dict.

        This exercises the type-check in OpenAIAdapter.generate()."""
        from mergemate.infrastructure.llm import openai_adapter

        class ResponseStub:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> object:
                return ["not_a_dict"]

        class AsyncClientStub:
            def __init__(self, *, timeout: int) -> None:
                self.timeout = timeout

            async def __aenter__(self) -> "AsyncClientStub":
                return self

            async def __aexit__(self, exc_type, exc, tb) -> None:
                return None

            async def post(
                self, url: str, *, headers: dict[str, str], json: dict[str, object]
            ) -> ResponseStub:
                return ResponseStub()

        monkeypatch.setattr(openai_adapter.httpx, "AsyncClient", AsyncClientStub)

        adapter = openai_adapter.OpenAIAdapter(
            model="gpt-5.4",
            api_key="secret-key",
            timeout_seconds=45,
            provider_url="https://api.example.com/v1/chat/completions",
            api_key_header="Authorization",
            api_key_prefix="Bearer",
            extra_headers={},
        )

        with pytest.raises(ProviderResponseError, match="top-level JSON object was expected"):
            await adapter.generate("system", "user")
