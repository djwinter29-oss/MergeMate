# ValidationHook module — Implementation Notes

**File:** `src/mergemate/domain/workflows/validation.py`

## What was built

The `validation.py` module provides a lightweight hook system for injecting
stage-level validation logic into the workflow execution pipeline without
modifying the core engine.

## API surface

| Export | Kind | Purpose |
|---|---|---|
| `ValidationHook` | Protocol (`@runtime_checkable`) | Async callable protocol: `(str, dict[str, Any]) -> bool` |
| `StageValidationHook` | Type alias | `Callable[[str, dict[str, Any]], Awaitable[bool]]` |
| `_VALIDATION_HOOKS` | Module-level dict | `dict[str, list[StageValidationHook]]` — keyed by handler key |
| `register_validation_hook()` | Function | Append a hook for a given handler key |
| `get_validation_hooks()` | Function | Return snapshot list of hooks for a key |
| `run_validation_hooks()` | Async function | Execute all hooks for a key, return False on first failure |

## Design decisions

**Protocol vs plain type alias.** Both `ValidationHook` (protocol) and
`StageValidationHook` (alias) are provided. The protocol gives runtime
type-checking via `isinstance(thing, ValidationHook)`. The alias is the
shorter, more ergonomic form for plain async functions.

**Runtime-checkable.** The protocol is decorated with `@runtime_checkable`
so that tools or frameworks can query `isinstance(obj, ValidationHook)`.

**Advisory-only in Phase 1.** Per the design doc, validation hooks log a
warning on failure but do NOT abort. The return value from
`run_validation_hooks` is available for the caller to decide.

**Exception safety.** If a hook raises, it's caught, logged at ERROR level,
and treated as a failure (returns `False`). This prevents a buggy hook from
halting the entire stage.

**Module-level dict.** Follows the same pattern as `_HANDLERS` in
`handlers.py`. Not thread-safe (same as the rest of the workflow module).
Registration happens at startup, not concurrently during execution.

## What was NOT done (by design)

- No tests (separate tester subtask `t_fc2a75e0`)
- No integration into the execution plan yet (that's a follow-up task)
- No configuration-driven hooks (Phase 2 concern)