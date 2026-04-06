from dataclasses import dataclass
from datetime import UTC, datetime
import asyncio

import pytest

from mergemate.application.jobs.worker import BackgroundRunWorker
from mergemate.application.use_cases.submit_prompt import PromptSubmissionError
from mergemate.domain.runs.entities import RunJob
from mergemate.domain.runs.value_objects import RunJobStatus, RunJobType, RunStatus


@dataclass(slots=True)
class RunStub:
    run_id: str
    status: RunStatus
    error_text: str | None = None
    chat_id: int = 5
    plan_text: str | None = "plan"
    estimate_seconds: int = 12


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


class PendingOrchestratorStub:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.release = asyncio.Event()

    async def process_run(self, run_id: str):
        self.calls.append(run_id)
        await self.release.wait()
        return RunStub(run_id=run_id, status=RunStatus.COMPLETED)


class SubmitPromptStub:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[str] = []

    async def complete_planning(self, run_id: str):
        self.calls.append(run_id)
        if self.error is not None:
            raise self.error
        return self.result


class LifecycleNotifierStub:
    def __init__(self) -> None:
        self.plan_ready: list[str] = []
        self.auto_started: list[str] = []
        self.terminal: list[str] = []

    async def notify_plan_ready(self, run) -> bool:
        self.plan_ready.append(run.run_id)
        return True

    async def notify_auto_execution_started(self, run) -> bool:
        self.auto_started.append(run.run_id)
        return True

    async def notify_terminal(self, run) -> bool:
        self.terminal.append(run.run_id)
        return True


class QueueBackendStub:
    def __init__(self) -> None:
        self.acknowledged: list[str] = []

    def acknowledge(self, job_id: str) -> None:
        self.acknowledged.append(job_id)

    def enqueue(self, job_id: str) -> bool:
        return True

    async def dequeue(self) -> str:
        raise AssertionError("dequeue should not be called in direct _consume tests")


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


class RunJobRepositoryStub:
    def __init__(self) -> None:
        self.jobs: dict[str, RunJob] = {}
        self.completed_calls: list[str] = []
        self.failed_calls: list[tuple[str, str]] = []
        self.claim_calls: list[tuple[str, str, int]] = []
        self.heartbeat_calls: list[tuple[str, str, int]] = []

    def add(self, job_id: str, run_id: str, *, job_type: RunJobType = RunJobType.EXECUTE_RUN, status: RunJobStatus = RunJobStatus.QUEUED) -> None:
        now = datetime.now(UTC)
        self.jobs[job_id] = RunJob(
            job_id=job_id,
            run_id=run_id,
            job_type=job_type,
            status=status,
            attempt_count=0,
            lease_owner=None,
            lease_expires_at=None,
            last_heartbeat_at=None,
            error_text=None,
            queued_at=now,
            started_at=now if status == RunJobStatus.RUNNING else None,
            finished_at=None,
            updated_at=now,
        )

    def claim_job(self, job_id: str, *, worker_id: str, lease_seconds: int):
        self.claim_calls.append((job_id, worker_id, lease_seconds))
        job = self.jobs.get(job_id)
        if job is None:
            return None
        if job.status != RunJobStatus.QUEUED:
            return None
        now = datetime.now(UTC)
        job.status = RunJobStatus.RUNNING
        job.attempt_count += 1
        job.lease_owner = worker_id
        job.lease_expires_at = now
        job.last_heartbeat_at = now
        job.started_at = now
        job.updated_at = now
        return job

    def heartbeat_job(self, job_id: str, *, worker_id: str, lease_seconds: int):
        self.heartbeat_calls.append((job_id, worker_id, lease_seconds))
        return self.jobs.get(job_id)

    def complete_job(self, job_id: str):
        job = self.jobs.get(job_id)
        if job is not None:
            job.status = RunJobStatus.COMPLETED
            self.completed_calls.append(job_id)
        return job

    def fail_job(self, job_id: str, error_text: str):
        job = self.jobs.get(job_id)
        if job is not None:
            job.status = RunJobStatus.FAILED
            job.error_text = error_text
            self.failed_calls.append((job_id, error_text))
        return job


def _build_worker(
    orchestrator,
    repository,
    run_job_repository,
    *,
    queue_backend=None,
    submit_prompt=None,
    notifier=None,
    heartbeat_interval_seconds: int = 60,
):
    return BackgroundRunWorker(
        orchestrator=orchestrator,
        run_repository=repository,
        run_job_repository=run_job_repository,
        queue_backend=queue_backend or QueueBackendStub(),
        submit_prompt=submit_prompt or SubmitPromptStub(),
        lifecycle_notifier=notifier or LifecycleNotifierStub(),
        max_concurrent_runs=1,
        lease_seconds=30,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        worker_id="worker-1",
    )


@pytest.mark.asyncio
async def test_consume_completes_execution_job_and_notifies_terminal() -> None:
    completed_run = RunStub(run_id="run-1", status=RunStatus.COMPLETED)
    orchestrator = OrchestratorStub(result=completed_run)
    repository = RunRepositoryStub()
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("job-1", "run-1")
    notifier = LifecycleNotifierStub()
    worker = _build_worker(orchestrator, repository, run_job_repository, notifier=notifier)

    await worker._consume("job-1")

    assert orchestrator.calls == ["run-1"]
    assert repository.calls == []
    assert run_job_repository.completed_calls == ["job-1"]
    assert notifier.terminal == ["run-1"]


