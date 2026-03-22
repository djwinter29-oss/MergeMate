from datetime import UTC, datetime

from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStatus
from mergemate.infrastructure.persistence.sqlite import SQLiteDatabase, SQLiteRunRepository


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

    assert approved is not None
    assert approved.status == RunStatus.COMPLETED
    assert approved.current_stage == "completed"
    assert approved.approved is True
