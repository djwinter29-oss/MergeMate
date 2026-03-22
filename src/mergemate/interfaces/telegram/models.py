"""Telegram-facing DTOs."""

from dataclasses import dataclass


@dataclass(slots=True)
class TelegramRequest:
    chat_id: int
    user_id: int
    message_text: str
    agent_name: str