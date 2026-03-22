"""Dispatch accepted work to the background worker."""

from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass(slots=True)
class DispatchResult:
    run_id: str
    status: str


class RunDispatcher:
    def __init__(self, worker) -> None:
        self._worker = worker

    def dispatch_run(
        self,
        run_id: str,
        on_finished: Callable[[object], Awaitable[None]] | None = None,
    ) -> DispatchResult:
        self._worker.enqueue(run_id, on_finished=on_finished)
        return DispatchResult(run_id=run_id, status="queued")