# Improvement 1: Structured Memory Extraction — Implementation

Implements the architecture from `docs/architecture/01-structured-memory-extraction.md`.

## Changes Made

### 1. Schema Migration — `learning_lessons` column

**File:** `src/mergemate/infrastructure/persistence/sqlite.py`

- Added `_ensure_column(connection, "learning_entries", "learning_lessons", "TEXT")` in `SQLiteDatabase.initialize()`
- `SQLiteLearningRepository.record()` accepts `learning_lessons: str | None = None` and includes it in the INSERT
- `SQLiteLearningRepository.list_recent()` SELECTs and returns `learning_lessons` in each dict

### 2. LearningService — `_extract_lessons()` and async `remember_success()`

**File:** `src/mergemate/application/services/learning_service.py`

- Constructor accepts optional `llm_gateway` and `extraction_agent_name` (defaults to `"default"`)
- `_extract_lessons(result_text) -> str` — async method. If `llm_gateway` is None, returns `"{}"` immediately. Otherwise calls `llm_gateway.generate()` with a structured extraction system prompt. Validates JSON response and ensures all 4 keys exist. On any failure, returns `"{}"` silently (best-effort, no pipeline block)
- `remember_success()` is now `async` — calls `await self._extract_lessons(result_text)` before recording

### 3. PromptService — structured rendering

**File:** `src/mergemate/application/services/prompt_service.py`

- Extracted `_build_learning_lines()` helper method
- When `learning_lessons` is present and parseable, renders `technical_points`, `pitfalls`, and `conclusion` lines
- Handles `None` and malformed JSON gracefully (silently skipped)
- Raw excerpt rendering preserved as fallback

### 4. Callers — `await remember_success()`

**File:** `src/mergemate/application/execution_plan.py`

- `DirectExecutionPlan.execute()` line 151: added `await`
- `MultiStageExecutionPlan.execute()` line 316: added `await`

### 5. Config — `LearningConfig.extraction_agent`

**File:** `src/mergemate/config/models.py`

- Added `extraction_agent: str | None = None` to `LearningConfig`

### 6. Bootstrap

**File:** `src/mergemate/bootstrap.py`

- Moved `LearningService` construction after `llm_gateway` creation (to satisfy dependency order)
- Wired `llm_gateway` and `settings.learning.extraction_agent` into `LearningService` constructor

## Verification

- `_extract_lessons()` returns `"{}"` when `llm_gateway` is `None` (tested)
- `LearningConfig` now has `extraction_agent` field (tested)
- PromptService rendering handles all three cases: structured JSON, None, malformed JSON
- All files pass Python syntax checks (no lint errors introduced)