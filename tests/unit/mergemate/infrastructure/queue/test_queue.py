from mergemate.infrastructure.queue.local_queue import LocalQueue


def test_local_queue_enqueue_is_noop() -> None:
    queue = LocalQueue()

    assert queue.enqueue("run-1") is None
