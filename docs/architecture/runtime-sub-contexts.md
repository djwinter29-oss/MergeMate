# Architecture Design: MergeMateRuntime Field Grouping into Sub-Contexts

## Problem

`MergeMateRuntime` (in `src/mergemate/bootstrap.py`, lines 114–133) is a flat
`@dataclass(slots=True)` with 18 fields. As the runtime grows this will become
unwieldy: hard to reason about, easy to miss a field in the construction call,
and awkward to mock for tests that only need a subset.

```python
@dataclass(slots=True)
class MergeMateRuntime:
    settings: AppConfig                         # config
    config_path: Path                           # config
    database: SQLiteDatabase                    # persistence (infra)
    run_repository: SQLiteRunRepository         # persistence
    run_job_repository: SQLiteRunJobRepository  # persistence
    conversation_repository: ...                # persistence
    learning_repository: ...                    # persistence
    tool_event_repository: ...                  # persistence
    queue_backend: JobQueueBackend              # infrastructure
    learning_service: LearningService           # service
    tool_service: ToolService                   # service
    planning_service: PlanningService           # service
    workflow_service: WorkflowService           # service
    submit_prompt: SubmitPromptUseCase          # use case
    get_run_status: GetRunStatusUseCase         # use case
    cancel_run: CancelRunUseCase                # use case
    worker: BackgroundRunWorker                 # infra / lifecycle
    lifecycle_notifier: TelegramRunLifecycleNotifier  # infra / lifecycle
```

## Proposed Grouping

Split the 18 fields into three objects:

### 1. `PersistenceContext`

Owns all *Repository fields + the raw Database reference. Represents
the durable state layer.

```python
@dataclass(slots=True)
class PersistenceContext:
    database: SQLiteDatabase
    run_repository: SQLiteRunRepository
    run_job_repository: SQLiteRunJobRepository
    conversation_repository: SQLiteConversationRepository
    learning_repository: SQLiteLearningRepository
    tool_event_repository: SQLiteToolEventRepository
```

### 2. `ServiceContext`

Owns the service-layer / use-case objects that orchestrate business logic.

```python
@dataclass(slots=True)
class ServiceContext:
    queue_backend: JobQueueBackend
    learning_service: LearningService
    tool_service: ToolService
    planning_service: PlanningService
    workflow_service: WorkflowService
    submit_prompt: SubmitPromptUseCase
    get_run_status: GetRunStatusUseCase
    cancel_run: CancelRunUseCase
```

### 3. `MergeMateRuntime` (reduced)

The remaining fields that are truly top-level runtime state — configuration,
worker lifecycle, and notification plumbing.

```python
@dataclass(slots=True)
class MergeMateRuntime:
    settings: AppConfig
    config_path: Path
    persistence: PersistenceContext
    services: ServiceContext
    worker: BackgroundRunWorker
    lifecycle_notifier: TelegramRunLifecycleNotifier
```

Total fields on the top-level runtime drops from 18 to **6**. All but two
(`worker`, `lifecycle_notifier`) are themselves grouped context objects.

## Rationale

| Group | Why it belongs together |
|---|---|
| **PersistenceContext** | All repositories share `database` and are injected together into services. They change as a unit when the storage backend changes. |
| **ServiceContext** | Services and use cases form the application layer. Callers that only need persistence shouldn't see these. |
| **MergeMateRuntime** (remainder) | `settings`/`config_path` are bootstrap-time invariants. `worker` and `lifecycle_notifier` are lifecycle-level concerns with no overlap with persistence or business logic. |

## Impact on Callers

The analysis below enumerates every consumer of `MergeMateRuntime` fields in the
source tree.

### Consumer 1: `bootstrap()` itself

The construction site. This is the only place that creates the sub-contexts and
passes them into `MergeMateRuntime(...)`. The change is entirely within this
function — no ripple to callers below.

### Consumer 2: `cli.py` — `run_bot()`, `install_package`, etc.

| Current access | New access |
|---|---|
| `runtime.settings` | `runtime.settings` (unchanged) |
| `runtime.tool_service` | `runtime.services.tool_service` |

`runtime.tool_service` appears at lines 149, 163, 176 → change to
`runtime.services.tool_service`.

### Consumer 3: `interfaces/telegram/bot.py` — `TelegramBotRuntime`

| Current access | New access |
|---|---|
| `runtime.settings` | `runtime.settings` (unchanged) |

`self._runtime.settings` and `self._runtime.settings.telegram` are the only accesses. **No change needed** for settings — it stays on the top-level runtime.

### Consumer 4: `interfaces/telegram/handlers.py`

All handlers receive `runtime` from `context.application.bot_data["runtime"]`.

| Current access | New access |
|---|---|
| `runtime.settings` | `runtime.settings` (unchanged) |
| `runtime.get_run_status.execute(...)` | `runtime.services.get_run_status.execute(...)` |
| `runtime.submit_prompt.approve(...)` | `runtime.services.submit_prompt.approve(...)` |
| `runtime.submit_prompt.revise_plan_for_chat(...)` | `runtime.services.submit_prompt.revise_plan_for_chat(...)` |
| `runtime.cancel_run.execute(...)` | `runtime.services.cancel_run.execute(...)` |

Handlers reference `get_run_status`, `submit_prompt`, and `cancel_run` — all
move into `runtime.services.*`.

### Consumer 5: `interfaces/telegram/progress_notifier.py`

```python
runtime.get_run_status.execute(run_id)
```

→ `runtime.services.get_run_status.execute(run_id)`

### Consumer 6: `interfaces/telegram/lifecycle_notifier.py`

