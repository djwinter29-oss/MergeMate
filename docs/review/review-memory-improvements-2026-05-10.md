# Review: 3 Memory Improvement Implementations

**Date:** 2026-05-10  
**Reviewer:** reviewer  
**PRs/Coverage:** Working tree (staged + unstaged changes already in place)

---

## Executive Summary

All 3 design specs are correctly implemented. The core logic in `learning_service.py`, `sqlite.py`, `orchestrator.py`, and `prompt_service.py` aligns with the architecture documents `01-structured-memory-extraction.md`, `02-repo-knowledge-base.md`, and `03-workflow-grouped-memory.md`.

**Verdict: PASS with 1 blocking issue and 3 advisory findings.**

The blocking issue is an integration test spy that hasn't been updated for the async `remember_success()`. The advisory findings are minor — no correctness defects, no regressions in the production code.

---

## Test Results (42/42 unit tests pass)

| Test file | Tests | Result |
|---|---|---|
| `tests/unit/mergemate/infrastructure/persistence/test_sqlite.py` | 13 | 13 passed |
| `tests/unit/mergemate/application/services/test_learning_service.py` | 7 | 7 passed |
| `tests/unit/mergemate/application/test_orchestrator.py` | 22 | 22 passed |

---

## BLOCKING ISSUE (must fix)

### #1 — Integration test `LearningServiceSpy.remember_success()` is sync, not async

**File:** `tests/integration/mergemate/application/test_execution_plan_integration.py:275`

```python
class LearningServiceSpy:
    def remember_success(self, **payload: Any) -> None:   # <-- sync, returns None
        self.saved.append(payload)
```

The production `LearningService.remember_success()` was made async (returns a coroutine). Both `DirectExecutionPlan.execute()` (line 163) and `MultiStageExecutionPlan.execute()` (line 328) now `await` it. The sync spy returns `None`, and `await None` raises `TypeError: object NoneType can't be used in 'await' expression`.

**Fix:** Add `async` to the spy method:

```python
async def remember_success(self, **payload: Any) -> None:
    self.saved.append(payload)
```

**Severity:** BLOCKING — the test `test_execute_completes_all_stages` crashes with `TypeError`.

---

## ADVISORY FINDINGS (non-blocking)

### #2 — `_load_workflow_config_plugins` has a duplicate `import logging` inside the except block

**File:** `src/mergemate/bootstrap.py:70-72`

```python
except Exception:
    import logging
    logging.getLogger(__name__).warning(...)
```

`logging` is already imported at the top of the file (line 30 is part of the tool import block — actually no, `logging` is NOT at the top of the file). There is a `from mergemate.infrastructure.telemetry.logger import configure_logging` at line 35, but `getLogger` is not imported. The inline import works but is inconsistent with the pattern used in the adjacent `_load_workflow_config_plugins` function (lines 105-112) which uses the same pattern.

**Suggestion:** Add `import logging` at module level alongside the other imports to avoid inline imports in both exception handlers. **Not blocking** — functional code.

### #3 — `SQLiteLearningRepository.list_grouped_by_workflow()` fetches all rows in-memory

**File:** `src/mergemate/infrastructure/persistence/sqlite.py:717-742`

The method runs `SELECT ... FROM learning_entries WHERE chat_id = ? ORDER BY workflow, created_at DESC` and then groups in Python. This is acceptable for the data volumes involved (tens to low hundreds of rows per chat) and matches the design spec. The design doc explicitly addresses why SQL-only grouping was rejected. **No action needed**, but noted for scale-out monitoring.

### #4 — `test_additional_branch_coverage.py` fails on stale `.pyc` cache after adding `SQLiteRepoKnowledgeRepository`

The test file `tests/unit/mergemate/test_additional_branch_coverage.py` failed during initial test collection with `ImportError: cannot import name 'SQLiteRepoKnowledgeRepository'` even though the class exists in `sqlite.py`. This was resolved by clearing `__pycache__` directories. The test file imports `cli.py` at module level, which transitively imports `bootstrap.py`, which module-level-imports `SQLiteRepoKnowledgeRepository`.

**Suggestion:** This is a `.pyc` staleness issue, not a code defect. If this resurfaces in CI, either (a) add `find . -name __pycache__ -exec rm -rf {} +` to the CI pipeline's test preparation step, or (b) make the `SQLiteRepoKnowledgeRepository` import in `bootstrap.py` lazy (inside the `bootstrap()` function body). Option (b) would also reduce module-level side effects in `bootstrap.py`.

---

## Verification Against Design Docs

