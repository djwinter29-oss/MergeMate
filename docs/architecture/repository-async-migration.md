# Architecture Design: Repository Layer Asyncification

- Status: Draft
- Date: 2026-05-10
- Related: ADR-003 (Non-blocking Telegram Jobs), ADR-010 (Durable Run Jobs)
- Review reference: Deep Review 2026-05-10 — Finding P1.2

---

## 1. Problem Statement

All repository implementations in `src/mergemate/infrastructure/persistence/sqlite.py` use plain synchronous methods. They are called from both sync and async contexts — service-layer code, use cases, executors, and the orchestrator. Because they are synchronous, every call in an async context blocks the event loop for the duration of the SQLite I/O.

While SQLite itself is single-writer and generally fast under low concurrency, blocking the event loop means:

1. **No context-switching during I/O** — other async tasks cannot yield while a repository method runs its SQLite query.
2. **Heartbeat and cancellation checks are delayed** when scheduled alongside a slow repository call.
3. **Lease-based job heartbeat deadlines** can be missed if repository methods block for more than the heartbeat interval.
4. **Scalability ceiling** — as the worker pool grows, synchronous SQLite calls under an asyncio event loop become a bottleneck.

MergeMate's current SQLite usage is single-writer (SQLite manages its own lock), so the fix is not about parallel writes — it's about **eliminating event-loop blocking**.

---

## 2. Scope

### 2.1 Repository classes in scope

| Class | Lines | Has Protocol? | Methods | Sync/Async Context Called From |
|---|---|---|---|---|
| `SQLiteRunRepository` | 166–403 | Yes (`AgentRunRepository`) | 7 methods | Mixed (both) |
| `SQLiteRunJobRepository` | 435–667 | Yes (`RunJobRepository`) | 7 methods | Mixed (both) |
| `SQLiteConversationRepository` | 406–432 | No (duck-typed) | 2 methods | Mixed (both) |
| `SQLiteLearningRepository` | 670–743 | No (duck-typed) | 3 methods | Mixed (both) |
| `SQLiteRepoKnowledgeRepository` | 746–787 | No (duck-typed) | 2 methods | Mixed (both) |
| `SQLiteToolEventRepository` | 790–824 | No (duck-typed) | 2 methods | Mixed (both) |

**Total: 6 classes, 23 methods.**

### 2.2 Protocols currently in place

Two repository classes already have formal Protocols in `src/mergemate/domain/runs/repository.py`:

- `AgentRunRepository` (7 methods)
- `RunJobRepository` (7 methods)

The other four classes (`SQLiteConversationRepository`, `SQLiteLearningRepository`, `SQLiteRepoKnowledgeRepository`, `SQLiteToolEventRepository`) have no Protocol — consumers depend on them by duck typing only.

---

## 3. Audit: Current Signatures and All Callers

### 3.1 `AgentRunRepository` Protocol + `SQLiteRunRepository`

| Method | Current Signature | Callers |
|---|---|---|
| `create` | `(self, run: AgentRun) -> None` | `SubmitPromptUseCase.execute()` |
| `get` | `(self, run_id: str) -> AgentRun \| None` | `Orchestrator._is_cancelled()`, `Orchestrator.process_run()`, `ExecutionPlan._check_cancelled()`, `ExecutionPlan._check_after_cancelled()`, `MultiStageExecutionPlan.execute()`, `SubmitPromptUseCase.complete_planning()`, `SubmitPromptUseCase.revise_plan_for_chat()`, `SubmitPromptUseCase.approve()`, `GetRunStatusUseCase.execute()`, `CancelRunUseCase.execute()`, `BackgroundRunWorker._process_planning_job()`, `BackgroundRunWorker._mark_shutdown_interrupted()`, `ToolService._update_run_state()`, `ToolService._get_run_progress()` |
| `list_for_chat` | `(self, chat_id: int, limit: int = 5) -> list[AgentRun]` | `GetRunStatusUseCase.execute()`, `CancelRunUseCase.execute()` |
| `try_update_status` | `(self, run_id, status, *, expected_current_status, current_stage, result_text, error_text) -> StatusUpdateDecision` | `Orchestrator.process_run()`, `CancelRunUseCase.execute()`, `ToolService._update_run_state()` (x4 calls) |
| `update_status` | `(self, run_id, status, *, expected_current_status, current_stage, result_text, error_text) -> AgentRun \| None` | `DirectExecutionPlan.execute()` (async), `MultiStageExecutionPlan.execute()` (async), `SubmitPromptUseCase.complete_planning()` (async), `SubmitPromptUseCase.revise_plan_for_chat()` (async), `SubmitPromptUseCase._dispatch_or_fail()`, `BackgroundRunWorker._process_execution_job()` (async), `BackgroundRunWorker._mark_shutdown_interrupted()` |
| `update_plan` | `(self, run_id, plan_text, prompt=None, *, current_stage) -> AgentRun \| None` | `SubmitPromptUseCase.complete_planning()` (async), `SubmitPromptUseCase.revise_plan_for_chat()` (async), `Handler._handle_replanning()` (async) |
| `approve` | `(self, run_id: str) -> ApprovalDecision` | `SubmitPromptUseCase.complete_planning()` (async), `SubmitPromptUseCase.approve()` |
| `save_artifacts` | `(self, run_id, *, current_stage, design_text, test_text, review_text, result_text, review_iterations, **extra) -> AgentRun \| None` | `DirectExecutionPlan.execute()` (async), `Handler._persist_artifacts()` (async) |

