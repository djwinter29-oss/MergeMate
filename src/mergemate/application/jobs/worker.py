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

    def enqueue(
        self,
        run_id: str,
        on_finished: Callable[[object], Awaitable[None]] | None = None,
    ) -> None:
        task = asyncio.create_task(self._consume(run_id, on_finished=on_finished))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _consume(
        self,
        run_id: str,
        on_finished: Callable[[object], Awaitable[None]] | None = None,
    ) -> None:
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

            if on_finished is not None and run is not None:
                await on_finished(run)