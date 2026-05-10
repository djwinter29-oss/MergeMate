"""Tests for BackgroundRunWorker covering uncovered lines.

Target lines:
 45-49: start() returns early when already started
 52-54: _consume_loop dequeues jobs
 75: stop() cancels consumer tasks
 80: stop() awaits consumer tasks
 95: _consume returns when job claim fails
125-126: _process_planning_job returns None when run not found
160: _notify_job_completion returns when run is None
176: _mark_shutdown_interrupted returns None when run not found
177-178: _mark_shutdown_interrupted returns existing when already terminal
"""
import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from mergemate.application.jobs.worker import BackgroundRunWorker
from mergemate.domain.shared import RunJobStatus, RunJobType, RunStatus
from mergemate.domain.shared.exceptions import WorkerStoppedError


@dataclass
class FakeJob:
    job_id: str = "job-1"
    run_id: str = "run-1"
    job_type: RunJobType = RunJobType.EXECUTE_RUN
    status: RunJobStatus = RunJobStatus.RUNNING


class FakeRunJobRepo:
    """Stub run-job repository."""

    def __init__(self):
        self.claimed = False

    def claim_job(self, job_id, **kwargs):
        if not self.claimed:
            self.claimed = True
            return FakeJob()
        return None

    def heartbeat_job(self, *args, **kwargs):
        pass

    def complete_job(self, *args, **kwargs):
        pass

    def fail_job(self, *args, **kwargs):
        pass


class FakeRunRepo:
    """Stub run repository."""

    def __init__(self, run=None):
        self._run = run

    def get(self, run_id: str):
        return self._run

    def update_status(self, run_id, status, **kwargs):
        return SimpleNamespace(run_id=run_id, status=status)


class FakeQueueBackend:
    """Stub queue backend."""

    def __init__(self, items=None):
        self._items = list(items or ["job-1"])

    def enqueue(self, job_id: str) -> bool:
        return True

    async def dequeue(self):
        if self._items:
            return self._items.pop(0)
        await asyncio.Event().wait()

    def acknowledge(self, job_id):
        pass


