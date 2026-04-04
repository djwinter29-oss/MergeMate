"""Background worker for queued runs."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from mergemate.domain.runs.value_objects import RunStatus

logger = logging.getLogger(__name__)


class BackgroundRunWorker:
    def __init__(self, orchestrator, run_repository, max_concurrent_runs: int) -> None:
        self._orchestrator = orchestrator
        self._run_repository = run_repository
        self._semaphore = asyncio.Semaphore(max_concurrent_runs)
        self._tasks: set[asyncio.Task[None]] = set()
        self._stopping = False

    def enqueue(
        self,
        run_id: str,
        on_finished: Callable[[object], Awaitable[None]] | None = None,
    ) -> None:
        if self._stopping:
            raise RuntimeError("Background worker is stopping and cannot accept new runs.")
        task = asyncio.create_task(self._consume(run_id, on_finished=on_finished))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def stop(self) -> None:
        self._stopping = True
        tasks = [task for task in self._tasks if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _consume(
        self,
        run_id: str,
        on_finished: Callable[[object], Awaitable[None]] | None = None,
    ) -> None:
        run = None
        try:
            async with self._semaphore:
                try:
                    run = await self._orchestrator.process_run(run_id)
                except Exception as exc:
                    logger.exception("Run %s failed", run_id)
                    run = self._run_repository.update_status(
                        run_id,
                        RunStatus.FAILED,
                        error_text=str(exc),
                    )
        except asyncio.CancelledError:
            logger.warning("Run %s interrupted during shutdown", run_id)
            run = self._mark_shutdown_interrupted(run_id)
        
        if on_finished is not None and run is not None:
            try:
                await on_finished(run)
            except Exception:
                logger.exception("Run %s completion callback failed", run_id)

    def _mark_shutdown_interrupted(self, run_id: str):
        existing = self._run_repository.get(run_id)
        if existing is None:
            return None
        if existing.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
            return existing
        return self._run_repository.update_status(
            run_id,
            RunStatus.FAILED,
            error_text="Run interrupted during shutdown.",
        )