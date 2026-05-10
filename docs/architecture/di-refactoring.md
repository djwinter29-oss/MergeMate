# Architecture Design: Replace DI Explosion with Typed Context Object

## Problem

`AgentOrchestrator.__init__` and `ExecutionRuntime` (in
`src/mergemate/application/execution_plan.py`) each repeat the same list of
service/repository dependencies.  `AgentOrchestrator` takes 11 parameters,
`ExecutionRuntime` takes 8.  Both also appear individually in `bootstrap.py`,
and tests must construct both objects with full argument lists.

Every new dependency (or removal of one) currently requires touching:
1. `OrchestratorDependencies` field list
2. `ExecutionRuntime` field list
3. `ExecutionRuntime.from_deps()` mapping
4. `AgentOrchestrator.__init__()` field expansion into `self._*`
5. Every test fixture that constructs either class

This is fragile, violates DRY, and discourages dependency refactoring.

## Current State (Before)

```
OrchestratorDependencies (10 fields, all Any)
├── run_repository
├── context_service
├── documentation_service
├── learning_service
├── planning_service
├── prompt_service
├── tool_service
├── workflow_service
├── llm_gateway
└── settings

ExecutionRuntime (8 fields, all Any)            ← duplicates + drops 3
├── run_repository
├── context_service
├── documentation_service
├── learning_service
├── planning_service
├── workflow_service                             ← reordered
├── settings
└── is_cancelled (Callable)                      ← extra, not in deps

AgentOrchestrator (10 self._* aliases)
├── unpacks each deps field to self._xxx
└── constructs ExecutionRuntime via .from_deps()
```

Key pain points:
- `ExecutionRuntime` drops `prompt_service`, `tool_service`, `llm_gateway`
- `AgentOrchestrator` unpacks 10 fields into 10 `self._` attributes (unnecessary
  indirection — only `_is_cancelled` and `process_run` use them)
- `_check_cancelled` and `_check_after_cancelled` take individual
  `run_repository` and `is_cancelled` parameters rather than receiving the deps
  object

## Target State (After)

```
ExecutionRuntime
  deps: OrchestratorDependencies     ← single typed field
  is_cancelled: Callable             ← stays as instance state

AgentOrchestrator
  deps: OrchestratorDependencies     ← single typed field
  (removes all self._xxx aliases — uses self.deps.xxx directly)
```

### Data-flow diagram

```
 bootstrap.py
    │
    ├── constructs OrchestratorDependencies(...)   ← once
    │
    ├── AgentOrchestrator(deps=...)                ← receives it
    │   └── process_run() → ExecutionRuntime(deps=..., is_cancelled=...)
    │
    └── handlers (design, code, review, etc.)
        └── receive ExecutionRuntime → access runtime.deps.xxx
```

## Changes Required

### 1. `OrchestratorDependencies` — already exists, already typed via protocols.py

No change needed.  It already has the `Protocol`-typed fields from
`service-protocols.md`.  Confirm that all 10 fields are still needed (see
"Optional: pruning" below).

### 2. `ExecutionRuntime` — refactor to hold `deps` instead of expanded fields

**Before:**
```python
@dataclass(slots=True)
class ExecutionRuntime:
    run_repository: Any
    context_service: Any
    documentation_service: Any
    learning_service: Any
    planning_service: Any
    workflow_service: Any
    settings: Any
    is_cancelled: Callable[[str], bool]

    @classmethod
    def from_deps(cls, deps, *, is_cancelled):
        return cls(
            run_repository=deps.run_repository,
            context_service=deps.context_service,
            ...,
            is_cancelled=is_cancelled,
        )
```

**After:**
```python
@dataclass(slots=True)
class ExecutionRuntime:
    deps: OrchestratorDependencies
    is_cancelled: Callable[[str], bool]
```

Every existing `runtime.workflow_service`, `runtime.run_repository`, etc.
becomes `runtime.deps.workflow_service`, `runtime.deps.run_repository`.  The
`from_deps` factory is no longer needed (the constructor itself accepts `deps`).

### 3. `_check_cancelled` and `_check_after_cancelled` — accept deps

**Before:**
```python
def _check_cancelled(
    *, run_id, run_repository, is_cancelled, stage=None,
) -> Any | None:
```

**After:**
```python
def _check_cancelled(
    *, run_id, deps: OrchestratorDependencies, is_cancelled, stage=None,
) -> Any | None:
```

The call sites change from:
```python
_check_cancelled(run_id=run.run_id, run_repository=runtime.run_repository, is_cancelled=runtime.is_cancelled)
```
to:
```python
_check_cancelled(run_id=run.run_id, deps=runtime.deps, is_cancelled=runtime.is_cancelled)
```

### 4. `AgentOrchestrator` — remove field expansion

**Before:**
```python
def __init__(self, deps: OrchestratorDependencies) -> None:
    self._deps = deps
    self._run_repository = deps.run_repository
    self._context_service = deps.context_service
    ...  # 8 more lines
```

