from dataclasses import dataclass

from mergemate.application.use_cases.get_run_status import GetRunStatusUseCase


@dataclass(slots=True)
class RunStub:
    run_id: str
    chat_id: int


class RunRepositoryStub:
    def __init__(self) -> None:
        self.run = RunStub("run-1", 10)

    def get(self, run_id: str):
        return self.run if run_id == "run-1" else None

    def list_for_chat(self, chat_id: int, limit: int = 1):
        return [self.run] if chat_id == 10 else []


class ToolEventRepositoryStub:
    def __init__(self) -> None:
        self.calls = []

    def list_for_run(self, run_id: str, limit: int = 5):
        self.calls.append((run_id, limit))
        return [{"tool_name": "syntax_checker", "action": "check", "status": "ok", "detail": "done"}]


def test_execute_returns_run_by_id_when_chat_matches() -> None:
    use_case = GetRunStatusUseCase(RunRepositoryStub())

    result = use_case.execute("run-1", chat_id=10)

    assert result is not None
    assert result.run_id == "run-1"


def test_execute_rejects_run_from_other_chat() -> None:
    use_case = GetRunStatusUseCase(RunRepositoryStub())

    assert use_case.execute("run-1", chat_id=99) is None


def test_execute_returns_none_for_missing_run_id() -> None:
    use_case = GetRunStatusUseCase(RunRepositoryStub())

    assert use_case.execute("missing", chat_id=10) is None


def test_execute_returns_none_when_chat_has_no_runs() -> None:
    use_case = GetRunStatusUseCase(RunRepositoryStub())

    assert use_case.execute(chat_id=99) is None


def test_execute_uses_latest_run_for_chat_and_requires_chat_when_no_id() -> None:
    use_case = GetRunStatusUseCase(RunRepositoryStub())

    assert use_case.execute(chat_id=10).run_id == "run-1"

    try:
        use_case.execute()
    except ValueError as exc:
        assert "chat_id is required" in str(exc)
    else:
        raise AssertionError("Expected ValueError when chat_id is missing")


def test_execute_includes_recent_tool_events_when_repository_is_configured() -> None:
    tool_event_repository = ToolEventRepositoryStub()
    use_case = GetRunStatusUseCase(RunRepositoryStub(), tool_event_repository)

    result = use_case.execute("run-1", chat_id=10)

    assert result is not None
    assert result.tool_events == [
        {"tool_name": "syntax_checker", "action": "check", "status": "ok", "detail": "done"}
    ]
    assert result.latest_tool_event == {
        "tool_name": "syntax_checker",
        "action": "check",
        "status": "ok",
        "detail": "done",
    }
    assert tool_event_repository.calls == [("run-1", 5)]


def test_execute_uses_custom_tool_event_limit_when_requested() -> None:
    tool_event_repository = ToolEventRepositoryStub()
    use_case = GetRunStatusUseCase(RunRepositoryStub(), tool_event_repository)

    result = use_case.execute(chat_id=10, tool_event_limit=12)

    assert result is not None
    assert tool_event_repository.calls == [("run-1", 12)]
