"""Cancel a queued or running job."""

from mergemate.domain.runs.value_objects import RunStatus


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

        return self._run_repository.update_status(target_run.run_id, RunStatus.CANCELLED)