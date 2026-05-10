# Structured Memory Extraction

## Overview

**Problem:** `learning_entries.result_excerpt` stores raw truncated text (first
1200 chars). When PromptService injects these into the LLM context, the LLM must
re-read and re-interpret the raw text every time. No structured summary
(key technical points, pitfalls, patterns, conclusions) is persisted.

**Goal:** After completing a successful run, extract structured lessons from the
result text using an LLM call, store them alongside the raw excerpt, and inject
both into future prompts.

---

## Design

### 1. Database Change — `learning_lessons` Column

File: `src/mergemate/infrastructure/persistence/sqlite.py`

Add a new nullable TEXT column to `learning_entries`:

```
learning_lessons TEXT   -- structured JSON: {"technical_points": [...], "pitfalls": [...], "patterns": [...], "conclusion": "..."}
```

Migration via existing `_ensure_column()`:

```python
self._ensure_column(
    connection,
    "learning_entries",
    "learning_lessons",
    "TEXT",
)
```

**Why nullable:** Backward compatible — existing rows without lessons remain
valid and return empty structures.

### 2. LearningRepository Interface Change

File: `src/mergemate/infrastructure/persistence/sqlite.py`

**`SQLiteLearningRepository.record()`** adds a `learning_lessons: str | None`
parameter. The INSERT includes the new column:

```python
def record(self, chat_id: int, workflow: str, prompt: str,
           result_excerpt: str, learning_lessons: str | None = None) -> None:
    ...
    INSERT INTO learning_entries (chat_id, workflow, prompt, result_excerpt, learning_lessons, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ...
```

**`SQLiteLearningRepository.list_recent()`** includes `learning_lessons` in the
SELECT and dict output:

```python
SELECT workflow, prompt, result_excerpt, learning_lessons
FROM learning_entries ...
```

### 3. LearningService Changes

File: `src/mergemate/application/services/learning_service.py`

**New dependency:** `llm_gateway` — an async callable for extracting lessons.

**New method `_extract_lessons(result_text: str) -> str`:**

- Calls `self._llm_gateway.generate(agent_name, system_prompt, user_prompt)`
  where the `agent_name` is a dedicated "lessons-extractor" agent (or the
  default agent if none configured).
- `system_prompt`: "You are a lesson extraction assistant. Analyze the
  following result text and extract structured lessons in JSON format."
- `user_prompt`: contains the full `result_text`
- Returns a JSON string with keys:
  ```json
  {
    "technical_points": ["...", "..."],
    "pitfalls": ["...", "..."],
    "patterns": ["...", "..."],
    "conclusion": "..."
  }
  ```
- If the LLM call fails, returns `"{}"` (empty JSON) silently — extraction
  is best-effort, not a pipeline blocker.

**`remember_success()` updated:**

```python
async def remember_success(self, *, chat_id: int, workflow: str,
                            prompt: str, result_text: str) -> None:
    if not self._enabled:
        return
    excerpt = result_text.strip()[:self._max_result_chars]
    lessons = await self._extract_lessons(result_text)
    self._learning_repository.record(chat_id, workflow, prompt, excerpt, lessons)
```

**Signature change:** `remember_success()` becomes **async** — affects all
callers in `execution_plan.py`.

**`load_recent_learnings()`** returns `learning_lessons` in each dict:

```python
{
    "workflow": ...,
    "prompt": ...,
    "result_excerpt": ...,
    "learning_lessons": ...,   # JSON string or None
}
```

### 4. PromptService Changes

File: `src/mergemate/application/services/prompt_service.py`

**`render()`** injects both raw excerpts and structured lessons:

```python
learning_lines = ...
if learned_items:
    lines = ["Previously successful patterns:"]
    for item in learned_items:
        lines.append(f"- Workflow: {item['workflow']}")
        lines.append(f"  Prior prompt: {item['prompt']}")
        lines.append(f"  Prior result excerpt: {item['result_excerpt']}")
        if item.get('learning_lessons'):
            try:
                lessons = json.loads(item['learning_lessons'])
                if lessons.get('technical_points'):
                    lines.append(f"  Key technical points: {', '.join(lessons['technical_points'])}")
                if lessons.get('pitfalls'):
                    lines.append(f"  Known pitfalls: {', '.join(lessons['pitfalls'])}")
                if lessons.get('conclusion'):
                    lines.append(f"  Conclusion: {lessons['conclusion']}")
            except (json.JSONDecodeError, TypeError):
                pass  # malformed JSON, skip
    learning_lines = lines
```

