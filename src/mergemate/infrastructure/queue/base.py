"""Queue abstraction."""

from typing import Protocol


class QueueBackend(Protocol):
    def enqueue(self, run_id: str) -> None: ...