@pytest.mark.asyncio
async def test_consume_marks_execution_job_failed_when_orchestrator_raises() -> None:
    orchestrator = OrchestratorStub(error=RuntimeError("boom"))
    repository = RunRepositoryStub()
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("job-2", "run-2")
    notifier = LifecycleNotifierStub()
    worker = _build_worker(orchestrator, repository, run_job_repository, notifier=notifier)

    await worker._consume("job-2")

    assert repository.calls == [("run-2", RunStatus.FAILED, "boom")]
    assert run_job_repository.failed_calls == [("job-2", "boom")]
    assert notifier.terminal == ["run-2"]


@pytest.mark.asyncio
async def test_consume_completes_planning_job_and_notifies_plan_ready() -> None:
    repository = RunRepositoryStub()
    repository.runs["run-plan"] = RunStub(run_id="run-plan", status=RunStatus.AWAITING_CONFIRMATION, plan_text="plan")
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("plan-job", "run-plan", job_type=RunJobType.PLAN_RUN)
    submit_prompt = SubmitPromptStub(result=object())
    notifier = LifecycleNotifierStub()
    worker = _build_worker(OrchestratorStub(), repository, run_job_repository, submit_prompt=submit_prompt, notifier=notifier)

    await worker._consume("plan-job")

    assert submit_prompt.calls == ["run-plan"]
    assert run_job_repository.completed_calls == ["plan-job"]
    assert notifier.plan_ready == ["run-plan"]


@pytest.mark.asyncio
async def test_consume_planning_job_notifies_auto_start_for_queued_run() -> None:
    repository = RunRepositoryStub()
    repository.runs["run-auto"] = RunStub(run_id="run-auto", status=RunStatus.QUEUED, plan_text="plan")
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("plan-job", "run-auto", job_type=RunJobType.PLAN_RUN)
    notifier = LifecycleNotifierStub()
    worker = _build_worker(OrchestratorStub(), repository, run_job_repository, submit_prompt=SubmitPromptStub(result=object()), notifier=notifier)

    await worker._consume("plan-job")

    assert notifier.auto_started == ["run-auto"]


@pytest.mark.asyncio
async def test_consume_planning_job_notifies_terminal_on_failure() -> None:
    repository = RunRepositoryStub()
    repository.runs["run-failed"] = RunStub(run_id="run-failed", status=RunStatus.FAILED, error_text="planner unavailable")
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("plan-job", "run-failed", job_type=RunJobType.PLAN_RUN)
    notifier = LifecycleNotifierStub()
    worker = _build_worker(
        OrchestratorStub(),
        repository,
        run_job_repository,
        submit_prompt=SubmitPromptStub(error=PromptSubmissionError("run-failed", "planner unavailable")),
        notifier=notifier,
    )

    await worker._consume("plan-job")

    assert run_job_repository.failed_calls == [("plan-job", "planner unavailable")]
    assert notifier.terminal == ["run-failed"]


@pytest.mark.asyncio
async def test_enqueue_tracks_and_acknowledges_completed_task() -> None:
    completed_run = RunStub(run_id="run-3", status=RunStatus.COMPLETED)
    orchestrator = OrchestratorStub(result=completed_run)
    repository = RunRepositoryStub()
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("job-3", "run-3")
    queue_backend = QueueBackendStub()
    worker = _build_worker(orchestrator, repository, run_job_repository, queue_backend=queue_backend)

    worker.enqueue("job-3")
    assert len(worker._tasks) == 1

    await asyncio.gather(*list(worker._tasks))

    assert orchestrator.calls == ["run-3"]
    assert len(worker._tasks) == 0
    assert queue_backend.acknowledged == ["job-3"]


@pytest.mark.asyncio
async def test_enqueue_ignores_duplicate_active_job_ids() -> None:
    orchestrator = PendingOrchestratorStub()
    repository = RunRepositoryStub()
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("job-dup", "run-dup")
    worker = _build_worker(orchestrator, repository, run_job_repository)

    worker.enqueue("job-dup")
    worker.enqueue("job-dup")
    await asyncio.sleep(0)

    assert orchestrator.calls == ["run-dup"]

    orchestrator.release.set()
    await asyncio.gather(*list(worker._tasks))
    assert worker._active_job_ids == set()


@pytest.mark.asyncio
async def test_stop_cancels_inflight_tasks_and_marks_runs_failed() -> None:
    orchestrator = BlockingOrchestratorStub()
    repository = RunRepositoryStub()
    repository.runs["run-5"] = RunStub(run_id="run-5", status=RunStatus.RUNNING)
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("job-5", "run-5")
    worker = _build_worker(orchestrator, repository, run_job_repository)

    worker.enqueue("job-5")
    await asyncio.sleep(0)
    await worker.stop()

    assert orchestrator.calls == ["run-5"]
    assert orchestrator.cancelled.is_set() is True
    assert repository.calls == [("run-5", RunStatus.FAILED, "Run interrupted during shutdown.")]
    assert run_job_repository.failed_calls == [("job-5", "Run interrupted during shutdown.")]


@pytest.mark.asyncio
async def test_enqueue_rejects_new_runs_after_stop() -> None:
    worker = _build_worker(OrchestratorStub(), RunRepositoryStub(), RunJobRepositoryStub())

    await worker.stop()

    with pytest.raises(RuntimeError, match="Background worker is stopping"):
        worker.enqueue("job-6")


def test_mark_shutdown_interrupted_does_not_overwrite_terminal_run() -> None:
    repository = RunRepositoryStub()
    repository.runs["run-9"] = RunStub(run_id="run-9", status=RunStatus.COMPLETED)
    run_job_repository = RunJobRepositoryStub()
    run_job_repository.add("job-9", "run-9", status=RunJobStatus.RUNNING)
    worker = _build_worker(OrchestratorStub(), repository, run_job_repository)

    run = worker._mark_shutdown_interrupted("run-9", "job-9")

    assert run is repository.runs["run-9"]
    assert repository.calls == []