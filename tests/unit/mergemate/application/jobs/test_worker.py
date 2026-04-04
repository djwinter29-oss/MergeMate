from dataclasses import dataclass
import asyncio

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


class BlockingOrchestratorStub:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.cancelled = asyncio.Event()

    async def process_run(self, run_id: str):
        self.calls.append(run_id)
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class RunRepositoryStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RunStatus, str | None]] = []
        self.runs: dict[str, RunStub] = {}

    def update_status(self, run_id: str, status: RunStatus, *, error_text: str | None = None, current_stage=None, result_text=None):
        self.calls.append((run_id, status, error_text))
        run = self.runs.get(run_id, RunStub(run_id=run_id, status=status, error_text=error_text))
        run.status = status
        run.error_text = error_text
        self.runs[run_id] = run
        return run

    def get(self, run_id: str):
        return self.runs.get(run_id)


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


@pytest.mark.asyncio
async def test_consume_logs_and_swallows_on_finished_failures(caplog: pytest.LogCaptureFixture) -> None:
    completed_run = RunStub(run_id="run-4", status=RunStatus.COMPLETED)
    orchestrator = OrchestratorStub(result=completed_run)
    repository = RunRepositoryStub()
    worker = BackgroundRunWorker(orchestrator, repository, max_concurrent_runs=1)

    async def on_finished(run) -> None:
        raise RuntimeError("telegram down")

    with caplog.at_level("ERROR"):
        await worker._consume("run-4", on_finished=on_finished)

    assert orchestrator.calls == ["run-4"]
    assert repository.calls == []
    assert "completion callback failed" in caplog.text


@pytest.mark.asyncio
async def test_stop_cancels_inflight_tasks_and_marks_runs_failed() -> None:
    orchestrator = BlockingOrchestratorStub()
    repository = RunRepositoryStub()
    repository.runs["run-5"] = RunStub(run_id="run-5", status=RunStatus.RUNNING)
    worker = BackgroundRunWorker(orchestrator, repository, max_concurrent_runs=1)

    worker.enqueue("run-5")
    await asyncio.sleep(0)
    await worker.stop()

    assert orchestrator.calls == ["run-5"]
    assert orchestrator.cancelled.is_set() is True
    assert repository.calls == [("run-5", RunStatus.FAILED, "Run interrupted during shutdown.")]
    assert worker._tasks == set()


@pytest.mark.asyncio
async def test_stop_still_calls_on_finished_for_interrupted_run() -> None:
    orchestrator = BlockingOrchestratorStub()
    repository = RunRepositoryStub()
    repository.runs["run-shutdown"] = RunStub(run_id="run-shutdown", status=RunStatus.RUNNING)
    worker = BackgroundRunWorker(orchestrator, repository, max_concurrent_runs=1)
    observed: list[tuple[str, RunStatus, str | None]] = []

    async def on_finished(run) -> None:
        observed.append((run.run_id, run.status, run.error_text))

    worker.enqueue("run-shutdown", on_finished=on_finished)
    await asyncio.sleep(0)
    await worker.stop()

    assert observed == [(
        "run-shutdown",
        RunStatus.FAILED,
        "Run interrupted during shutdown.",
    )]


@pytest.mark.asyncio
async def test_enqueue_rejects_new_runs_after_stop() -> None:
    worker = BackgroundRunWorker(OrchestratorStub(), RunRepositoryStub(), max_concurrent_runs=1)

    await worker.stop()

    with pytest.raises(RuntimeError, match="Background worker is stopping"):
        worker.enqueue("run-6")


@pytest.mark.asyncio
async def test_stop_marks_tasks_waiting_on_semaphore_failed() -> None:
    orchestrator = BlockingOrchestratorStub()
    repository = RunRepositoryStub()
    repository.runs["run-7"] = RunStub(run_id="run-7", status=RunStatus.RUNNING)
    repository.runs["run-8"] = RunStub(run_id="run-8", status=RunStatus.QUEUED)
    worker = BackgroundRunWorker(orchestrator, repository, max_concurrent_runs=1)

    worker.enqueue("run-7")
    worker.enqueue("run-8")
    await asyncio.sleep(0)
    await worker.stop()

    assert repository.runs["run-8"].status == RunStatus.FAILED
    assert repository.runs["run-8"].error_text == "Run interrupted during shutdown."


@pytest.mark.asyncio
async def test_stop_does_not_overwrite_terminal_run_on_cancellation() -> None:
    repository = RunRepositoryStub()
    repository.runs["run-9"] = RunStub(run_id="run-9", status=RunStatus.COMPLETED, error_text=None)
    worker = BackgroundRunWorker(OrchestratorStub(), repository, max_concurrent_runs=1)

    run = worker._mark_shutdown_interrupted("run-9")

    assert run is repository.runs["run-9"]
    assert repository.calls == []
