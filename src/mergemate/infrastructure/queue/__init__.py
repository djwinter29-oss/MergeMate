"""Queue backends."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class JobQueueBackend(Protocol):
    """Protocol for queue backends used by the job dispatcher and worker."""

    def enqueue(self, job_id: str) -> bool:
        """Enqueue a job for processing. Returns False if already queued."""
        ...

    async def dequeue(self) -> str:
        """Dequeue the next available job. Blocks until one is available."""
        ...

    def acknowledge(self, job_id: str) -> None:
        """Acknowledge completion of a dequeued job."""
        ...