# HandlerContext Protocol — decouple domain from application

**Task:** [t_7ff79891](https://github.com/djwinter29-oss/MergeMate/issues?q=is%3Apr+t_7ff79891)

## Problem

`src/mergemate/domain/workflows/handlers.py` imported `ExecutionRuntime` from
`mergemate.application.execution_plan` under `TYPE_CHECKING`, breaking the
domain-layer isolation rule. The `StageHandler = Any` type alias was a
type-safety hole that bypassed all type checking on handler signatures.

## Changes

### `src/mergemate/domain/workflows/handlers.py`

1. **Defined `HandlerContext` protocol** — a structural protocol in the domain
   layer exposing only the `deps: Any` property that handlers actually consume.
   Uses `@runtime_checkable` so it can be verified at runtime.

2. **Replaced `StageHandler = Any`** with a callable `Protocol` class that
   matches the actual handler signature:
   ```
   async (runtime: HandlerContext, artifacts: dict[str, Any],
          *, agent_name: str) -> dict[str, Any]
   ```

3. **Removed** the `TYPE_CHECKING` guard and the `from mergemate.application.execution_plan import ExecutionRuntime` import.

4. **Updated all 8 handler functions** (`_handle_design`, `_handle_implementation`,
   `_handle_testing`, `_handle_review`, `_handle_replanning`, `_handle_chronicle`,
   `_handle_direct`) and 2 helper functions (`_persist_artifacts`, `_save_document`)
   to use `HandlerContext` in place of `ExecutionRuntime`.

### `src/mergemate/application/execution_plan.py`

No changes needed — `ExecutionRuntime` structurally satisfies `HandlerContext`
(via its `deps: OrchestratorDependencies` attribute).

## Verification

- **Tests:** 753 passed, 4 skipped (unchanged)
- **Ruff:** no issues
- **Mypy:** no issues across all 72 source files