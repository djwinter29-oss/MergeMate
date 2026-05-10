# Implementation: Repo-Level Knowledge Base

## Changes Made

### 1. SQLite Database — New `repo_knowledge` Table
**File:** `src/mergemate/infrastructure/persistence/sqlite.py`

- Added `repo_knowledge` table in `initialize()`: `(id INTEGER PK AUTOINCREMENT, chat_id INTEGER NOT NULL, repo_name TEXT NOT NULL, topic TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL)`
- Created index `idx_repo_knowledge_chat_repo` on `(chat_id, repo_name, created_at DESC)`
- Added `repo_name TEXT` column to `agent_runs` via `_ensure_column()` for future run-scoped repo tracking

### 2. New Repository — SQLiteRepoKnowledgeRepository
**File:** `src/mergemate/infrastructure/persistence/sqlite.py`

New class `SQLiteRepoKnowledgeRepository` (at line ~745):
- `record(chat_id, repo_name, topic, summary) -> None` — INSERT with current UTC timestamp
- `list_recent(chat_id, repo_name=None, limit=5) -> list[dict]` — SELECT with optional `repo_name` filter, ordered by `created_at DESC`

### 3. LearningService — 2 New Methods + Constructor Param
**File:** `src/mergemate/application/services/learning_service.py`

- Constructor now accepts `repo_knowledge_repository=None` (keyword-only, defaults to None for backward compat)
- Stores as `self._repo_knowledge_repository`
- `remember_repo_knowledge(*, chat_id, repo_name, topic, summary) -> None` — no-op when disabled or no repo_knowledge_repository
- `load_repo_knowledge(chat_id, repo_name=None) -> list[dict]` — no-op returns `[]` when disabled or no repo_knowledge_repository

### 4. PromptService — `repo_knowledge` Parameter
**File:** `src/mergemate/application/services/prompt_service.py`

- `render()` now accepts `repo_knowledge: list[dict[str, str]] | None = None`
- When provided, appends a "Current repository knowledge:" section with `- [repo_name] topic: summary` lines
- Backward compatible: callers not passing `repo_knowledge` get the old behavior

### 5. Orchestrator — Load + Pass Repo Knowledge
**File:** `src/mergemate/application/orchestrator.py`

- Calls `self._deps.learning_service.load_repo_knowledge(chat_id, repo_name=self._deps.settings.repo_name)` alongside existing `load_grouped_learnings()`
- Passes result to `prompt_service.render(..., repo_knowledge=repo_knowledge)`

### 6. AppConfig — `repo_name` Field
**File:** `src/mergemate/config/models.py`

- Added `repo_name: str | None = Field(default=None, description="Current repo name for session-scoped knowledge")`

### 7. Bootstrap — Wire Repository
**File:** `src/mergemate/bootstrap.py`

- Imported `SQLiteRepoKnowledgeRepository`
- Passes `SQLiteRepoKnowledgeRepository(database)` as `repo_knowledge_repository` to `LearningService`

## Backward Compatibility

- `repo_knowledge_repository=None` → both new methods are no-ops
- `repo_knowledge=None` (default) on `render()` → no repo section rendered
- `repo_name=None` on config → `load_repo_knowledge(chat_id, repo_name=None)` returns across all repos
- New `repo_name` column on `agent_runs` defaults to NULL for existing rows