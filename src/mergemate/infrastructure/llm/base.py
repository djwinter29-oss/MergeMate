"""Provider abstraction."""

from typing import Protocol


class LLMClient(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str) -> str: ...