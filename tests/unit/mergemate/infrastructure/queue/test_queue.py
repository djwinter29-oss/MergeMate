import pytest

from mergemate.infrastructure.queue.local_queue import LocalQueue


@pytest.mark.asyncio
async def test_local_queue_tracks_pending_jobs_until_acknowledged() -> None:
    queue = LocalQueue()

    assert queue.enqueue("job-1") is True
    assert queue.enqueue("job-1") is False

    dequeued = await queue.dequeue()

    assert dequeued == "job-1"

    queue.acknowledge("job-1")
    assert queue.enqueue("job-1") is True