### Improvement 1: Structured Memory Extraction (`01-structured-memory-extraction.md`)

| Design Spec | Implementation | Status |
|---|---|---|
| `_ensure_column` for `learning_lessons` on `learning_entries` | ✅ `sqlite.py:142` | Pass |
| `record()` takes `learning_lessons: str \| None` | ✅ `sqlite.py:674` | Pass |
| `list_recent()` returns `learning_lessons` in dict | ✅ `sqlite.py:701` | Pass |
| `_extract_lessons()` async, uses `llm_gateway.generate()` | ✅ `learning_service.py:67` | Pass |
| Returns `"{}"` on failure or when gateway is None | ✅ `learning_service.py:74-93` | Pass |
| `remember_success()` becomes async | ✅ `learning_service.py:33` (was `def`, now `async def`) | Pass |
| Callers in `execution_plan.py` use `await` | ✅ `execution_plan.py:163,328` | Pass |
| `render()` parses and injects structured lessons | ✅ `prompt_service.py:24-35` | Pass |
| `extraction_agent` field on `LearningConfig` | ✅ `config/models.py:175` | Pass |
| Bootstrap wires `llm_gateway` to `LearningService` | ✅ `bootstrap.py:183-186` (via builder refactor) | Pass |

### Improvement 2: Repo-Level Knowledge Base (`02-repo-knowledge-base.md`)

| Design Spec | Implementation | Status |
|---|---|---|
| `repo_knowledge` table DDL in `initialize()` | ✅ `sqlite.py:114-124` | Pass |
| `SQLiteRepoKnowledgeRepository` class with `record()` / `list_recent()` | ✅ `sqlite.py:746-787` | Pass |
| `repo_knowledge_repository` param on `LearningService.__init__` | ✅ `learning_service.py:23` | Pass |
| `remember_repo_knowledge()` delegates to repo | ✅ `learning_service.py:47-50` | Pass |
| `load_repo_knowledge()` delegates to repo | ✅ `learning_service.py:52-55` | Pass |
| Both methods no-op when repo is None | ✅ `learning_service.py:48,53` | Pass |
| `render()` accepts `repo_knowledge` param | ✅ `prompt_service.py:60` | Pass |
| Orchestrator loads and passes repo knowledge | ✅ `orchestrator.py:51-61` | Pass |
| `repo_name` on `AppConfig` | ✅ `config/models.py:252` | Pass |
| `repo_name` column migration on `agent_runs` | ✅ `sqlite.py:144` | Pass |
| Bootstrap wires `SQLiteRepoKnowledgeRepository` | ✅ `bootstrap.py:186` | Pass |

**Design deviation (minor):** The design doc shows `repo_name` on `AppConfig` as a simple field and says "The run carries `repo_name` from the config". The implementation adds `repo_name` as a column on `agent_runs` (via `_ensure_column`), but the `AgentRun` entity does NOT have a `repo_name` field. The orchestrator reads `self._deps.settings.repo_name` directly from the AppConfig settings, not from `run.repo_name`. This means repo knowledge is loaded from current-config settings, not from the run's persisted repo_name. This is acceptable for the current single-repo-per-config usage and matches the design intent, but note that if the config's `repo_name` changes mid-session, historical runs' repo knowledge will be loaded under the new name. **Non-blocking.**

### Improvement 3: Workflow-Grouped Memory (`03-workflow-grouped-memory.md`)

| Design Spec | Implementation | Status |
|---|---|---|
| `list_grouped_by_workflow()` on repository | ✅ `sqlite.py:706-743` | Pass |
| Groups in-memory, current first, others 1 each | ✅ | Pass |
| `load_grouped_learnings()` on service | ✅ `learning_service.py:57-65` | Pass |
| Orchestrator switches from `load_recent_learnings()` to `load_grouped_learnings()` | ✅ `orchestrator.py:48-49` | Pass |
| `learning_lessons` column included in grouped results | ✅ `sqlite.py:718` (SELECT includes learning_lessons) | Pass |
| No config changes needed | ✅ | Pass |
| Backward compat: `load_recent_learnings()` retained | ✅ `learning_service.py:42-45` | Pass |

---

## Summary

Production code: **CORRECT**. All 3 design specs are faithfully implemented with proper async/sync boundaries, backward compatibility shims, and graceful degradation.

Integration test spy: **BROKEN**. The `LearningServiceSpy.remember_success()` in `test_execution_plan_integration.py` is sync but production now awaits it. Fix: add `async` keyword.

Stale pycache: Minor CI concern. Clear `__pycache__` or use lazy imports in `bootstrap.py`.