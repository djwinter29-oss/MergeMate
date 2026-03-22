from dataclasses import dataclass

import pytest

from mergemate.application.jobs.worker import BackgroundRunWorker
from mergemate.domain.runs.value_objects import RunStatus


@dataclass(slots=True)
class RunStub:
    run_id: str
    status: RunStatus
    error_text: str | None = None


class OrchestratorStub:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def process_run(self, run_id: str):
        self.calls.append(run_id)
        if self.error is not None:
            raise self.error
        return self.result


class RunRepositoryStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RunStatus, str | None]] = []

    def update_status(self, run_id: str, status: RunStatus, *, error_text: str | None = None, current_stage=None, result_text=None):
        self.calls.append((run_id, status, error_text))
        return RunStub(run_id=run_id, status=status, error_text=error_text)


@pytest.mark.asyncio
async def test_consume_calls_on_finished_for_successful_run() -> None:
    completed_run = RunStub(run_id="run-1", status=RunStatus.COMPLETED)
    orchestrator = OrchestratorStub(result=completed_run)
    repository = RunRepositoryStub()
    worker = BackgroundRunWorker(orchestrator, repository, max_concurrent_runs=1)
    observed: list[RunStub] = []

    async def on_finished(run) -> None:
        observed.append(run)

    await worker._consume("run-1", on_finished=on_finished)

    assert orchestrator.calls == ["run-1"]
    assert repository.calls == []
    assert observed == [completed_run]


@pytest.mark.asyncio
async def test_consume_marks_run_failed_when_orchestrator_raises() -> None:
    orchestrator = OrchestratorStub(error=RuntimeError("boom"))
    repository = RunRepositoryStub()
    worker = BackgroundRunWorker(orchestrator, repository, max_concurrent_runs=1)
    observed: list[RunStub] = []

    async def on_finished(run) -> None:
        observed.append(run)

    await worker._consume("run-2", on_finished=on_finished)

    assert repository.calls == [("run-2", RunStatus.FAILED, "boom")]
    assert observed[0].status == RunStatus.FAILED
    assert observed[0].error_text == "boom"


@pytest.mark.asyncio
async def test_enqueue_tracks_and_discards_completed_task() -> None:
    completed_run = RunStub(run_id="run-3", status=RunStatus.COMPLETED)
    orchestrator = OrchestratorStub(result=completed_run)
    repository = RunRepositoryStub()
    worker = BackgroundRunWorker(orchestrator, repository, max_concurrent_runs=1)

    worker.enqueue("run-3")
    assert len(worker._tasks) == 1

    await pytest.importorskip("asyncio").sleep(0)
    await pytest.importorskip("asyncio").sleep(0)

    assert orchestrator.calls == ["run-3"]
    assert len(worker._tasks) == 0
