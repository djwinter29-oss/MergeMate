"""Read the current run status."""


class GetRunStatusUseCase:
    def __init__(self, run_repository) -> None:
        self._run_repository = run_repository

    def execute(self, run_id: str | None = None, *, chat_id: int | None = None):
        if run_id is not None:
            run = self._run_repository.get(run_id)
            if run is None:
                return None
            if chat_id is not None and run.chat_id != chat_id:
                return None
            return run
        if chat_id is None:
            raise ValueError("chat_id is required when run_id is not provided")
        runs = self._run_repository.list_for_chat(chat_id, limit=1)
        return runs[0] if runs else None