### 3.2 `RunJobRepository` Protocol + `SQLiteRunJobRepository`

| Method | Current Signature | Callers |
|---|---|---|
| `ensure_queued_job` | `(self, run_id, *, job_type) -> QueuedRunJobDecision` | `RunDispatcher.dispatch_run()` |
| `get` | `(self, job_id: str) -> RunJob \| None` | Internal (`complete_job`, `fail_job`) |
| `get_active_for_run` | `(self, run_id, *, job_type) -> RunJob \| None` | Internal (`ensure_queued_job`) |
| `claim_job` | `(self, job_id, *, worker_id, lease_seconds) -> RunJob \| None` | `BackgroundRunWorker._consume()` (async) |
| `heartbeat_job` | `(self, job_id, *, worker_id, lease_seconds) -> RunJob \| None` | `BackgroundRunWorker._heartbeat()` (async) |
| `complete_job` | `(self, job_id: str) -> RunJob \| None` | `BackgroundRunWorker._process_planning_job()` (async), `BackgroundRunWorker._process_execution_job()` (async) |
| `fail_job` | `(self, job_id, error_text: str) -> RunJob \| None` | `BackgroundRunWorker._process_planning_job()` (async), `BackgroundRunWorker._process_execution_job()` (async), `BackgroundRunWorker._mark_shutdown_interrupted()` |

### 3.3 Non-Protocol Repository Classes

| Class | Methods | Callers |
|---|---|---|
| `SQLiteConversationRepository` | `append_message`, `list_messages` | `ContextService.append_message()` (sync+async), `ContextService.load_recent_messages()` |
| `SQLiteLearningRepository` | `record`, `list_recent`, `list_grouped_by_workflow` | `LearningService.remember_success()` (async), `LearningService.load_recent_learnings()`, `LearningService.load_grouped_learnings()` |
| `SQLiteRepoKnowledgeRepository` | `record`, `list_recent` | `LearningService.remember_success()` (async), `LearningService.load_repo_knowledge()` |
| `SQLiteToolEventRepository` | `record`, `list_for_run` | `ToolService._record_tool_event()`, `GetRunStatusUseCase._build_snapshot()` |

---

## 4. Proposed Async Signature Standards

### 4.1 Principles

1. **All repository methods become `async def`** — no sync methods remain. This is a single atomic change across all repository classes.
2. **Protocols are updated in lockstep** with their implementations so the type system enforces correctness.
3. **Methods with no I/O** (pure helpers like `_row_to_run`, `_row_to_job`) stay sync — they are `@staticmethod` helpers, not part of the Protocol.
4. **No parameter changes** — the method signatures (names, parameters, return types) are preserved, only `async def` is added.
5. **`SQLiteDatabase.connection()` stays sync** — it is a `@contextmanager` that acquires/releases a `sqlite3.Connection`; the SQLite calls inside the `with` block are what become async, via `asyncio.to_thread` or `loop.run_in_executor`.

### 4.2 Thread Offloading Strategy

SQLite Python API (`sqlite3`) is synchronous and its connection objects are not thread-safe by default. However:

- Each `SQLiteDatabase.connection()` context manager call creates a **new connection** (not shared), so there is no cross-task contention on the connection object itself.
- SQLite file-level locking is handled by the OS; `asyncio.to_thread` offloads the blocking call to a thread pool.

**Recommended approach:** Wrap every `connection.execute(...)`/`connection.executescript(...)` call in `asyncio.to_thread()`. This is minimally invasive and preserves the existing code flow.

```python
# Before
with self._database.connection() as connection:
    connection.execute("INSERT ...", params)

# After
async with asyncio.to_thread(self._database._get_connection) as connection:
    await asyncio.to_thread(connection.execute, "INSERT ...", params)
```

