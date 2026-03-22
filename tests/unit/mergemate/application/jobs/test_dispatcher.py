from mergemate.application.jobs.dispatcher import RunDispatcher


class WorkerStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def enqueue(self, run_id: str, on_finished=None) -> None:
        self.calls.append((run_id, on_finished))


async def _noop(_: object) -> None:
    return None


def test_dispatch_run_enqueues_work_and_returns_result() -> None:
    worker = WorkerStub()
    dispatcher = RunDispatcher(worker)

    result = dispatcher.dispatch_run("run-42", on_finished=_noop)

    assert result.run_id == "run-42"
    assert result.status == "queued"
    assert worker.calls == [("run-42", _noop)]
