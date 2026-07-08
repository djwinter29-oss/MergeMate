# Architecture Review — 2026-05-10

**Reviewer:** Architect Soul
**Scope:** Full stack review of MergeMate 0.1.0
**Review areas:** Domain layer boundaries, interface contracts, config/models.py quality,
infrastructure abstraction, workflow plugin system, async/sync boundary consistency

---

## Summary of Findings

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 1 | Systemic async/sync boundary violation — blocking I/O on event loop |
| Major | 4 | Cross-layer reference, orphaned legacy code, missing abstraction layer, tightly-coupled config |
| Moderate | 2 | Repository protocols incomplete, missing interface for infrastructure pluggability |
| Minor | 3 | Incomplete `__init__.py` exports, unused namespace packages, doc-only placeholder files |

---

## Critical Issues

### C1. Systemic async/sync boundary violation — blocking I/O on event loop

**Severity: Critical**
**Affects:** All async code paths (orchestrator, execution plans, handlers, worker, use cases)
**Files:** `application/orchestrator.py`, `application/execution_plan.py`, `application/use_cases/submit_prompt.py`,
`application/jobs/worker.py`, `domain/workflows/handlers.py`, `interfaces/telegram/handlers.py`,
`interfaces/telegram/progress_notifier.py`

#### Problem

The codebase uses a two-tier architecture: an **async layer** (all LLM calls via `httpx.AsyncClient`,
all Telegram handlers via `python-telegram-bot` async callbacks, all background worker loops via
`asyncio`) and a **sync layer** (SQLite via `sqlite3`, filesystem via `open()`, subprocess via
`subprocess.run()`).

The problem: **the async layer calls sync blocking I/O directly** in 20+ locations with no
`asyncio.to_thread()` or `run_in_executor()` wrapper. Every SQLite read/write, every filesystem
read/write, and every subprocess call blocks the asyncio event loop for the duration of the I/O.

#### Affected Call Chain

```
worker._process_execution_job()          [async]
  └─ orchestrator.process_run()          [async]
       ├─ run_repository.get()           SQLite  ✗ blocking
       ├─ run_repository.try_update_status() SQLite ✗ blocking
       ├─ context_service.load_recent_messages() SQLite ✗ blocking
       ├─ learning_service.load_recent_learnings() SQLite ✗ blocking
       ├─ prompt_service.render()        filesystem ✗ blocking
       └─ execution_plan.execute()       [async]
            ├─ run_repository.get()      SQLite ✗ blocking (called in hot loop)
            ├─ handler()                 [async]
            │    ├─ _persist_artifacts() SQLite ✗ blocking (in every stage handler)
            │    └─ _save_document()     filesystem ✗ blocking
            ├─ run_repository.update_status() SQLite ✗ blocking
            └─ learning_service.remember_success() SQLite ✗ blocking
```

The **only** properly wrapped async/sync boundary in the entire codebase is
`tool_service.build_runtime_tool_context_async()`, which uses `asyncio.to_thread()`.

#### Recommendation

Two approaches, pick one:

**Approach A (pragmatic — async wrapper facade):**
Add an `AsyncRunRepository` / `AsyncContextService` / etc. facade layer that wraps every
sync method with `asyncio.to_thread()`. This is low-risk, can be done incrementally, and
preserves the existing sync repository implementations.

```python
class AsyncRunRepository:
    def __init__(self, sync_repo: AgentRunRepository):
        self._sync = sync_repo

    async def get(self, run_id: str) -> AgentRun | None:
        return await asyncio.to_thread(self._sync.get, run_id)
```

**Approach B (architectural — async-native SQLite):**
Replace the raw `sqlite3` module with `aiosqlite` and make the repository layer fully async.
This is more correct but a larger refactor — every repository method becomes `async def`,
rippling up through every caller.

**Recommendation:** Approach A is preferred for MVP velocity. Create a single
`AsyncPersistence` wrapper class, inject it into `OrchestratorDependencies`, and
migrate callers one at a time.

---

## Major Issues

### M1. Cross-layer reference: domain/handlers.py imports application layer

**Severity: Major**
**Files:** `domain/workflows/handlers.py` → `application/execution_plan`

#### Problem