`TelegramRunLifecycleNotifier` stores `self._runtime` via `bind_runtime(runtime)`.
It only accesses `self._runtime.*` in `notify_started` and related methods.  
Access is through the `_RunLike` Protocol, not direct field access. **No change
needed** as long as the runtime passed via `bind_runtime()` still provides the
methods the notifier calls.

### Consumer 7: `domain/workflows/handlers.py`

All handlers access fields via `runtime.deps.*`, not `MergeMateRuntime` fields
directly. This file does NOT use `runtime.repository` — it uses
`runtime.deps.run_repository`. **No change needed** — `runtime` in handlers is
`ExecutionRuntime`, not `MergeMateRuntime`.

### Consumer 8: Tests (indirect)

Tests construct `MergeMateRuntime` for integration tests, or mock a portion of
it. The test file at `tests/unit/mergemate/test_bootstrap.py` is the main
consumer. Construction will need to wrap fields into the new sub-contexts.

## Migration Strategy

### Phase 1 — Add sub-context dataclasses + dot-access shim (single commit)

1. Define `PersistenceContext` and `ServiceContext` dataclasses in
   `src/mergemate/bootstrap.py`.
2. Modify `MergeMateRuntime` to have 6 fields and construct sub-contexts
   in `bootstrap()`.
3. Add **backward-compatible property shims** on `MergeMateRuntime`:

```python
@dataclass(slots=True)
class MergeMateRuntime:
    settings: AppConfig
    config_path: Path
    persistence: PersistenceContext
    services: ServiceContext
    worker: BackgroundRunWorker
    lifecycle_notifier: TelegramRunLifecycleNotifier

    # ── Dot-access backward compatibility shims ─────────────────────
    @property
    def database(self) -> SQLiteDatabase:
        return self.persistence.database

    @property
    def run_repository(self) -> SQLiteRunRepository:
        return self.persistence.run_repository

    @property
    def run_job_repository(self) -> SQLiteRunJobRepository:
        return self.persistence.run_job_repository

    @property
    def conversation_repository(self) -> SQLiteConversationRepository:
        return self.persistence.conversation_repository

    @property
    def learning_repository(self) -> SQLiteLearningRepository:
        return self.persistence.learning_repository

    @property
    def tool_event_repository(self) -> SQLiteToolEventRepository:
        return self.persistence.tool_event_repository

    @property
    def queue_backend(self) -> JobQueueBackend:
        return self.services.queue_backend

    @property
    def learning_service(self) -> LearningService:
        return self.services.learning_service

    @property
    def tool_service(self) -> ToolService:
        return self.services.tool_service

    @property
    def planning_service(self) -> PlanningService:
        return self.services.planning_service

    @property
    def workflow_service(self) -> WorkflowService:
        return self.services.workflow_service

    @property
    def submit_prompt(self) -> SubmitPromptUseCase:
        return self.services.submit_prompt

    @property
    def get_run_status(self) -> GetRunStatusUseCase:
        return self.services.get_run_status

    @property
    def cancel_run(self) -> CancelRunUseCase:
        return self.services.cancel_run
```

These shims mean every existing caller continues to work unmodified **without
any behavioral change**. Mypy will accept them since the return types match the
old field types exactly.

4. Run the full test suite to confirm no regression.

### Phase 2 — Migrate callers to `runtime.services.*` (separate commit)

After Phase 1 is green, gradually update callers:

| File | Changes |
|---|---|
| `cli.py` | `runtime.tool_service` → `runtime.services.tool_service` (lines 149, 163, 176) |
| `interfaces/telegram/handlers.py` | `runtime.get_run_status` → `runtime.services.get_run_status` (lines 101, 119, 135, 192, 204, 233), `runtime.submit_prompt` → `runtime.services.submit_prompt` (lines 141, 198), `runtime.cancel_run` → `runtime.services.cancel_run` (line 166) |
| `interfaces/telegram/progress_notifier.py` | `runtime.get_run_status` → `runtime.services.get_run_status` |
| Tests | Update `test_bootstrap.py` construction and any direct field access |

### Phase 3 — Remove property shims (separate commit, optional)

Once no caller references the old flat property names, delete the backward
compatibility properties from `MergeMateRuntime`. This is optional — the shims
are cheap (one extra function call) and provide a gentler upgrade path for
plugin developers who depend on `MergeMateRuntime`.

## Files to Change

| File | Change description |
|---|---|
| `src/mergemate/bootstrap.py` | Add `PersistenceContext` + `ServiceContext` dataclasses; refactor `MergeMateRuntime` to 6 fields + backward-compat properties; update `bootstrap()` construction |
| `src/mergemate/cli.py` | Phase 2: `runtime.tool_service` → `runtime.services.tool_service` (3 occurrences) |
| `src/mergemate/interfaces/telegram/handlers.py` | Phase 2: use-case field access → `runtime.services.*` (11 occurrences) |
| `src/mergemate/interfaces/telegram/progress_notifier.py` | Phase 2: `runtime.get_run_status` → `runtime.services.get_run_status` |
| `tests/unit/mergemate/test_bootstrap.py` | Phase 2: update construction/mocking |

## No Behavioral Change Expected

- All existing callers continue to work via the backward-compatible property
  shims in Phase 1.
- After Phase 2, the dot-access pattern is explicit but semantically identical.
- `PersistenceContext` and `ServiceContext` have `@dataclass(slots=True)`,
  preserving the same memory characteristics as the current flat dataclass.
- The properties return the exact same object references — no copies, no
  wrappers.
- Test assertions that compare `runtime.run_repository` (old) vs
  `runtime.persistence.run_repository` (new) will find the same object via `is`.