class FakeSubmitPrompt:
    """Stub prompt submission."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def complete_planning(self, run_id):
        if self._error:
            raise self._error
        return self._result


class FakeOrchestrator:
    """Stub orchestrator."""

    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    async def process_run(self, run_id):
        if self._error:
            raise self._error
        return self._result


class FakeLifecycleNotifier:
    """Stub lifecycle notifier."""

    def __init__(self):
        self.calls = []

    async def notify_terminal(self, run):
        self.calls.append(("notify_terminal", run))

    async def notify_plan_ready(self, run):
        self.calls.append(("notify_plan_ready", run))

    async def notify_auto_execution_started(self, run):
        self.calls.append(("notify_auto_execution_started", run))


def _make_worker(**kwargs):
    defaults = dict(
        orchestrator=FakeOrchestrator(),
        run_repository=FakeRunRepo(),
        run_job_repository=FakeRunJobRepo(),
        queue_backend=FakeQueueBackend(),
        submit_prompt=FakeSubmitPrompt(),
        lifecycle_notifier=FakeLifecycleNotifier(),
        max_concurrent_runs=5,
        lease_seconds=30,
        heartbeat_interval_seconds=10,
        worker_id="test-worker",
    )
    defaults.update(kwargs)
    return BackgroundRunWorker(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStart:
    """Cover line 45-49: start() when already started."""

    @pytest.mark.asyncio
    async def test_start_returns_early_when_already_started(self) -> None:
        """Line 45-46: if self._consumer_tasks is non-empty, return immediately."""
        worker = _make_worker()
        # Add a dummy task so the set is non-empty
        dummy = asyncio.create_task(asyncio.sleep(0))
        worker._consumer_tasks.add(dummy)
        result = await worker.start()
        assert result is None


class TestConsumeLoop:
    """Cover lines 52-54: _consume_loop dequeues and enqueues."""

    @pytest.mark.asyncio
    async def test_consume_loop_dequeues_and_enqueues(self) -> None:
        """Line 53-54: dequeue returns job_id, enqueue is called with it."""
        consumed = []

        worker = _make_worker(queue_backend=FakeQueueBackend(["job-p1"]))
        worker.enqueue = lambda job_id: consumed.append(job_id)

        task = asyncio.create_task(worker._consume_loop())
        await asyncio.sleep(0.1)
        worker._stopping = True
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, RuntimeError):
            pass

        assert consumed == ["job-p1"]


class TestStop:
    """Cover lines 75, 80: stop() cancels and awaits tasks."""

    @pytest.mark.asyncio
    async def test_stop_cancels_and_awaits(self) -> None:
        """Lines 75, 80: consumer tasks are cancelled and gathered."""
        worker = _make_worker()

        async def forever():
            await asyncio.Event().wait()

        consumer_task = asyncio.create_task(forever())
        worker._consumer_tasks.add(consumer_task)

        work_task = asyncio.create_task(forever())
        worker._tasks.add(work_task)

        await worker.stop()

        assert consumer_task.done()
        assert work_task.done()
        assert len(worker._consumer_tasks) == 0
        assert len(worker._tasks) == 0
        assert len(worker._active_job_ids) == 0


class TestConsumeReturnsWhenJobClaimFails:
    """Cover line 95: _consume returns when job claim fails."""

    @pytest.mark.asyncio
    async def test_consume_returns_when_job_not_claimed(self) -> None:
        """Line 94-95: claim_job returns None -> return."""
        repo = FakeRunJobRepo()
        repo.claimed = True  # makes claim_job return None
        worker = _make_worker(run_job_repository=repo)
        result = await worker._consume("job-none")
        assert result is None


class TestProcessPlanningJob:
    """Cover lines 125-126: _process_planning_job returns None when result None."""

    @pytest.mark.asyncio
    async def test_planning_job_result_none(self) -> None:
        """Line 124-126: complete_planning returns None -> fail and return None."""
        fail_called = False

        class FailTrackingRepo(FakeRunJobRepo):
            def fail_job(self, job_id, error_text):
                nonlocal fail_called
                fail_called = True

        worker = _make_worker(
            submit_prompt=FakeSubmitPrompt(result=None),
            run_job_repository=FailTrackingRepo(),
        )
        job = FakeJob(job_id="job-p1", run_id="run-p1", job_type=RunJobType.PLAN_RUN)
        result = await worker._process_planning_job(job)
        assert result is None
        assert fail_called


class TestNotifyJobCompletion:
    """Cover line 160: _notify_job_completion returns when run is None."""

    @pytest.mark.asyncio
    async def test_notify_returns_when_run_none(self) -> None:
        """Line 159-160: if run is None, return immediately."""
        notifier = FakeLifecycleNotifier()
        worker = _make_worker(lifecycle_notifier=notifier)
        await worker._notify_job_completion(RunJobType.PLAN_RUN, None)
        assert notifier.calls == []


class TestMarkShutdownInterrupted:
    """Cover lines 175-183: _mark_shutdown_interrupted behavior."""

    def test_returns_none_when_run_not_found(self) -> None:
        """Line 175-176: get returns None -> return None."""
        worker = _make_worker(run_repository=FakeRunRepo(run=None))
        result = worker._mark_shutdown_interrupted("run-missing", "job-missing")
        assert result is None

    def test_returns_existing_when_already_terminal(self) -> None:
        """Line 177-178: existing run is terminal -> return existing."""
        existing = SimpleNamespace(run_id="run-term", status=RunStatus.COMPLETED)
        worker = _make_worker(run_repository=FakeRunRepo(run=existing))
        result = worker._mark_shutdown_interrupted("run-term", "job-term")
        assert result is existing

    def test_updates_status_when_not_terminal(self) -> None:
        """Line 179-183: existing run not terminal -> update to FAILED."""
        existing = SimpleNamespace(run_id="run-live", status=RunStatus.QUEUED)
        worker = _make_worker(run_repository=FakeRunRepo(run=existing))
        result = worker._mark_shutdown_interrupted("run-live", "job-live")
        assert result.run_id == "run-live"
        assert result.status == RunStatus.FAILED


class TestEnqueue:
    """Cover enqueue edge cases."""

    def test_enqueue_raises_when_stopping(self) -> None:
        """Line 60-61: raise WorkerStoppedError when stopping."""
        worker = _make_worker()
        worker._stopping = True
        with pytest.raises(WorkerStoppedError, match="stopping"):
            worker.enqueue("job-x")

    @pytest.mark.asyncio
    async def test_enqueue_skips_existing_job(self) -> None:
        """Line 62-63: skip if job_id already active."""
        worker = _make_worker()
        worker._active_job_ids.add("job-x")
        worker.enqueue("job-x")
        assert len(worker._tasks) == 0


class TestProcessJob:
    """Cover _process_job and its branches."""

    @pytest.mark.asyncio
    async def test_process_execution_job(self) -> None:
        """Process a plain execution job."""
        run = SimpleNamespace(run_id="run-e1", status=RunStatus.COMPLETED)
        worker = _make_worker(orchestrator=FakeOrchestrator(result=run))
        job = FakeJob(job_id="job-e1", run_id="run-e1", job_type=RunJobType.EXECUTE_RUN)
        result = await worker._process_job(job)
        assert result is run


class TestNotifyJobCompletionPaths:
    """Cover all branches of _notify_job_completion (lines 158-170)."""

    @pytest.mark.asyncio
    async def test_notify_plan_failed(self) -> None:
        """Line 162-163: plan FAILED -> notify_terminal."""
        notifier = FakeLifecycleNotifier()
        worker = _make_worker(lifecycle_notifier=notifier)
        run = SimpleNamespace(status=RunStatus.FAILED)
        await worker._notify_job_completion(RunJobType.PLAN_RUN, run)
        assert ("notify_terminal", run) in notifier.calls

    @pytest.mark.asyncio
    async def test_notify_plan_awaiting_confirmation(self) -> None:
        """Line 165-166: plan AWAITING_CONFIRMATION -> notify_plan_ready."""
        notifier = FakeLifecycleNotifier()
        worker = _make_worker(lifecycle_notifier=notifier)
        run = SimpleNamespace(status=RunStatus.AWAITING_CONFIRMATION)
        await worker._notify_job_completion(RunJobType.PLAN_RUN, run)
        assert ("notify_plan_ready", run) in notifier.calls

    @pytest.mark.asyncio
    async def test_notify_plan_auto_execution(self) -> None:
        """Line 168: plan not FAILED/AWAITING -> auto_execution_started."""
        notifier = FakeLifecycleNotifier()
        worker = _make_worker(lifecycle_notifier=notifier)
        run = SimpleNamespace(status=RunStatus.COMPLETED)
        await worker._notify_job_completion(RunJobType.PLAN_RUN, run)
        assert ("notify_auto_execution_started", run) in notifier.calls

    @pytest.mark.asyncio
    async def test_notify_execution_job(self) -> None:
        """Line 170: EXECUTE_RUN -> notify_terminal."""
        notifier = FakeLifecycleNotifier()
        worker = _make_worker(lifecycle_notifier=notifier)
        run = SimpleNamespace(status=RunStatus.COMPLETED)
        await worker._notify_job_completion(RunJobType.EXECUTE_RUN, run)
        assert ("notify_terminal", run) in notifier.calls


class TestStartCreatesConsumer:
    """Cover lines 47-49: start() creates a consumer task."""

    @pytest.mark.asyncio
    async def test_start_creates_consumer_task(self) -> None:
        """Line 47-49: consumer task is added with done callback."""
        worker = _make_worker(queue_backend=FakeQueueBackend([]))
        await worker.start()
        assert len(worker._consumer_tasks) == 1
        task = list(worker._consumer_tasks)[0]
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, RuntimeError):
            pass


class TestEnqueueNewJob:
    """Cover lines 64-69: enqueue a new job."""

    @pytest.mark.asyncio
    async def test_enqueue_new_job_creates_task(self) -> None:
        """Lines 64-69: new job id creates a task."""
        worker = _make_worker(run_job_repository=FakeRunJobRepo())
        assert len(worker._tasks) == 0
        worker.enqueue("job-new")
        assert len(worker._tasks) == 1
        assert "job-new" in worker._active_job_ids


class TestConsumeFullFlow:
    """Cover lines 96-110: _consume full path."""

    @pytest.mark.asyncio
    async def test_consume_full_flow(self) -> None:
        """Lines 96-110: claim job, heartbeat, process, notify."""
        run = SimpleNamespace(run_id="run-c1", status=RunStatus.COMPLETED)
        notifier = FakeLifecycleNotifier()
        worker = _make_worker(
            run_job_repository=FakeRunJobRepo(),
            run_repository=FakeRunRepo(run=run),
            orchestrator=FakeOrchestrator(result=run),
            lifecycle_notifier=notifier,
        )
        await worker._consume("job-flow-1")
        assert ("notify_terminal", run) in notifier.calls


class TestProcessExecutionJobFailure:
    """Cover lines 136-144: exception handling."""

    @pytest.mark.asyncio
    async def test_process_execution_job_handles_exception(self) -> None:
        """Lines 136-144: orchestrator raises -> fail job, return run."""
        fail_called = False

        class FailTrack(FakeRunJobRepo):
            def fail_job(self, job_id, error_text):
                nonlocal fail_called
                fail_called = True

        run = SimpleNamespace(run_id="run-f1", status=RunStatus.FAILED)
        worker = _make_worker(
            orchestrator=FakeOrchestrator(error=RuntimeError("boom")),
            run_repository=FakeRunRepo(run=run),
            run_job_repository=FailTrack(),
        )
        job = FakeJob(job_id="job-f1", run_id="run-f1", job_type=RunJobType.EXECUTE_RUN)
        result = await worker._process_job(job)
        assert result is not None
        assert result.status == RunStatus.FAILED
        assert fail_called


class TestProcessPlanningJobError:
    """Cover lines 121-123: PromptSubmissionError handling."""

    @pytest.mark.asyncio
    async def test_planning_job_catches_prompt_error(self) -> None:
        """Lines 121-123: PromptSubmissionError -> fail and return run."""
        from mergemate.application.use_cases.submit_prompt import PromptSubmissionError

        fail_called = False

        class FailTrack(FakeRunJobRepo):
            def fail_job(self, job_id, error_text):
                nonlocal fail_called
                fail_called = True

        run = SimpleNamespace(run_id="run-p1")
        worker = _make_worker(
            submit_prompt=FakeSubmitPrompt(error=PromptSubmissionError("run-p1", "bad")),
            run_repository=FakeRunRepo(run=run),
            run_job_repository=FailTrack(),
        )
        job = FakeJob(job_id="job-p1", run_id="run-p1", job_type=RunJobType.PLAN_RUN)
        result = await worker._process_planning_job(job)
        assert result is run
        assert fail_called


class TestProcessPlanningJobCompletes:
    """Cover lines 127-128: _process_planning_job completes successfully."""

    @pytest.mark.asyncio
    async def test_planning_job_completes(self) -> None:
        """Lines 127-128: complete_planning returns result -> complete and return run."""
        complete_called = False

        class CompleteTrack(FakeRunJobRepo):
            def complete_job(self, job_id):
                nonlocal complete_called
                complete_called = True

        run = SimpleNamespace(run_id="run-p2")
        worker = _make_worker(
            submit_prompt=FakeSubmitPrompt(result="plan result"),
            run_repository=FakeRunRepo(run=run),
            run_job_repository=CompleteTrack(),
        )
        job = FakeJob(job_id="job-p2", run_id="run-p2", job_type=RunJobType.PLAN_RUN)
        result = await worker._process_planning_job(job)
        assert result is run
        assert complete_called