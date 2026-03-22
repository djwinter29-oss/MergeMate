"""Read the current run status."""


class GetRunStatusUseCase:
    def __init__(self, run_repository) -> None:
        self._run_repository = run_repository

    def execute(self, run_id: str | None = None, *, chat_id: int | None = None):
        if run_id is not None:
            return self._run_repository.get(run_id)
        if chat_id is None:
            raise ValueError("chat_id is required when run_id is not provided")
        runs = self._run_repository.list_for_chat(chat_id, limit=1)
        return runs[0] if runs else None