However, the `@contextmanager` pattern cannot be directly asyncified. The cleanest approach is to add an **async connection context manager** to `SQLiteDatabase`:

```python
@asynccontextmanager
async def async_connection(self):
    connection = sqlite3.connect(self.path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
```

Then all repository methods use `async with`:

```python
async def create(self, run: AgentRun) -> None:
    async with self._database.async_connection() as connection:
        await asyncio.to_thread(
            connection.execute,
            "INSERT INTO agent_runs (...) VALUES (...)",
            params,
        )
```

**Alternative (less invasive):** Keep the sync `connection()` context manager and use `asyncio.to_thread()` around the entire `with` block. This is simpler but creates a thread per repository method call:

```python
async def create(self, run: AgentRun) -> None:
    def _sync_create():
        with self._database.connection() as connection:
            connection.execute(...)
    await asyncio.to_thread(_sync_create)
```

**Recommendation:** Add `async_connection()` to `SQLiteDatabase` and use `await asyncio.to_thread(connection.execute, ...)` inside. This keeps SQLite connection management cleanly async and avoids the closure-over-exceptions pattern that wrapping the full `with` block creates.

### 4.3 `SQLiteDatabase.initialize()` — Special Case

`initialize()` currently uses `connection.executescript()` for DDL. Since this runs once at startup (not in the hot path), it can either:

- Stay sync (called from `bootstrap()` sync context before the event loop runs).
- Use a one-shot `async def initialize_async()` for async startup.

**Recommendation:** Keep `initialize()` sync. It's called synchronously from `bootstrap()` before any async context exists.

---

## 5. Migration Strategy

### 5.1 Phased Approach

The migration happens in one unit of work (single PR) to avoid intermediate inconsistency where some repos are async and others are not.

#### Phase A: `SQLiteDatabase` — Add `async_connection()` (1 point)

Add an `@asynccontextmanager` version of `connection()` to `SQLiteDatabase`. No callers change yet.

#### Phase B: All repository classes — Make methods async (4 points)

For each of the 6 repository classes, convert every method. This is a mechanical transformation: wrap each `with self._database.connection():` → `async with self._database.async_connection():` and each `connection.execute(...)` → `await asyncio.to_thread(connection.execute, ...)`.

#### Phase C: Protocols — Add `async` (1 point)

Update both `AgentRunRepository` and `RunJobRepository` Protocols to declare `async def` for all methods.

**Note on non-Protocol repos:** `SQLiteConversationRepository`, `SQLiteLearningRepository`, `SQLiteRepoKnowledgeRepository`, and `SQLiteToolEventRepository` have no Protocol today. Adding Protocols for them is out of scope for this migration (see Future Work). The async transformation of these classes is still required — their callers (service layer) will `await` them.

#### Phase D: Caller side — Add `await` in all callers (4 points)

Every caller that invokes a repository method must `await` it. This is also mechanical:

| Caller file | Await changes needed |
|---|---|
| `src/mergemate/application/orchestrator.py` | `.get()` (x2), `.try_update_status()` |
| `src/mergemate/application/execution_plan.py` | `.get()` (x3), `.save_artifacts()`, `.update_status()` (x2) |
| `src/mergemate/domain/workflows/handlers.py` | `.update_plan()`, `.save_artifacts()` |
| `src/mergemate/application/use_cases/submit_prompt.py` | `.create()`, `.get()` (x3), `.update_status()` (x2), `.update_plan()` (x2), `.approve()` (x2) |
| `src/mergemate/application/use_cases/cancel_run.py` | `.get()` (x2), `.list_for_chat()`, `.try_update_status()` |
| `src/mergemate/application/use_cases/get_run_status.py` | `.get()`, `.list_for_chat()` |
| `src/mergemate/application/jobs/worker.py` | `.claim_job()`, `.complete_job()` (x2), `.fail_job()` (x3), `.heartbeat_job()`, `.get()`, `.update_status()` (x2) |
| `src/mergemate/application/jobs/dispatcher.py` | `.ensure_queued_job()` |
| `src/mergemate/application/services/tool_service.py` | `.get()` (x2), `.try_update_status()` (x4) |
| `src/mergemate/application/services/context_service.py` | `.append_message()`, `.list_messages()` |
| `src/mergemate/application/services/learning_service.py` | `.record()`, `.list_recent()`, `.list_grouped_by_workflow()`, `.record()` (repo_knowledge), `.list_recent()` (repo_knowledge) |
| `src/mergemate/bootstrap.py` | No repo calls directly (wiring only) |

