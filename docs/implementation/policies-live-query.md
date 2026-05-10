# Policies: Live-query WorkflowRegistry

**Task:** [t_d53dcac6](https://github.com/djwinter29-oss/MergeMate/issues?q=is%3Apr+t_d53dcac6)

## Changes

### `src/mergemate/domain/policies/__init__.py`

1. **Removed** frozen `_MULTI_STAGE_WORKFLOWS` — no longer derived at import time
2. **Replaced** import of `get_workflow_definitions` from `stage.py` with `get_workflow` from `registry.py`
3. **Updated** `uses_multi_stage_delivery()` to:
   - Query `get_workflow()` (str-keyed) from the live registry
   - Try `WorkflowName` resolution first; if it fails (plugin workflow), query with the raw string
   - Return `get_workflow(name) is not None` — any registered workflow is multi-stage
4. **Updated** `__all__`: `get_workflow_definitions` replaced by `get_workflow`

### Rationale

- Removes the import-time freeze of workflow definitions, enabling plugin workflows to be registered after module import but before policy evaluation
- Preserves backward compatibility with both `str` and `WorkflowName` callers
- Plugin workflows (strings not in `WorkflowName` enum) fall through to raw-string registry lookup