# Repo-Level Knowledge Base

## Overview

**Problem:** All learning knowledge is scoped to `chat_id`. When MergeMate
manages multiple projects in the same chat (or when the same agent context
switches between repos), memories from different projects mix together, leaking
context and causing irrelevant suggestions.

**Goal:** Introduce a `repo_knowledge` table scoped by `(chat_id, repo_name)`,
expose `remember_repo_knowledge()` and `load_repo_knowledge()` on
`LearningService`, inject repo-specific knowledge alongside general learning in
`PromptService.render()`, and add `repo_name` to `AppConfig`.

---

## Design

### 1. New Table — `repo_knowledge`

File: `src/mergemate/infrastructure/persistence/sqlite.py`

Add to `SQLiteDatabase.initialize()`:

```python
CREATE TABLE IF NOT EXISTS repo_knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    repo_name TEXT NOT NULL,
    topic TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_repo_knowledge_chat_repo
    ON repo_knowledge(chat_id, repo_name, created_at DESC);
```

**Columns:**

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `chat_id` | INTEGER NOT NULL | Chat/thread scope |
| `repo_name` | TEXT NOT NULL | Repo identifier (e.g. "hermes-agent", "MergeMate") |
| `topic` | TEXT NOT NULL | Short topic label (e.g. "project structure", "dependency injection pattern") |
| `summary` | TEXT NOT NULL | Knowledge summary (what was learned, up to ~2000 chars) |
| `created_at` | TEXT NOT NULL | ISO 8601 timestamp |

### 2. New Repository Class — `SQLiteRepoKnowledgeRepository`

File: `src/mergemate/infrastructure/persistence/sqlite.py`

```python
class SQLiteRepoKnowledgeRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(self, chat_id: int, repo_name: str, topic: str, summary: str) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """INSERT INTO repo_knowledge (chat_id, repo_name, topic, summary, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (chat_id, repo_name, topic, summary, datetime.now(UTC).isoformat()),
            )

    def list_recent(self, chat_id: int, repo_name: str | None = None,
                    limit: int = 5) -> list[dict[str, str]]:
        with self._database.connection() as connection:
            if repo_name is not None:
                rows = connection.execute(
                    """SELECT repo_name, topic, summary
                       FROM repo_knowledge
                       WHERE chat_id = ? AND repo_name = ?
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (chat_id, repo_name, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT repo_name, topic, summary
                       FROM repo_knowledge
                       WHERE chat_id = ?
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (chat_id, limit),
                ).fetchall()
        return [
            {"repo_name": row["repo_name"], "topic": row["topic"],
             "summary": row["summary"]}
            for row in rows
        ]
```

### 3. LearningService Changes

File: `src/mergemate/application/services/learning_service.py`

**Constructor** adds `repo_knowledge_repository`:

```python
class LearningService:
    def __init__(self, learning_repository, repo_knowledge_repository=None,
                 enabled: bool, max_context_items: int, max_result_chars: int,
                 llm_gateway=None, extraction_agent_name: str | None = None) -> None:
        self._learning_repository = learning_repository
        self._repo_knowledge_repository = repo_knowledge_repository
        ...
```

**New method `remember_repo_knowledge()`:**

```python
def remember_repo_knowledge(self, *, chat_id: int, repo_name: str,
                             topic: str, summary: str) -> None:
    if not self._enabled or self._repo_knowledge_repository is None:
        return
    self._repo_knowledge_repository.record(chat_id, repo_name, topic, summary)
```

**New method `load_repo_knowledge()`:**

```python
def load_repo_knowledge(self, chat_id: int,
                        repo_name: str | None = None) -> list[dict[str, str]]:
    if not self._enabled or self._repo_knowledge_repository is None:
        return []
    return self._repo_knowledge_repository.list_recent(
        chat_id, repo_name=repo_name, limit=self._max_context_items,
    )
```

### 4. PromptService Changes

File: `src/mergemate/application/services/prompt_service.py`

**`render()` signature** adds a `repo_knowledge` parameter:

```python
def render(
    self,
    workflow: str,
    recent_messages: list[dict[str, str]],
    learned_items: list[dict[str, str]],
    user_prompt: str,
    repo_knowledge: list[dict[str, str]] | None = None,
) -> tuple[str, str]:
```

**Injection logic** (appended after learning lines, before user prompt):