Caller changes must be **strictly additive** — add `await` before each repo call, and ensure the containing function is `async def`. In most cases the containing function is already `async def` (all orchestrator flows, worker, handlers, use cases). The exceptions where sync `def` calls repos are:

| Function | Sync def? | Action |
|---|---|---|
| `Orchestrator._is_cancelled()` | `def` | Convert to `async def`; all callers already `async` |
| `CancelRunUseCase.execute()` | `def` | Convert to `async def`; update Telegram interface caller |
| `SubmitPromptUseCase.approve()` | `def` | Convert to `async def`; update Telegram interface caller |
| `SubmitPromptUseCase._dispatch_or_fail()` | `def` | Convert to `async def`; callers already `async` |
| `GetRunStatusUseCase.execute()` | `def` | Convert to `async def`; update Telegram interface caller |
| `RunDispatcher.dispatch_run()` | `def` | Convert to `async def`; callers already `async` |
| `ContextService.append_message()` | `def` | Convert to `async def`; update all callers (many) |
| `ToolService._update_run_state()` | `def` | Convert to `async def`; callers already `async` |
| `Handler._persist_artifacts()` | `def` | Convert to `async def`; callers already `async` |

A small number of sync callers outside the async pipeline use repos — these must become async or use `asyncio.run()` wrappers at the boundary.

### 5.2 Call Graph: Sync-to-async Conversion Depth

```
Telegram Interface (sync handlers)
  ├─ SubmitPromptUseCase.execute()         → already async ✓
  ├─ SubmitPromptUseCase.approve()         → needs await + async def
  ├─ SubmitPromptUseCase.revise_for_chat() → already async ✓
  ├─ CancelRunUseCase.execute()            → needs await + async def
  └─ GetRunStatusUseCase.execute()         → needs await + async def

ToolService (called from async tool execution)
  ├─ _update_run_state()                   → needs await + async def
  └─ _record_tool_event()                  → needs await

BackgroundRunWorker (fully async)
  ├─ _consume()                            → already async ✓
  ├─ _process_planning_job()               → already async ✓
  ├─ _process_execution_job()              → already async ✓
  ├─ _heartbeat()                          → already async ✓
  └─ _mark_shutdown_interrupted()          → needs await

Orchestrator (fully async)
  ├─ process_run()                         → already async ✓
  └─ _is_cancelled()                       → needs await + async def

ExecutionPlans (fully async)
  ├─ DirectExecutionPlan.execute()         → already async ✓
  └─ MultiStageExecutionPlan.execute()     → already async ✓

RunDispatcher.dispatch_run()               → needs await + async def
Handler._persist_artifacts()                → needs await + async def
Handler._handle_replanning()                → already async ✓
ContextService methods                      → needs await + async def
LearningService methods                     → already async (except sync helpers)

GetRunStatusUseCase._build_snapshot()       → needs await
```

### 5.3 Changes to sync callers at the interface boundary

The Telegram interface (`src/mergemate/interfaces/telegram/`) calls use cases that are currently synchronous. These handlers run on the `python-telegram-bot` framework's async event loop — they are already `async def`. The issue is only that the use case methods they call need to be awaited. Since `python-telegram-bot` callbacks are async, no framework changes are needed, merely adding `await` in the right places.

---

## 6. Backward Compatibility

### 6.1 Protocol compatibility

Changing `AgentRunRepository` and `RunJobRepository` Protcols from `def` to `async def` is a **breaking change** for any external implementor (e.g., in-memory test repos, hypothetical Redis adapters). Mitigations:

- All first-party implementations change in the same PR.
- Any in-tree test mocks/stubs are updated in the same PR.
- Protocol methods are not overloaded — no `sync` vs `async` branch needed in the Protocol.

### 6.2 Caller compatibility

Adding `await` to every repository call is additive in async functions. The only risk is a sync function where `await` is not legal. These are listed in the table above and must be converted to `async def`.

### 6.3 Migration rule

**All-or-nothing in one PR.** Do not partially async a repository — half-async repos that must be called with and without `await` create cognitive load and runtime errors.

---

## 7. Implementation Plan

### Task breakdown for coder

