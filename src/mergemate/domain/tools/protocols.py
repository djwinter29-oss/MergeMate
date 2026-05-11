"""Protocols for tool boundaries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ToolInvoker(Protocol):
    """Shared invocation contract for tool implementations."""

    name: str
    metadata: object

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        """Execute the tool with a structured payload."""