```python
if repo_knowledge:
    repo_lines = ["\nCurrent repository knowledge:"]
    for item in repo_knowledge:
        repo_lines.append(f"- [{item['repo_name']}] {item['topic']}: {item['summary']}")
    contextual_user_prompt += "\n" + "\n".join(repo_lines)
```

### 5. Orchestrator Changes

File: `src/mergemate/application/orchestrator.py`

In `process_run()`, load repo knowledge alongside learned items:

```python
learned_items = self._deps.learning_service.load_recent_learnings(run.chat_id)
repo_knowledge = self._deps.learning_service.load_repo_knowledge(
    run.chat_id, repo_name=run.repo_name,
)

system_prompt, context_text = self._deps.prompt_service.render(
    run.workflow,
    recent_messages,
    learned_items,
    run.prompt,
    repo_knowledge=repo_knowledge,
)
```

### 6. AppConfig Changes

File: `src/mergemate/config/models.py`

**New field** on `AppConfig`:

```python
repo_name: str | None = Field(default=None, description="Current repo name for session-scoped knowledge")
```

**On Run model** (`agent_runs` table), add `repo_name`:

```python
# In SQLiteDatabase.initialize():
self._ensure_column(connection, "agent_runs", "repo_name", "TEXT")
```

The run carries `repo_name` from the config, persisted at creation time. This
allows different runs within the same chat to have different repo_name values
(useful for multi-repo workflows).

### 7. Bootstrap Changes

File: `src/mergemate/bootstrap.py`

```python
repo_knowledge_repository = SQLiteRepoKnowledgeRepository(database)

learning_service = LearningService(
    learning_repository=SQLiteLearningRepository(database),
    repo_knowledge_repository=repo_knowledge_repository,
    ...
)
```

**`MergeMateRuntime`** adds `repo_knowledge_repository` if needed. The config
`app.repo_name` is read when creating runs.

### 8. Backward Compatibility

- `repo_knowledge_repository=None` → `remember_repo_knowledge()` and
  `load_repo_knowledge()` are no-ops returning `[]`.
- `repo_name=None` on a run → `load_repo_knowledge(chat_id, repo_name=None)`
  returns repo knowledge across all repos (not scoped to one).
- Existing `PromptService.render()` callers that don't pass `repo_knowledge`
  default to `None` → no repo knowledge section rendered.
- New `repo_name` column on `agent_runs` defaults to NULL for existing rows.

### 9. What to Test (for tester task)

1. `SQLiteRepoKnowledgeRepository.record()` inserts a row correctly.
2. `list_recent()` with `repo_name` returns only that repo's knowledge.
3. `list_recent()` without `repo_name` returns all repos' knowledge.
4. `LearningService.remember_repo_knowledge()` delegates to repository.
5. `LearningService.load_repo_knowledge()` delegates to repository.
6. Both methods are no-ops when `_repo_knowledge_repository` is None.
7. `PromptService.render()` includes repo knowledge section when provided.
8. `PromptService.render()` renders correctly when `repo_knowledge` is None.
9. Orchestrator `process_run()` passes `repo_knowledge` to `render()`.
10. Bootstrap wires `SQLiteRepoKnowledgeRepository` into `LearningService`.
11. `repo_name` column migration via `_ensure_column`.

---

## Files Changed

| File | Change |
|------|--------|
| `config/models.py` | Add `AppConfig.repo_name` field |
| `infrastructure/persistence/sqlite.py` | New `SQLiteRepoKnowledgeRepository` class + table DDL in `initialize()` |
| `application/services/learning_service.py` | New `repo_knowledge_repository` param + 2 methods |
| `application/services/prompt_service.py` | `repo_knowledge` param in `render()` |
| `application/orchestrator.py` | Call `load_repo_knowledge()` + pass to `render()` |
| `bootstrap.py` | Wire `SQLiteRepoKnowledgeRepository` |
| Tests | See section 9 above |

---

## Integration with Workflow

Repo knowledge is populated **manually** via a tool or hook, not automatically
on every run (unlike learning entries). Suggested integration points:

- **Slash command** `@remember <topic> <summary>` — calls
  `learning_service.remember_repo_knowledge()`
- **Chronicle hook** — optionally calls `remember_repo_knowledge()` if the
  lesson content references repo-specific patterns

This keeps write paths explicit and avoids flooding the repo knowledge table
with auto-generated noise.