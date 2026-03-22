"""Tool runtime contracts."""

from typing import Protocol


class Tool(Protocol):
    name: str

    def invoke(self, payload: dict[str, str]) -> dict[str, str]: ...