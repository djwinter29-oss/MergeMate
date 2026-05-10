# WorkflowRegistry Module

## File Created

`src/mergemate/domain/workflows/registry.py`

## API

Module-level `_WORKFLOW_REGISTRY: dict[str, WorkflowDefinition]` backed by four public functions:

| Function | Signature | Description |
|----------|-----------|-------------|
| `register_workflow` | `(name: str, definition: WorkflowDefinition) -> None` | Registers a workflow. Raises `KeyError` if name already registered. |
| `get_workflow` | `(name: str) -> WorkflowDefinition \| None` | Lookup by name, returns `None` for unknown names. |
| `get_all_workflows` | `() -> dict[str, WorkflowDefinition]` | Returns a **copy** of the internal dict (caller can't mutate the registry). |
| `known_workflow_names` | `() -> frozenset[str]` | Returns all registered names as a frozenset. |

## Design Decisions

- **String-keyed, not enum-keyed** — any string is a valid workflow name. The `WorkflowName` enum stays for backward compat but new code uses strings directly.
- **Dict, not list** — O(1) lookup, built-in overwrite detection.
- **Module-level dict, not class** — matches the existing `_HANDLERS` pattern in `handlers.py`; no need for a class instance when there's only one registry.
- **`register_workflow` raises on conflict** — prevents silent overwrites from conflicting plugins.
- **`get_all_workflows` returns a copy** — callers can iterate safely without the registry changing under them.

## PR #82

Branch: `feat/workflow-registry`  
PR: https://github.com/djwinter29-oss/MergeMate/pull/82