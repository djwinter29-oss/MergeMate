from datetime import UTC, datetime, timedelta
import sqlite3
from pathlib import Path

from mergemate.infrastructure.persistence.sqlite import SQLiteDatabase, SQLiteLearningRepository


def _seed_learning_entries(
    database_path: Path, rows: list[tuple[int, str, str, str, str | None, str]]
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE learning_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                workflow TEXT NOT NULL,
                prompt TEXT NOT NULL,
                result_excerpt TEXT NOT NULL,
                learning_lessons TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO learning_entries (
                chat_id, workflow, prompt, result_excerpt, learning_lessons, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _iso(base: datetime, seconds: int) -> str:
    return (base + timedelta(seconds=seconds)).isoformat()


def test_list_grouped_by_workflow_limits_current_workflow_and_other_workflows(tmp_path) -> None:
    database_path = tmp_path / "state.db"
    base = datetime(2026, 1, 1, tzinfo=UTC)
    _seed_learning_entries(
        database_path,
        [
            (7, "debug_code", "debug-new", "debug-excerpt-new", None, _iso(base, 5)),
            (7, "debug_code", "debug-old", "debug-excerpt-old", None, _iso(base, 4)),
            (
                7,
                "generate_code",
                "generate-4",
                "generate-excerpt-4",
                '{"lesson": 4}',
                _iso(base, 3),
            ),
            (
                7,
                "generate_code",
                "generate-3",
                "generate-excerpt-3",
                '{"lesson": 3}',
                _iso(base, 2),
            ),
            (
                7,
                "generate_code",
                "generate-2",
                "generate-excerpt-2",
                '{"lesson": 2}',
                _iso(base, 1),
            ),
            (
                7,
                "generate_code",
                "generate-1",
                "generate-excerpt-1",
                '{"lesson": 1}',
                _iso(base, 0),
            ),
            (7, "plan_code", "plan-new", "plan-excerpt-new", None, _iso(base, 6)),
            (7, "plan_code", "plan-old", "plan-excerpt-old", None, _iso(base, -1)),
        ],
    )

    repository = SQLiteLearningRepository(SQLiteDatabase(database_path))

    results = repository.list_grouped_by_workflow(
        chat_id=7,
        current_workflow="generate_code",
        same_workflow_limit=2,
        other_workflow_limit=1,
    )

    assert results == [
        {
            "workflow": "generate_code",
            "prompt": "generate-4",
            "result_excerpt": "generate-excerpt-4",
            "learning_lessons": '{"lesson": 4}',
        },
        {
            "workflow": "generate_code",
            "prompt": "generate-3",
            "result_excerpt": "generate-excerpt-3",
            "learning_lessons": '{"lesson": 3}',
        },
        {
            "workflow": "debug_code",
            "prompt": "debug-new",
            "result_excerpt": "debug-excerpt-new",
            "learning_lessons": None,
        },
        {
            "workflow": "plan_code",
            "prompt": "plan-new",
            "result_excerpt": "plan-excerpt-new",
            "learning_lessons": None,
        },
    ]


def test_list_grouped_by_workflow_returns_other_workflows_when_current_workflow_missing(
    tmp_path,
) -> None:
    database_path = tmp_path / "state.db"
    base = datetime(2026, 1, 1, tzinfo=UTC)
    _seed_learning_entries(
        database_path,
        [
            (11, "debug_code", "debug-new", "debug-excerpt-new", None, _iso(base, 2)),
            (11, "debug_code", "debug-old", "debug-excerpt-old", None, _iso(base, 1)),
            (11, "plan_code", "plan-new", "plan-excerpt-new", None, _iso(base, 4)),
            (11, "plan_code", "plan-old", "plan-excerpt-old", None, _iso(base, 3)),
        ],
    )

    repository = SQLiteLearningRepository(SQLiteDatabase(database_path))

    results = repository.list_grouped_by_workflow(
        chat_id=11,
        current_workflow="generate_code",
        same_workflow_limit=3,
        other_workflow_limit=1,
    )

    assert results == [
        {
            "workflow": "debug_code",
            "prompt": "debug-new",
            "result_excerpt": "debug-excerpt-new",
            "learning_lessons": None,
        },
        {
            "workflow": "plan_code",
            "prompt": "plan-new",
            "result_excerpt": "plan-excerpt-new",
            "learning_lessons": None,
        },
    ]
