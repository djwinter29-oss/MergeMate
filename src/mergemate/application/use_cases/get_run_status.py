"""Read the current run status."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class RunStatusSnapshot:
    run: object
    tool_events: list[dict[str, str]] = field(default_factory=list)

    def __getattr__(self, name: str):
        return getattr(self.run, name)

    @property
    def latest_tool_event(self) -> dict[str, str] | None:
        return self.tool_events[0] if self.tool_events else None


class GetRunStatusUseCase:
    def __init__(self, run_repository, tool_event_repository=None) -> None:
        self._run_repository = run_repository
        self._tool_event_repository = tool_event_repository

    def _build_snapshot(self, run, *, tool_event_limit: int = 5):
        tool_events = []
        if self._tool_event_repository is not None:
            tool_events = self._tool_event_repository.list_for_run(run.run_id, limit=tool_event_limit)
        return RunStatusSnapshot(run=run, tool_events=tool_events)

    def execute(self, run_id: str | None = None, *, chat_id: int | None = None, tool_event_limit: int = 5):
        if run_id is not None:
            run = self._run_repository.get(run_id)
            if run is None:
                return None
            if chat_id is not None and run.chat_id != chat_id:
                return None
            return self._build_snapshot(run, tool_event_limit=tool_event_limit)
        if chat_id is None:
            raise ValueError("chat_id is required when run_id is not provided")
        runs = self._run_repository.list_for_chat(chat_id, limit=1)
        if not runs:
            return None
        return self._build_snapshot(runs[0], tool_event_limit=tool_event_limit)