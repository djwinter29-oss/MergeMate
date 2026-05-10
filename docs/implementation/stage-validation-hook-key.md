# Stage refactor: `validation_hook_key` field + auto-register built-in workflows

## Changes

### 1. `WorkflowStage.validation_hook_key` field

Added `validation_hook_key: str = ""` to the `WorkflowStage` dataclass, inserted after `prompt_template`. When non-empty, the execution plan can use this key to look up post-stage validation hooks from `mergemate.domain.workflows.validation`.

**Motivation:** A stage may need a different validation handler key than its execution handler. For example, a generic `"direct"` handler might need `"implementation"`-level validation, or a custom workflow might reuse a standard handler while still getting standard validation.

### 2. Auto-register built-in workflows with `WorkflowRegistry`

The built-in workflow definitions (`_BUILTIN_WORKFLOWS` dict in `stage.py`) are now registered with the string-keyed registry at module load time. The registration is triggered from `mergemate.domain.workflows.__init__` (not from `stage.py`'s module body) to avoid a circular import:

```
stage.py (defines WorkflowDefinition) ← registry.py (imports WorkflowDefinition)
```

The call chain:
1. `mergemate.domain.workflows.__init__` imports all submodules
2. After imports complete, it calls `_register_builtin_workflows()`
3. This function lazily imports `register_workflow` from `registry.py`
4. Each `_BUILTIN_WORKFLOWS` entry (keyed by `WorkflowName`) is registered with its `.value` string

### 3. `get_workflow_definitions()` now delegates to registry

`get_workflow_definitions()` now calls `get_all_workflows()` from the registry instead of returning `dict(_BUILTIN_WORKFLOWS)`. It still returns `dict[WorkflowName, WorkflowDefinition]` for backward compatibility — only entries whose string keys match a known `WorkflowName` enum value are included.

**Backward compat:** Both callers (`policies/__init__.py` and `workflow_service.py`) use `WorkflowName` keys and continue to work unchanged.

## Files changed

| File | Change |
|---|---|
| `src/mergemate/domain/workflows/stage.py` | Added `validation_hook_key` field, added `_register_builtin_workflows()`, refactored `get_workflow_definitions()` |
| `src/mergemate/domain/workflows/__init__.py` | Added deferred auto-registration call after submodule imports |