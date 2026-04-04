"""Telegram message delivery helpers."""

from collections.abc import Awaitable, Callable


TELEGRAM_MESSAGE_LIMIT = 4000


def split_telegram_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0 or split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip("\n")
    return chunks


async def send_text_chunks(
    send_text: Callable[[str], Awaitable[None]],
    text: str,
    *,
    limit: int = TELEGRAM_MESSAGE_LIMIT,
) -> None:
    for chunk in split_telegram_message(text, limit=limit):
        await send_text(chunk)