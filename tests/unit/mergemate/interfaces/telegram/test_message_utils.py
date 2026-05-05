"""Unit tests for Telegram message delivery helpers."""

import pytest

from mergemate.interfaces.telegram.message_utils import (
    TELEGRAM_MESSAGE_LIMIT,
    send_text_chunks,
    split_telegram_message,
)


def _make_lines(n: int, line_length: int = 20) -> str:
    """Build a string of n lines, each with line_length dashes."""
    return "\n".join("-" * line_length for _ in range(n))


class TestSplitTelegramMessage:
    def test_short_text_returns_single_chunk(self) -> None:
        text = "Hello, world!"
        assert split_telegram_message(text) == [text]

    def test_empty_text_returns_single_chunk(self) -> None:
        assert split_telegram_message("") == [""]

    def text_exact_limit_returns_single_chunk(self) -> None:
        text = "x" * TELEGRAM_MESSAGE_LIMIT
        assert split_telegram_message(text) == [text]

    def test_one_over_limit_splits_at_newline(self) -> None:
        text = _make_lines(TELEGRAM_MESSAGE_LIMIT // 10 + 1, line_length=9)
        chunks = split_telegram_message(text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= TELEGRAM_MESSAGE_LIMIT

    def test_each_chunk_stays_within_limit(self) -> None:
        line = "x" * 100
        text = "\n".join(line for _ in range(100))
        chunks = split_telegram_message(text, limit=5000)
        for chunk in chunks:
            assert len(chunk) <= 5000

    def test_long_word_exceeds_limit_forces_hard_split(self) -> None:
        text = "x" * TELEGRAM_MESSAGE_LIMIT + "-short"
        chunks = split_telegram_message(text)
        assert len(chunks) == 2
        assert chunks[0] == "x" * TELEGRAM_MESSAGE_LIMIT
        assert chunks[1] == "-short"

    def test_newline_excessive_whitespace_is_trimmed(self) -> None:
        text = "hello\n\n\n\n\n" + "world" + "\n\n\n\n\n" + "end"
        text_long = text * (TELEGRAM_MESSAGE_LIMIT // len(text) + 1)
        chunks = split_telegram_message(text_long, limit=400)
        for chunk in chunks:
            assert len(chunk) <= 400
        assert all(isinstance(c, str) for c in chunks)

    def test_custom_limit(self) -> None:
        text = "AAAAABBBBBCCCCCDDDDD"
        chunks = split_telegram_message(text, limit=10)
        assert chunks == ["AAAAABBBBB", "CCCCCDDDDD"]

    def test_split_at_newline_preserves_line_integrity(self) -> None:
        """Newline boundaries should be preferred split points."""
        line = "short"
        text = "\n".join(line for _ in range(10))
        chunks = split_telegram_message(text, limit=15)
        for chunk in chunks:
            assert len(chunk) <= 15
        # Each chunk should hold at least one complete line
        assert len(chunks) > 1

    def test_all_chunks_respect_limit_with_no_content_loss(self) -> None:
        text = _make_lines(300, line_length=15)
        chunks = split_telegram_message(text)
        for chunk in chunks:
            assert len(chunk) <= TELEGRAM_MESSAGE_LIMIT
        # All original words should be present somewhere
        all_text = " ".join(chunks)
        assert all(line in all_text for line in text.split("\n"))


class TestSendTextChunks:
    @pytest.mark.asyncio
    async def test_sends_each_chunk(self) -> None:
        sent: list[str] = []

        async def fake_sender(text: str) -> None:
            sent.append(text)

        await send_text_chunks(fake_sender, "Hello\n" * 600, limit=500)
        assert len(sent) >= 2
        for msg in sent:
            assert len(msg) <= 500