### 5. Callers — `execution_plan.py`

File: `src/mergemate/application/execution_plan.py`

Both `DirectExecutionPlan.execute()` (line 151) and
`MultiStageExecutionPlan.execute()` (line 316) call
`learning_service.remember_success()`. Because `remember_success()` becomes
async, these call sites must be `await`ed:

```python
await runtime.deps.learning_service.remember_success(...)
```

**Impact on `DirectExecutionPlan.execute()`:** It is already async, so only an
`await` keyword change.

**Impact on `MultiStageExecutionPlan.execute()`:** Same — already async.

### 6. LLM Gateway Requirement

The `LearningService` needs an `llm_gateway` with an async `.generate()` method.
The existing `LLM_gateway` in the codebase already conforms to this interface.

**Constructor change:**

```python
class LearningService:
    def __init__(self, learning_repository, enabled: bool,
                 max_context_items: int, max_result_chars: int,
                 llm_gateway=None, extraction_agent_name: str | None = None) -> None:
        self._llm_gateway = llm_gateway
        self._extraction_agent_name = extraction_agent_name or "default"
```

**Bootstrap change (`bootstrap.py`):**

```python
learning_service = LearningService(
    learning_repository=SQLiteLearningRepository(database),
    enabled=config.learning.enabled,
    max_context_items=config.learning.max_context_items,
    max_result_chars=config.learning.max_result_chars,
    llm_gateway=llm_gateway,
    extraction_agent_name=config.learning.extraction_agent,
)
```

**Config model change** (`config/models.py`):

```python
class LearningConfig(BaseModel):
    enabled: bool = True
    max_context_items: int = Field(default=3, ge=1)
    max_result_chars: int = Field(default=1200, ge=1)
    extraction_agent: str | None = None   # agent name for lesson extraction
```

### 7. Backward Compatibility

- Old rows with `learning_lessons IS NULL` → `item.get('learning_lessons')`
  returns `None` → no structured output rendered by PromptService.
- `extraction_agent` is optional; when `None`, the default agent is used.
- If `llm_gateway` is `None`, `_extract_lessons()` returns `"{}"` immediately
  without making a call (graceful degradation).

### 8. What to Test (for tester task)

1. `_extract_lessons()` returns JSON with all 4 keys when LLM succeeds.
2. `_extract_lessons()` returns `"{}"` when LLM raises an exception.
3. `_extract_lessons()` returns `"{}"` when `llm_gateway` is None.
4. `remember_success()` stores `learning_lessons` in the repository.
5. `load_recent_learnings()` returns `learning_lessons` in dict.
6. `PromptService.render()` includes structured content when `learning_lessons`
   is present.
7. `PromptService.render()` falls back gracefully when `learning_lessons` is
   None or malformed.
8. `DirectExecutionPlan.execute()` awaits the async `remember_success()`.
9. `MultiStageExecutionPlan.execute()` awaits the async `remember_success()`.
10. Bootstrap wires `llm_gateway` into `LearningService`.

---

## Files Changed

| File | Change |
|------|--------|
| `config/models.py` | Add `LearningConfig.extraction_agent` |
| `infrastructure/persistence/sqlite.py` | `_ensure_column` migration + `record()` param + `list_recent()` SELECT |
| `application/services/learning_service.py` | `_extract_lessons()`, async `remember_success()`, constructor params |
| `application/services/prompt_service.py` | Structured lesson rendering in `render()` |
| `application/execution_plan.py` | `await` on `remember_success()` calls |
| `bootstrap.py` | Wire `llm_gateway` and `extraction_agent` into `LearningService` |
| Tests | See section 8 above |

## Sequence

```
run completes
  → execution_plan.execute()
    → await learning_service.remember_success(result_text)
      → excerpt = result_text[:1200]
      → await _extract_lessons(result_text)
        → llm_gateway.generate("lessons-extractor", system_prompt, result_text)
        → parse JSON
      → repository.record(chat_id, workflow, prompt, excerpt, lessons_json)
  → next run starts
    → orchestrator.process_run()
      → learning_service.load_recent_learnings(chat_id)
      → prompt_service.render(workflow, messages, learned_items, prompt)
        → for each item with learning_lessons:
            render technical_points, pitfalls, conclusion
```