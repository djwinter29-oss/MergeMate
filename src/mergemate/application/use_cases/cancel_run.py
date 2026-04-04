"""Cancel a run that is still awaiting confirmation."""

from dataclasses import dataclass

from mergemate.domain.runs.value_objects import RunStatus


@dataclass(slots=True)
class CancelRunResult:
    run_id: str
    cancelled: bool
    status: str


class CancelRunUseCase:
    def __init__(self, run_repository) -> None:
        self._run_repository = run_repository

    def execute(self, run_id: str | None = None, *, chat_id: int | None = None):
        target_run = None
        if run_id is not None:
            target_run = self._run_repository.get(run_id)
            if target_run is not None and chat_id is not None and target_run.chat_id != chat_id:
                return None
        elif chat_id is not None:
            runs = self._run_repository.list_for_chat(chat_id, limit=1)
            target_run = runs[0] if runs else None

        if target_run is None:
            return None

        if target_run.status != RunStatus.AWAITING_CONFIRMATION:
            return CancelRunResult(
                run_id=target_run.run_id,
                cancelled=False,
                status=target_run.status.value,
            )

        cancelled_run = self._run_repository.update_status(
            target_run.run_id,
            RunStatus.CANCELLED,
            expected_current_status=RunStatus.AWAITING_CONFIRMATION,
        )
        if cancelled_run is None:
            return None
        if cancelled_run.status != RunStatus.CANCELLED:
            return CancelRunResult(
                run_id=cancelled_run.run_id,
                cancelled=False,
                status=cancelled_run.status.value,
            )
        return CancelRunResult(
            run_id=target_run.run_id,
            cancelled=True,
            status=RunStatus.CANCELLED.value,
        )