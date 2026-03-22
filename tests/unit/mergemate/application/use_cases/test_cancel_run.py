from dataclasses import dataclass

from mergemate.application.use_cases.cancel_run import CancelRunUseCase
from mergemate.domain.runs.value_objects import RunStatus


@dataclass(slots=True)
class RunStub:
    run_id: str
    chat_id: int


class RunRepositoryStub:
    def __init__(self) -> None:
        self.run = RunStub("run-1", 10)
        self.updated = []

    def get(self, run_id: str):
        return self.run if run_id == "run-1" else None

    def list_for_chat(self, chat_id: int, limit: int = 1):
        return [self.run] if chat_id == 10 else []

    def update_status(self, run_id: str, status: RunStatus, *, current_stage=None, result_text=None, error_text=None):
        self.updated.append((run_id, status))
        return {"run_id": run_id, "status": status}


def test_cancel_run_by_run_id_and_chat_scope() -> None:
    repository = RunRepositoryStub()
    use_case = CancelRunUseCase(repository)

    assert use_case.execute("run-1", chat_id=99) is None
    result = use_case.execute("run-1", chat_id=10)

    assert result == {"run_id": "run-1", "status": RunStatus.CANCELLED}
    assert repository.updated == [("run-1", RunStatus.CANCELLED)]


def test_cancel_run_uses_latest_for_chat_and_none_when_missing() -> None:
    repository = RunRepositoryStub()
    use_case = CancelRunUseCase(repository)

    assert use_case.execute(chat_id=99) is None
    result = use_case.execute(chat_id=10)

    assert result == {"run_id": "run-1", "status": RunStatus.CANCELLED}