`domain/workflows/handlers.py` imports `ExecutionRuntime` from `application/execution_plan`:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from mergemate.application.execution_plan import ExecutionRuntime
```

While this is `TYPE_CHECKING`-only (no runtime dependency), it's a **design smell** — the
domain layer should have zero knowledge of the application layer by definition. The handler
signatures reference `ExecutionRuntime` which is an application-layer concept.

The type alias `StageHandler = Any` (line 6) is also a weakness — it's a hole that bypasses
type checking entirely.

#### Recommendation

Define the handler's required context as a domain-layer protocol instead of referencing
the application-layer class:

```python
# In domain/workflows/handlers.py
class HandlerContext(Protocol):
    """Minimal dependency shape that handlers need — defined in domain."""
    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str: ...
    async def update_run(self, run_id: str, **fields) -> None: ...
```

Then have `ExecutionRuntime` satisfy this protocol structurally. This keeps the domain clean.

### M2. Orphaned legacy policy functions in domain/shared/enums.py

**Severity: Major**
**Files:** `domain/shared/enums.py`, `domain/policies/__init__.py`

#### Problem

The policy functions (`resolve_workflow_name`, `uses_multi_stage_delivery`,
`is_user_facing_workflow`, `workflow_prompt_file`) have been extracted from `enums.py`
into `domain/policies/__init__.py`, but **the original copies remain** in `enums.py`.
The `domain/shared/__init__.py` even includes a migration note advising importers to
use `domain/policies/` instead.

This creates a maintenance hazard: a future developer might fix a policy bug in one
location but not the other, or new code might import from the wrong location.

#### Recommendation

Remove the legacy copies from `domain/shared/enums.py`. The `domain/shared/__init__.py`
should re-export from `domain/policies/` for backward compatibility (with a deprecation
warning), but the original definitions must not live in two places.

### M3. Missing abstraction layer between application code and SQLite persistence

**Severity: Major**
**Files:** `application/orchestrator.py`, `application/execution_plan.py`, `application/use_cases/*`,
`infrastructure/persistence/sqlite.py`

#### Problem

Application-layer classes (`OrchestratorDependencies`) are injected with **concrete sync
repositories** directly. The dependency injection is done via constructor injection, which
is good, but there is no unit-of-work or transaction management across the repository calls
within a single async operation.

For example, `submit_prompt.execute()` calls `run_repository.create()` and
`context_service.append_message()` and `_dispatch_or_fail()` in sequence — if any fails,
the earlier operations are already committed. There is no rollback, no transaction scope.

Additionally, `SQLiteDatabase`'s `connection()` context manager auto-commits on exit, which
means partial operations within a single orchestrator call are already visible to other
workers/readers.

#### Recommendation

Introduce a **Unit of Work** pattern at the service layer:

```python
class AsyncUnitOfWork:
    def __init__(self, db: SQLiteDatabase):
        self._db = db
        self._conn: sqlite3.Connection | None = None

    async def __aenter__(self):
        def _connect():
            conn = self._db._connect()
            conn.execute("BEGIN")
            return conn
        self._conn = await asyncio.to_thread(_connect)
        return self

    async def __aexit__(self, exc_type, ...):
        if exc_type:
            await asyncio.to_thread(self._conn.rollback)
        else:
            await asyncio.to_thread(self._conn.commit)
        await asyncio.to_thread(self._conn.close)
```

The use case classes then receive a factory for creating scoped UoWs rather than
raw repository references.

### M4. config/models.py is overburdened — 442 lines combining validation, resolution, and path logic

**Severity: Major**
**File:** `config/models.py` (442 lines)

#### Problem

`config/models.py` contains:

1. **Pydantic model definitions** (12 models) — properly scoped
2. **Business logic validators** (`_populate_roles_from_agents`, cross-field checks, provider reference validation) — should not be in model layer
3. **Environment variable resolution** (`resolve_provider_api_key`, `resolve_telegram_token`) — infrastructure concern
4. **Path resolution** (`resolve_database_path`, `resolve_workspace_root`, `resolve_docs_root`, `resolve_working_directory`) — infrastructure concern
5. **Agent dispatch logic** (`resolve_agent_name_for_workflow`) — application/business logic

The model has a `model_validator(mode="after")` that runs significant business logic
(deduplication, cross-referencing, backward-compatibility shimming).

#### Recommendation

Split `config/models.py` into three files:

| File | Contents |
|------|----------|
| `config/models.py` | Pydantic models only (12 model classes with `Field()` declarations and minimal inline validators like URL checks) |
| `config/resolver.py` | All `resolve_*()` methods — path resolution, env var resolution |
| `config/validators.py` | Cross-model validation functions (`validate_provider_refs`, `validate_workflow_agents`, `populate_roles_from_agents`) |

`AppConfig` should be a **thin model** — validators become standalone functions called
explicitly after construction.

---

## Moderate Issues

### Mod1. Repository Protocols lack async method signatures

**Severity: Moderate**
**Files:** `domain/runs/repository.py`

#### Problem

The `AgentRunRepository` and `RunJobRepository` Protocols define only **sync method signatures**:

```python
class AgentRunRepository(Protocol):
    def create(self, run: AgentRun) -> None: ...
    def get(self, run_id: str) -> AgentRun | None: ...
    def try_update_status(self, ...) -> ApprovalDecision: ...
```

Every concrete implementation (`SQLiteRunRepository`) is sync. But the call site is entirely
async. This means:

1. The Protocol doesn't match the calling pattern — there's no abstraction over async access
2. If someone writes an async repository (e.g., `aiosqlite`-based), it won't satisfy the Protocol
3. Mocking in tests requires `AsyncMock` wrappers because the Protocol doesn't declare `async def`

#### Recommendation

Update both repository Protocols to `async def` signatures:

```python
class AgentRunRepository(Protocol):
    async def create(self, run: AgentRun) -> None: ...
    async def get(self, run_id: str) -> AgentRun | None: ...
    async def try_update_status(self, ...) -> ApprovalDecision: ...
```

Then wrap the `SQLiteRunRepository` methods (see C1 — use `asyncio.to_thread` in an adapter,
or switch to `aiosqlite`).

### Mod2. Queue backend protocol status

**Severity: Moderate**
**Files:** `infrastructure/queue/__init__.py`, `infrastructure/queue/local_queue.py`

#### Status

Resolved in current main.

`JobQueueBackend` is now defined as a `Protocol` in
`src/mergemate/infrastructure/queue/__init__.py`, and `LocalQueue` explicitly
implements that contract. The dispatcher and worker now depend on the queue
boundary via the protocol instead of ad-hoc duck typing.

#### Notes

- The abstraction now makes it straightforward to swap in a Redis, RabbitMQ, or
  SQS-backed implementation later.
- The implementation detail remains in-memory today, but the contract boundary is
  now explicit and type-checked.

---

## Minor Issues

### m1. Several `__init__.py` files are bare docstrings with no re-exports

**Severity: Minor**
**Files:** `domain/runs/__init__.py`, `domain/tools/__init__.py`,
`application/__init__.py`, `application/services/__init__.py`,
`application/use_cases/__init__.py`, `application/jobs/__init__.py`,
`infrastructure/__init__.py`, `infrastructure/llm/__init__.py`,
`infrastructure/persistence/__init__.py`, `infrastructure/persistence/repositories/__init__.py`,
`infrastructure/queue/__init__.py`, `infrastructure/telemetry/__init__.py`,
`infrastructure/tools/__init__.py`, `infrastructure/tools/builtin/__init__.py`,
`interfaces/telegram/__init__.py`

#### Problem

These files contain only a docstring — no `__all__`, no re-exports. While Python allows
wildcard re-exports (`from .module import *`), the absence of explicit exports means:

- IDE autocomplete doesn't know what symbols a package exposes
- `from mergemate.domain.runs import AgentRun` works, but `from mergemate.domain.runs import *` does nothing
- New contributors have to read individual files to discover the public API

#### Recommendation

Add `__all__` with explicit re-exports to each `__init__.py`. Focus on the domain package
`__init__.py` files first — they define the public API boundary. Infrastructure packages
are lower priority since they're implementation details.

### m2. `src/mergemate/workflows/__init__.py` is a dead namespace package

**Severity: Minor**
**File:** `src/mergemate/workflows/__init__.py`

#### Problem

This file exists at `src/mergemate/workflows/` and contains only a docstring:
`"""Workflow configuration."""`. It has no code, no imports, no re-exports.

The real workflow logic lives in `src/mergemate/domain/workflows/`. This top-level
`workflows/` package appears to be an artifact of an earlier directory structure.

#### Recommendation

Either:
- Remove the empty `workflows/` package entirely (if no code is planned to be added),
- Or populate it with a re-export from `domain/workflows/` for backward compatibility.

### m3. `domain/shared/exceptions.py` defines exceptions that are never re-exported

**Severity: Minor**
**Files:** `domain/shared/exceptions.py`, `domain/shared/__init__.py`

#### Problem

`domain/shared/exceptions.py` defines 18 exception classes in a clean hierarchy, but
`domain/shared/__init__.py` does **not** re-export them. Importers must know the exact
module path: `from mergemate.domain.shared.exceptions import ConfigurationError`.

#### Recommendation

Add re-exports to `domain/shared/__init__.py`:

```python
from mergemate.domain.shared.exceptions import (
    MergeMateError, ConfigurationError, RunError,
    SoulPermissionError, ProviderError, PersistenceError,
    JobQueueError, ...
)
```

---

## Detailed Area Reviews

### 1. Domain Layer Boundaries

**Verdict: Clean, with one exception**

| Metric | Value |
|--------|-------|
| Files inspected | 18 files across 6 subpackages |
| External deps | Zero (stdlib only) |
| Cross-boundary refs | 1 (handlers.py → application, TYPE_CHECKING only) |
|| Protocols defined | 5 (AgentRunRepository, RunJobRepository, ValidationHook, HandlerContext, StageHandler) |
| Exception hierarchy depth | 3 levels (MergeMateError → 7 subtypes → 11 leaf exceptions) |

**Strengths:**
- Domain layer has zero runtime dependencies on external packages (stdlib only)
- All domain entities are plain dataclasses with no ORM coupling
- Exception hierarchy is well-structured with meaningful specialization
- Repository protocols use structural subtyping (Protocol) rather than inheritance, enabling test doubles without complex mocking
- Soul definitions (`domain/agents/soul.py`) are cleanly separated from business logic

**Weakness:**
- None currently called out in this slice; `handlers.py` now uses `HandlerContext`
  and `StageHandler` Protocols instead of an `Any` alias.

### 2. Interface Contracts (Protocols / ABCs)

**Verdict: Incomplete coverage**

| Protocol | Location | Implemented by | Async-ready |
|----------|----------|----------------|-------------|
| `AgentRunRepository` | `domain/runs/repository.py` | `SQLiteRunRepository` | No (sync sigs) |
| `RunJobRepository` | `domain/runs/repository.py` | `SQLiteRunRepository` | No (sync sigs) |
| `LLMClient` | `infrastructure/llm/base.py` | `OpenAIAdapter` | Yes (async prot) |
| `ValidationHook` | `domain/workflows/validation.py` | `@runtime_checkable` | Yes (async prot) |
| `JobQueueBackend` | `infrastructure/queue/__init__.py` | `LocalQueue` | Yes (async protocol) |
| `ToolInvoker` | `domain/tools/protocols.py` | 4 tool classes | Yes (sync protocol) |
| `LifecycleNotifier` | `interfaces/telegram/lifecycle_notifier.py` | `TelegramRunLifecycleNotifier` | Yes (async protocol) |

**Recommendation:** Add async repository protocols for `AgentRunRepository` /
`RunJobRepository` (see Mod1 and C1). The queue and lifecycle notifier boundaries
are already covered.

### 3. config/models.py

**Verdict: Overburdened — violates Single Responsibility**

Lines breakdown:
- Pydantic model field declarations: ~200 lines
- Pydantic validators (business logic): ~50 lines
- `resolve_*()` methods (env/path logic): ~120 lines
- Helper functions and imports: ~70 lines

The file mixes model definition, application-level validation, infrastructure-level
resolution, and path management. See M4 for the proposed split.

Specific issues:
- `_populate_roles_from_agents()` is backward-compat logic that should live in `bootstrap.py`
- `resolve_database_path()` and `resolve_workspace_root()` mutate the model state (via validator) but
  are path-resolution concerns, not model concerns
- `AppConfig.resolve_agent_name_for_workflow()` is application-level dispatch logic

### 4. Infrastructure Layer Abstraction

**Verdict: Mixed — LLM is well-abstracted, persistence is not**

> Update 2026-07-08: the tool-interface gap called out in the original review has
> since been closed. `ToolInvoker` now exists in `src/mergemate/domain/tools/`
> and is re-exported from `src/mergemate/domain/tools/__init__.py`.

**LLM abstraction (GOOD):**
- `LLMClient` Protocol in `base.py` with a single `async def generate()` method
- `OpenAIAdapter` is a clean implementation — no framework dependency
- `ParallelLLMGateway` composes multiple providers cleanly
- Provider switching is config-driven, not code-driven

**Persistence abstraction (WEAK):**
- `SQLiteRunRepository` has no async wrapper — it's sync-only
- No `AsyncRunRepository` exists
- `SQLiteDatabase` is a low-level connection manager, not a Unit of Work
- No connection pooling or concurrent-access strategy (SQLite is single-writer)

**Queue abstraction (MISSING):**
- `LocalQueue` is an in-memory asyncio.Queue — not durable, not swappable
- No Protocol defines the queue contract
- `RunDispatcher` takes `queue_backend` by duck type only

**Tool abstraction (ADEQUATE):**
- Each tool has a `ToolMetadata` descriptor and an `invoke(payload)` method
- `ToolRegistry` provides name-based lookup
- Strong point: tools are self-describing via `metadata`
- Weak point: the review originally noted missing protocol coverage, but that gap has
  since been resolved by `ToolInvoker`

### 5. Workflow Plugin System Design

**Verdict: Good foundation with clear extensibility path**

The workflow plugin system has been recently formalized (per prior architect work on task t_00965217):

**Strengths:**
- `WorkflowRegistry` is string-keyed (not enum-keyed), allowing third-party plugins to register new workflows without modifying the core
- `ValidationHook` protocol provides clean post-stage extension points
- `register_workflow()` raises on duplicate — prevents silent overrides
- `register_handler()` decorator makes handler registration declarative
- Entry-point mechanism (`mergemate.workflows` group) supports plugin discovery
- Built-in workflows auto-register via `_register_builtin_workflows()` at import time

**Weaknesses:**
- `StageHandler = Any` type alias (see M1)
- No lifecycle hooks (pre-register, pre-unregister callbacks)
- Handler context (`ExecutionRuntime`) is an application concept in the domain layer

**Recommendation for the next phase:**
- Add `WorkflowPlugin` Protocol that plugins implement:
  ```python
  class WorkflowPlugin(Protocol):
      name: str
      async def on_register(self, registry: WorkflowRegistry) -> None: ...
      async def on_unregister(self, registry: WorkflowRegistry) -> None: ...
  ```
- Add plugin validation hooks at registration time (schema validation of definitions)
- Consider a `depends_on` field in `WorkflowStage` for stage ordering constraints

### 6. Async/Sync Boundary Consistency

**Verdict: Systemic issue — see C1**

Detailed breakdown:

| Layer | Async | Sync | Boundary handling |
|-------|-------|------|-------------------|
| Domain workflows | Handlers (7 async) | Persist helpers | ✗ Calls sync directly |
| Application services | Planning, Workflow | Context, Learning, Doc, Prompt, Tool | ✗ 1 correct, 4 wrong |
| Application use cases | SubmitPrompt (3 async) | Approve (sync) | ✗ Mixed async+sync |
| Application jobs | Worker (all async) | — | ✗ All callers of sync repos |
| Infrastructure LLM | Gateway, Adapter (async) | — | ✓ Proper httpx async |
| Infrastructure Persistence | — | All repos (sync) | N/A (leaf) |
| Infrastructure Queue | dequeue (async) | enqueue, acknowledge | N/A (leaf) |
| Interfaces/Telegram | All handlers (async) | — | ✗ Call sync use cases |

**Root cause:** The `AgentRunRepository` and `RunJobRepository` Protocols were designed
with sync signatures. Every higher layer built on top of these inherited sync calls.
The LLM abstraction was designed async from the start and is correct; the persistence
abstraction was not.

---

## Recommendations Prioritized

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| P0 | **C1** Fix async/sync boundary (Approach A — async wrapper) | Medium | Blocks production scalability |
| P0 | **C1** Make repository Protocols async | Small | Enables proper async dependency injection |
| P1 | **M1** Decouple handlers from application types | Small | Maintains domain purity |
| P1 | **M2** Remove orphaned legacy policy functions | Trivial | Prevents maintenance bugs |
| P1 | **M4** Split config/models.py | Medium | Reduces config module complexity |
| P2 | **M3** Introduce Unit of Work for transaction safety | Medium | Prevents data inconsistency |
| P2 | **Mod1** Add JobQueueBackend Protocol | Small | Enables queue swap |
| P2 | **Mod2** Make repo protocols fully async | Small | Aligns types with usage |
| P3 | **m1** Add __all__ to init files | Large (tedious) | Developer UX improvement |
| P3 | **m2** Remove dead workflows/ namespace | Trivial | Dead code cleanup |
| P3 | **m3** Re-export exceptions from shared/__init__ | Trivial | Import consistency |

---

## Files Examined During Review

All files in `src/mergemate/` (60+ Python files across 5 layers: config, domain,
application, infrastructure, interfaces/telegram), plus `bootstrap.py`, `cli.py`,
`docs/` structure, and `tests/` structure.

---

*Review conducted by Architect Soul on 2026-05-10*