"""Queue abstraction."""

from typing import Protocol


class QueueBackend(Protocol):
    def enqueue(self, job_id: str) -> bool: ...

    async def dequeue(self) -> str: ...

    def acknowledge(self, job_id: str) -> None: ...