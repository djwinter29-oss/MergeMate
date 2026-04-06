"""Local durable queue placeholder."""

import asyncio


class LocalQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._pending_job_ids: set[str] = set()

    def enqueue(self, job_id: str) -> bool:
        if job_id in self._pending_job_ids:
            return False
        self._pending_job_ids.add(job_id)
        self._queue.put_nowait(job_id)
        return True

    async def dequeue(self) -> str:
        return await self._queue.get()

    def acknowledge(self, job_id: str) -> None:
        self._pending_job_ids.discard(job_id)
        self._queue.task_done()