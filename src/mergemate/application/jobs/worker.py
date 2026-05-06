"""Background worker for queued runs."""

import asyncio
import logging
from uuid import uuid4

from mergemate.application.use_cases.submit_prompt import PromptSubmissionError
from mergemate.domain.runs.value_objects import RunJobStatus, RunJobType, RunStatus

logger = logging.getLogger(__name__)


class BackgroundRunWorker:
    def __init__(
        self,
        orchestrator,
        run_repository,
        run_job_repository,
        queue_backend,
        submit_prompt,
        lifecycle_notifier,
        *,
        max_concurrent_runs: int,
        lease_seconds: int,
        heartbeat_interval_seconds: int,
        worker_id: str | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._run_repository = run_repository
        self._run_job_repository = run_job_repository
        self._queue_backend = queue_backend
        self._submit_prompt = submit_prompt
        self._lifecycle_notifier = lifecycle_notifier
        self._semaphore = asyncio.Semaphore(max_concurrent_runs)
        self._tasks: set[asyncio.Task[None]] = set()
        self._consumer_tasks: set[asyncio.Task[None]] = set()
        self._active_job_ids: set[str] = set()
        self._stopping = False
        self._lease_seconds = lease_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._worker_id = worker_id or f"local-worker-{uuid4().hex}"

    async def start(self) -> None:
        if self._consumer_tasks:
            return
        consumer = asyncio.create_task(self._consume_loop())
        self._consumer_tasks.add(consumer)
        consumer.add_done_callback(self._consumer_tasks.discard)

    async def _consume_loop(self) -> None:
        while not self._stopping:
            job_id = await self._queue_backend.dequeue()
            self.enqueue(job_id)

    def enqueue(
        self,
        job_id: str,
    ) -> None:
        if self._stopping:
            raise RuntimeError("Background worker is stopping and cannot accept new runs.")
        if job_id in self._active_job_ids:
            return
        self._active_job_ids.add(job_id)
        task = asyncio.create_task(self._consume(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(lambda completed_task: self._active_job_ids.discard(job_id))
        task.add_done_callback(lambda completed_task: self._queue_backend.acknowledge(job_id))

    async def stop(self) -> None:
        self._stopping = True
        consumer_tasks = [task for task in self._consumer_tasks if not task.done()]
        for task in consumer_tasks:
            task.cancel()
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if consumer_tasks:
            await asyncio.gather(*consumer_tasks, return_exceptions=True)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._consumer_tasks.clear()
        self._tasks.clear()
        self._active_job_ids.clear()

    async def _consume(self, job_id: str) -> None:
        run = None
        job = self._run_job_repository.claim_job(
            job_id,
            worker_id=self._worker_id,
            lease_seconds=self._lease_seconds,
        )
        if job is None or job.status != RunJobStatus.RUNNING:
            return
        run_id = job.run_id
        heartbeat_stop = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat(job_id, heartbeat_stop))
        try:
            async with self._semaphore:
                run = await self._process_job(job)
        except asyncio.CancelledError:
            logger.warning("Run %s interrupted during shutdown", run_id)
            run = self._mark_shutdown_interrupted(run_id, job_id)
        finally:
            heartbeat_stop.set()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
        
        if run is not None:
            await self._notify_job_completion(job.job_type, run)

    async def _process_job(self, job) -> object | None:
        if job.job_type == RunJobType.PLAN_RUN:
            return await self._process_planning_job(job)
        return await self._process_execution_job(job)

    async def _process_planning_job(self, job):
        run_id = job.run_id
        try:
            result = await self._submit_prompt.complete_planning(run_id)
        except PromptSubmissionError as exc:
            self._run_job_repository.fail_job(job.job_id, exc.error_text)
            return self._run_repository.get(run_id)
        if result is None:
            self._run_job_repository.fail_job(job.job_id, "Run not found for planning job.")
            return None
        self._run_job_repository.complete_job(job.job_id)
        return self._run_repository.get(run_id)

    async def _process_execution_job(self, job):
        run_id = job.run_id
        try:
            run = await self._orchestrator.process_run(run_id)
            self._run_job_repository.complete_job(job.job_id)
            return run
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            run = self._run_repository.update_status(
                run_id,
                RunStatus.FAILED,
                error_text=str(exc),
            )
            self._run_job_repository.fail_job(job.job_id, str(exc))
            return run

    async def _heartbeat(self, job_id: str, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._heartbeat_interval_seconds)
                return
            except TimeoutError:
                self._run_job_repository.heartbeat_job(
                    job_id,
                    worker_id=self._worker_id,
                    lease_seconds=self._lease_seconds,
                )

    async def _notify_job_completion(self, job_type, run) -> None:
        if run is None:
            return
        if job_type == RunJobType.PLAN_RUN:
            if run.status == RunStatus.FAILED:
                await self._lifecycle_notifier.notify_terminal(run)
                return
            if run.status == RunStatus.AWAITING_CONFIRMATION:
                await self._lifecycle_notifier.notify_plan_ready(run)
                return
            await self._lifecycle_notifier.notify_auto_execution_started(run)
            return
        await self._lifecycle_notifier.notify_terminal(run)

    def _mark_shutdown_interrupted(self, run_id: str, job_id: str):
        self._run_job_repository.fail_job(job_id, "Run interrupted during shutdown.")
        existing = self._run_repository.get(run_id)
        if existing is None:
            return None
        if existing.status in RunStatus.terminal_statuses():
            return existing
        return self._run_repository.update_status(
            run_id,
            RunStatus.FAILED,
            error_text="Run interrupted during shutdown.",
        )