from datetime import UTC, datetime
import sqlite3

from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus
from mergemate.infrastructure.persistence.sqlite import (
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteLearningRepository,
    SQLiteRunRepository,
    SQLiteToolEventRepository,
)


def _build_run(run_id: str = "run-1") -> AgentRun:
    now = datetime.now(UTC)
    return AgentRun(
        run_id=run_id,
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.AWAITING_CONFIRMATION,
        current_stage="planning",
        prompt="build a bot",
        estimate_seconds=30,
        plan_text=None,
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )


def test_update_plan_can_use_internal_replanning_stage(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    repository = SQLiteRunRepository(database)
    repository.create(_build_run())

    updated = repository.update_plan(
        "run-1",
        "updated plan",
        current_stage="internal_replanning",
    )

    assert updated is not None
    assert updated.current_stage == "internal_replanning"
    assert updated.plan_text == "updated plan"
    assert updated.status == RunStatus.AWAITING_CONFIRMATION


def test_approve_does_not_transition_completed_run(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    repository = SQLiteRunRepository(database)
    run = _build_run()
    run.status = RunStatus.COMPLETED
    run.current_stage = "completed"
    run.approved = True
    repository.create(run)

    approved = repository.approve("run-1")

    assert approved.run is not None
    assert approved.transitioned is False
    assert approved.run.status == RunStatus.COMPLETED
    assert approved.run.current_stage == "completed"
    assert approved.run.approved is True


def test_approve_marks_queued_run_as_approved_without_resetting_stage(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    repository = SQLiteRunRepository(database)
    run = _build_run()
    run.status = RunStatus.QUEUED
    run.current_stage = "queued_for_execution"
    repository.create(run)

    approved = repository.approve("run-1")

    assert approved.run is not None
    assert approved.transitioned is True
    assert approved.run.status == RunStatus.QUEUED
    assert approved.run.current_stage == "queued_for_execution"
    assert approved.run.approved is True


def test_run_repository_round_trip_and_updates(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    repository = SQLiteRunRepository(database)
    run = _build_run()
    repository.create(run)

    loaded = repository.get("run-1")
    assert loaded is not None
    assert loaded.prompt == "build a bot"

    updated = repository.update_status(
        "run-1",
        RunStatus.RUNNING,
        current_stage="implementation",
        result_text="partial",
        error_text="warning",
    )
    assert updated is not None
    assert updated.status == RunStatus.RUNNING
    assert updated.current_stage == "implementation"
    assert updated.result_text == "partial"
    assert updated.error_text == "warning"

    preserved = repository.update_status(
        "run-1",
        RunStatus.CANCELLED,
        expected_current_status=RunStatus.AWAITING_CONFIRMATION,
    )
    assert preserved is not None
    assert preserved.status == RunStatus.RUNNING

    artifacted = repository.save_artifacts(
        "run-1",
        current_stage="review",
        design_text="design",
        test_text="tests",
        review_text="review",
        result_text="implementation",
        review_iterations=2,
    )
    assert artifacted is not None
    assert artifacted.design_text == "design"
    assert artifacted.test_text == "tests"
    assert artifacted.review_text == "review"
    assert artifacted.result_text == "implementation"
    assert artifacted.review_iterations == 2

    listed = repository.list_for_chat(1)
    assert [item.run_id for item in listed] == ["run-1"]
    assert repository.get("missing") is None
    assert repository.update_status("missing", RunStatus.FAILED) is None
    assert repository.update_plan("missing", "plan") is None
    approved_missing = repository.approve("missing")
    assert approved_missing.run is None
    assert approved_missing.transitioned is False
    assert repository.save_artifacts("missing", result_text="x") is None


def test_conversation_and_learning_repositories_preserve_order_and_limit(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()

    conversations = SQLiteConversationRepository(database)
    conversations.append_message(1, "user", "first")
    conversations.append_message(1, "assistant", "second")
    conversations.append_message(1, "user", "third")

    assert conversations.list_messages(1, limit=2) == [
        {"role": "assistant", "content": "second"},
        {"role": "user", "content": "third"},
    ]

    learning = SQLiteLearningRepository(database)
    learning.record(1, "generate_code", "p1", "r1")
    learning.record(1, "debug_code", "p2", "r2")

    assert learning.list_recent(1, limit=2) == [
        {"workflow": "debug_code", "prompt": "p2", "result_excerpt": "r2"},
        {"workflow": "generate_code", "prompt": "p1", "result_excerpt": "r1"},
    ]


def test_database_initialize_handles_existing_schema_and_non_approvable_status(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    database.initialize()

    repository = SQLiteRunRepository(database)
    run = _build_run("run-2")
    run.status = RunStatus.FAILED
    repository.create(run)

    approved = repository.approve("run-2")

    assert approved.run is not None
    assert approved.transitioned is False
    assert approved.run.status == RunStatus.FAILED


def test_approve_is_atomic_after_first_transition(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    repository = SQLiteRunRepository(database)
    repository.create(_build_run())

    first = repository.approve("run-1")
    second = repository.approve("run-1")

    assert first.run is not None
    assert first.transitioned is True
    assert second.run is not None
    assert second.transitioned is False
    assert second.run.status == RunStatus.QUEUED


def test_try_update_status_reports_lost_transition(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    repository = SQLiteRunRepository(database)
    run = _build_run()
    run.status = RunStatus.RUNNING
    run.current_stage = "retrieve_context"
    repository.create(run)

    decision = repository.try_update_status(
        "run-1",
        RunStatus.WAITING_TOOL,
        expected_current_status=RunStatus.QUEUED,
        current_stage="tool:git_repository",
    )

    assert decision.run is not None
    assert decision.transitioned is False
    assert decision.run.status == RunStatus.RUNNING
    assert decision.run.current_stage == "retrieve_context"


def test_ensure_column_adds_missing_column(tmp_path) -> None:
    database_path = tmp_path / "state.db"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

    SQLiteDatabase._ensure_column(connection, "sample", "extra", "TEXT")

    columns = {row["name"] for row in connection.execute("PRAGMA table_info(sample)").fetchall()}
    connection.close()

    assert "extra" in columns


def test_tool_event_repository_records_and_lists_events(tmp_path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    database.initialize()
    repository = SQLiteToolEventRepository(database)

    repository.record("run-1", "syntax_checker", "check", "started", "Invoking tool.")
    repository.record("run-1", "syntax_checker", "check", "ok", "done")
    repository.record("run-2", "git_repository", "status", "ok", "clean")

    assert repository.list_for_run("run-1", limit=1) == [
        {
            "tool_name": "syntax_checker",
            "action": "check",
            "status": "ok",
            "detail": "done",
            "created_at": repository.list_for_run("run-1", limit=1)[0]["created_at"],
        }
    ]
    listed = repository.list_for_run("run-1", limit=5)
    assert listed == [
        {
            "tool_name": "syntax_checker",
            "action": "check",
            "status": "ok",
            "detail": "done",
            "created_at": listed[0]["created_at"],
        },
        {
            "tool_name": "syntax_checker",
            "action": "check",
            "status": "started",
            "detail": "Invoking tool.",
            "created_at": listed[1]["created_at"],
        },
    ]
    assert repository.list_for_run("missing") == []
