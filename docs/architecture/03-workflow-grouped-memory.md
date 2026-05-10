# Workflow-Grouped Memory Injection

## Overview

**Problem:** `LearningService.load_recent_learnings(chat_id, limit=3)` returns
the 3 most recent entries across **all** workflows. If the user switches between
workflows (e.g. `generate_code` then `debug_code` then back to `generate_code`),
the 3 results may contain 0 entries from the current workflow, losing relevant
historical context.

**Goal:** Group learning entries by workflow. For the **current workflow**, load
top-N entries (default 3). For **each other workflow** with entries, load at
least top-1. This ensures the LLM sees both focused prior context for the same
workflow and a signal (at least one entry) from each other workflow.

---

## Design

### 1. New Query — `list_grouped_by_workflow`

File: `src/mergemate/infrastructure/persistence/sqlite.py`

**`SQLiteLearningRepository`** gets a new method:

```python
def list_grouped_by_workflow(self, chat_id: int, current_workflow: str,
                              same_workflow_limit: int = 3,
                              other_workflow_limit: int = 1) -> list[dict[str, str]]:
    """Return learning entries grouped by workflow.

    - ``same_workflow_limit``: how many entries to return from the
      current workflow (default 3).
    - ``other_workflow_limit``: how many entries to return from each
      *other* workflow (default 1 — enough to signal existence).
    """
    with self._database.connection() as connection:
        rows = connection.execute(
            """SELECT workflow, prompt, result_excerpt, learning_lessons
               FROM learning_entries
               WHERE chat_id = ?
               ORDER BY workflow, created_at DESC""",
            (chat_id,),
        ).fetchall()

    # Group by workflow
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        wf = row["workflow"]
        if wf not in groups:
            groups[wf] = []
        groups[wf].append({
            "workflow": wf,
            "prompt": row["prompt"],
            "result_excerpt": row["result_excerpt"],
            "learning_lessons": row["learning_lessons"],
        })

    current_entries = groups.pop(current_workflow, [])[:same_workflow_limit]

    other_entries: list[dict[str, str]] = []
    for wf, entries in groups.items():
        other_entries.extend(entries[:other_workflow_limit])

    return current_entries + other_entries
```

**Why not SQL-only grouping?** The `ORDER BY workflow, created_at DESC` +
in-memory grouping approach is simpler, more maintainable, and the data volumes
(typically tens to low hundreds of rows per workflow) make in-memory grouping
negligible. A SQL-native approach (window functions or subqueries) would be
over-engineering.

### 2. LearningService Changes

File: `src/mergemate/application/services/learning_service.py`

**New method `load_grouped_learnings()`:**

```python
def load_grouped_learnings(self, chat_id: int,
                            current_workflow: str) -> list[dict[str, str]]:
    if not self._enabled:
        return []
    return self._learning_repository.list_grouped_by_workflow(
        chat_id=chat_id,
        current_workflow=current_workflow,
        same_workflow_limit=self._max_context_items,
        other_workflow_limit=1,
    )
```

**Backward compat:** `load_recent_learnings()` is retained for existing callers
that don't know about workflow grouping. The orchestrator is the sole changed
caller.

### 3. Orchestrator Changes

File: `src/mergemate/application/orchestrator.py`

In `process_run()`, replace:

```python
learned_items = self._deps.learning_service.load_recent_learnings(run.chat_id)
```

with:

```python
learned_items = self._deps.learning_service.load_grouped_learnings(
    run.chat_id, current_workflow=run.workflow,
)
```

### 4. LearningRepository Interface Change

The interface (`SQLiteLearningRepository` is concrete, not abstract) gets one
new method. Tests use the real class or monkeypatch.

### 5. Config Impact

No config changes needed. `max_context_items` (default 3) controls
`same_workflow_limit`. `other_workflow_limit` is hardcoded to 1 — this is the
"at least one signal" pattern. If users want to tune this, a config field can
be added later.

### 6. Backward Compatibility

- Existing `load_recent_learnings()` unchanged.
- Only `orchestrator.py` switches to the new method.
- No schema changes.
- No new dependencies.

### 7. What to Test (for tester task)

1. `list_grouped_by_workflow()` with 5 entries for current workflow and 3 for
   other → returns 3 current + 1 other (total 4).
2. `list_grouped_by_workflow()` with entries from only current workflow →
   returns up to `same_workflow_limit` entries.
3. `list_grouped_by_workflow()` with entries from only other workflows →
   returns 1 per other workflow.
4. `list_grouped_by_workflow()` with no entries at all → returns `[]`.
5. `list_grouped_by_workflow()` with `same_workflow_limit > available entries`
   → returns all available from current workflow.
6. `load_grouped_learnings()` delegates to repository correctly.
7. `load_grouped_learnings()` returns `[]` when disabled.
8. Orchestrator calls `load_grouped_learnings()` instead of
   `load_recent_learnings()`.
9. `learning_lessons` column is included in the grouped results.
10. When a workflow name appears that's not in any entry (empty dict after
    pop), current_entries is empty list, not missing key error.

### 8. Edge Case — Current Workflow Has No Entries

If `current_workflow` has zero entries in the database, `groups.pop(
current_workflow, [])` returns `[]` without error. The result is still
correct: 0 current-entries + N other-entries (1 per other workflow).

### 9. Prompt Rendering Order

In `PromptService.render()`, the grouped learnings appear in order: **current
workflow entries first** (sorted newest-first), **then other workflow entries**
(sorted alphabetically by workflow, then newest-first within each).

This ordering was not explicitly specified but is a natural consequence of the
`list_grouped_by_workflow()` return format: `current_entries + other_entries`.
The LLM sees its current workflow context first, which is the most useful
signal.

---

## Files Changed

| File | Change |
|------|--------|
| `infrastructure/persistence/sqlite.py` | New `list_grouped_by_workflow()` on `SQLiteLearningRepository` |
| `application/services/learning_service.py` | New `load_grouped_learnings()` method |
| `application/orchestrator.py` | Switch to `load_grouped_learnings()` in `process_run()` |
| Tests | See section 7 above |

---

## Total diff

```
 sqlite.py        | +47 lines  (list_grouped_by_workflow)
 learning_service.py | +9 lines  (load_grouped_learnings)
 orchestrator.py     | -1/+2 lines (switch call)
 tests/              | +~60 lines
```