| # | Task | Changed Files | Est. Points |
|---|---|---|---|
| 1 | Add `async_connection()` to `SQLiteDatabase` | `sqlite.py` | 1 |
| 2 | Convert `SQLiteRunRepository` (7 methods) to async | `sqlite.py` | 2 |
| 3 | Convert `SQLiteRunJobRepository` (7 methods) to async | `sqlite.py` | 2 |
| 4 | Convert `SQLiteConversationRepository` (2 methods) to async | `sqlite.py` | 1 |
| 5 | Convert `SQLiteLearningRepository` (3 methods) to async | `sqlite.py` | 1 |
| 6 | Convert `SQLiteRepoKnowledgeRepository` (2 methods) to async | `sqlite.py` | 1 |
| 7 | Convert `SQLiteToolEventRepository` (2 methods) to async | `sqlite.py` | 1 |
| 8 | Update `AgentRunRepository` Protocol to `async def` | `repository.py` | 1 |
| 9 | Update `RunJobRepository` Protocol to `async def` | `repository.py` | 1 |
| 10 | Add `await` to all callers in `orchestrator.py` | `orchestrator.py` | 1 |
| 11 | Add `await` to all callers in `execution_plan.py` | `execution_plan.py` | 1 |
| 12 | Add `await` to all callers in `handlers.py` | `handlers.py` | 1 |
| 13 | Add `await` to all callers in `submit_prompt.py` | `submit_prompt.py` | 2 |
| 14 | Add `await` to all callers in `cancel_run.py` | `cancel_run.py` | 1 |
| 15 | Add `await` to all callers in `get_run_status.py` | `get_run_status.py` | 1 |
| 16 | Add `await` to all callers in `worker.py` | `worker.py` | 2 |
| 17 | Add `await` to all callers in `dispatcher.py` | `dispatcher.py` | 1 |
| 18 | Add `await` to all callers in `tool_service.py` | `tool_service.py` | 2 |
| 19 | Add `await` to all callers in `context_service.py` | `context_service.py` | 1 |
| 20 | Add `await` to all callers in `learning_service.py` | `learning_service.py` | 1 |
| 21 | Update all interface-layer callers (Telegram handlers) | `interfaces/telegram/*.py` | 1 |
| 22 | Update in-memory test stubs/mocks | `tests/` | 1 |
| 23 | Run full test suite and fix regressions | — | 2 |

**Total: ~27 story points.**

### Task grouping for PR

The changes should be submitted as **a single PR** to avoid intermediate inconsistency. Within that PR, changes to `sqlite.py` happen first (so the compiler can verify the rest), then protocols, then callers.

## 8. Risk and Open Questions

### 8.1 Thread pool overhead

`asyncio.to_thread()` dispatches work to the default `ThreadPoolExecutor`. Under load, the pool could grow large. For SQLite-heavy workloads:

- **Mitigation:** The default thread pool has no hard cap (grows on demand). For MergeMate's concurrency model (single-worker, low concurrency), this is acceptable. If profiling shows thread-bloat, switch to a bounded executor: `asyncio.to_thread(executor=my_bounded_executor, fn, ...)`.

### 8.2 SQLite thread-safety

`sqlite3` module connections default to `check_same_thread=True` (the connection object may not be used from a different thread). `SQLiteDatabase.connection()` passes `check_same_thread=False` in its `sqlite3.connect()` call, so threads are already allowed. No change needed.

### 8.3 Transaction atomicity

SQLite's default mode is autocommit — each `connection.execute()` is its own transaction. The `async_connection()` context manager calls `connection.commit()` on success and closes on exit, preserving the existing semantics. For operations that need multi-statement transactions (e.g., `try_update_status` → `self.get()` then `UPDATE`), both calls happen inside the same `async with async_connection()` block and thus share the same connection. However, `get()` currently opens a *new* connection via `async_connection()`, then closes it, then opens another for the UPDATE. **This should be consolidated** into a single connection per logical operation.

### 8.4 Non-Protocol repos — future Protocol addition

The four classes without Protocols (`ConversationRepository`, `LearningRepository`, `ToolEventRepository`, `RepoKnowledgeRepository`) are candidates for formal Protocols in a follow-up PR. This async migration does not add them — it only makes the existing duck-typed interfaces async.

---

## 9. Future Work (out of scope)

1. Add formal Protocols for `SQLiteConversationRepository`, `SQLiteLearningRepository`, `SQLiteToolEventRepository`, and `SQLiteRepoKnowledgeRepository`.
2. Evaluate `aiosqlite` as an alternative to `asyncio.to_thread()` for native async SQLite support.
3. Add connection pooling if multiple async tasks contend for SQLite.
4. Extract repository interfaces into `domain/runs/` for all repository types (beyond the two that exist).

---

## 10. Verification

- All existing unit tests pass (target: `make test` / `pytest tests/`).
- All repository methods produce the same results as sync versions (test coverage via existing test files).
- No event loop blocking is measurable in hot path (optional: add a simple `asyncio.get_running_loop()` blocking detector assertion in debug mode).
- Type-check passes: `mypy src/mergemate` (or `pyright`).