**After:**
```python
def __init__(self, deps: OrchestratorDependencies) -> None:
    self._deps = deps
```

All internal references change from `self._run_repository` to `self._deps.run_repository`.

### 5. `bootstrap.py` — no change needed

`bootstrap.py` already constructs `OrchestratorDependencies(...)` once and passes
it to `AgentOrchestrator(deps=...)`.  No changes required.

### 6. Stage handlers — migrate to `runtime.deps.xxx`

All handler calls to `runtime.workflow_service`, `runtime.documentation_service`,
`runtime.planning_service`, `runtime.run_repository` need the `.deps.` prefix
added.  This is a mechanical search-and-replace across `handlers.py`:

| Current | New |
|---|---|
| `runtime.workflow_service` | `runtime.deps.workflow_service` |
| `runtime.documentation_service` | `runtime.deps.documentation_service` |
| `runtime.planning_service` | `runtime.deps.planning_service` |
| `runtime.run_repository` | `runtime.deps.run_repository` |

Handlers also call `runtime.context_service` and `runtime.learning_service`
inside `execution_plan.py`'s `DirectExecutionPlan.execute()` and
`MultiStageExecutionPlan.execute()`.  Those also need `.deps.` prefix.

### 7. Test fixtures — consolidate around `OrchestratorDependencies`

**`test_execution_plan_uncovered.py`** — `_make_runtime()` currently constructs
`ExecutionRuntime` with explicit fields.  Change to:

```python
def _make_runtime(run=None, ..., deps: OrchestratorDependencies | None = None) -> ExecutionRuntime:
    if deps is None:
        deps = _make_deps(run, ...)
    return ExecutionRuntime(deps=deps, is_cancelled=is_cancelled or (lambda _: False))
```

Create a companion `_make_deps()` factory that builds an
`OrchestratorDependencies` with stubs/SimpleNamespace, or let the existing
`_make_runtime` construct the deps internally.

**`test_execution_plan_integration.py`** — `_make_runtime_from_deps()` already
calls `ExecutionRuntime(deps=deps, is_cancelled=is_cancelled)`, which is correct
for the target state.  No change needed to this function.

**`test_orchestrator.py`** — the `AgentOrchestrator` constructor already accepts
`deps`.  No changes needed if fixtures already build an `OrchestratorDependencies` object.

**`test_orchestrator_integration.py`** — same as above.

## Testing Strategy

1. **Unit tests pass** — existing tests in `test_execution_plan_uncovered.py` and
   `test_orchestrator.py` must continue passing after the refactor.  The key
   migration: test fixtures that construct `ExecutionRuntime` with positional
   args switch to `ExecutionRuntime(deps=..., is_cancelled=...)`.

2. **Integration tests pass** — `test_execution_plan_integration.py` and
   `test_orchestrator_integration.py` verify the full `process_run()` path.
   No fixture changes needed beyond the ExecutionRuntime constructor migration.

3. **Static type check** — run `mypy` on the changed files.  With the Protocol
   types already in place, the refactored code should be strictly better typed
   (fewer `Any` field accesses).

4. **No behavioral change** — this is a pure structural refactor.  No service
   call order, error handling path, or side effect changes.

## Optional: Pruning Opportunities

- `AgentOrchestrator` only uses `prompt_service` and `tool_service` inside
  `process_run()` (not stored or used elsewhere).  Storing them via
  `self._deps` is fine — no need to keep `self._prompt_service` aliases.
- `ExecutionRuntime` currently drops `prompt_service`, `tool_service`, and
  `llm_gateway` — after the refactor it carries them automatically via
  `deps`, which is strictly better (no unnecessary omissions).
- `_check_cancelled` and `_check_after_cancelled` could be moved as methods on
  `ExecutionRuntime` or even on `OrchestratorDependencies`, but that is a
  separate refactoring concern.  This design intentionally keeps them as module-
  level functions to minimize diff scope.

## File Impact Summary

| File | Type of Change |
|---|---|
| `src/mergemate/application/execution_plan.py` | Refactor `ExecutionRuntime` to hold `deps`; update `_check_cancelled`/`_check_after_cancelled`; no changes to `OrchestratorDependencies` or execution plan classes |
| `src/mergemate/application/orchestrator.py` | Remove 10 `self._xxx` aliases; update internal references to `self._deps.xxx` |
| `src/mergemate/domain/workflows/handlers.py` | Replace `runtime.xxx` with `runtime.deps.xxx` (mechanical) |
| `tests/unit/mergemate/application/test_execution_plan_uncovered.py` | Migrate `_make_runtime` to use `deps`; add `_make_deps` helper |
| `tests/integration/mergemate/application/test_execution_plan_integration.py` | Already compatible — `_make_runtime_from_deps` works as-is |
| `tests/unit/mergemate/application/test_orchestrator.py` | Verify no change needed; only uses `AgentOrchestrator(deps=...)` |
| `tests/integration/mergemate/application/test_orchestrator_integration.py` | Verify no change needed |
| `src/mergemate/bootstrap.py` | No change needed |