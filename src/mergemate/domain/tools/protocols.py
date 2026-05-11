"""Protocols for tool boundaries."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mergemate.domain.tools.entities import ToolMetadata


@runtime_checkable
class ToolInvoker(Protocol):
    """Shared invocation contract for tool implementations."""

    name: str
    metadata: ToolMetadata

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        """Execute the tool with a structured payload."""
