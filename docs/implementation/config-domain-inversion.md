# Implementation: Config-to-Domain Dependency Inversion

- **Status:** Complete
- **Related architecture doc:** [docs/architecture/config-domain-inversion.md](../architecture/config-domain-inversion.md)
- **Branch:** `impl/config-domain-inversion`

## Changes Made

### File modified: `src/mergemate/config/models.py`

#### 1. Removed domain imports

Removed three import lines that created reverse dependencies from `config/` → `domain/`:

```python
from mergemate.domain.shared.exceptions import (
    AgentNotFoundError, ConfigurationError, ProviderNotFoundError, WorkflowNotFoundError,
)
from mergemate.domain.policies import is_user_facing_workflow
from mergemate.domain.shared import WorkflowName
```

#### 2. Added config-local workflow name constants

```python
_WORKFLOW_PLANNING = "planning"
_WORKFLOW_DESIGN = "design"
_WORKFLOW_GENERATE_CODE = "generate_code"
_WORKFLOW_DEBUG_CODE = "debug_code"
_WORKFLOW_EXPLAIN_CODE = "explain_code"
_WORKFLOW_TESTING = "testing"
_WORKFLOW_REVIEW = "review"
_WORKFLOW_LEARNING = "learning"

_USER_FACING_WORKFLOWS: frozenset[str] = frozenset({
    _WORKFLOW_GENERATE_CODE,
    _WORKFLOW_DEBUG_CODE,
    _WORKFLOW_EXPLAIN_CODE,
})
```

These are private (`_`-prefixed) to prevent them from becoming a new public API. They mirror the domain `WorkflowName` enum using value semantics (plain strings).

#### 3. Added config-local exception classes

```python
class ConfigError(ValueError):
    """Base exception for config-layer errors."""

class ConfigAgentNotFoundError(ConfigError):
    """Referenced agent is not configured."""

class ConfigProviderNotFoundError(ConfigError):
    """Referenced provider is not configured."""

class ConfigWorkflowNotFoundError(ConfigError):
    """No agent found for the requested workflow."""
```

All inherit from `ValueError`, maintaining backward compatibility with existing `except ValueError` handlers.

#### 4. Changed field types from `WorkflowName` to `str`

- `RoleConfig.workflow`: `WorkflowName` → `str`
- `AgentConfig.workflow`: `WorkflowName` → `str`

Since Pydantic accepts raw string values from YAML config and `WorkflowName` is a `str` subclass at runtime, this is fully backward compatible. No config file changes needed.

#### 5. Replaced `is_user_facing_workflow()` call

Changed from:
```python
if not is_user_facing_workflow(default_agent_workflow):
```
To:
```python
if default_agent_workflow not in _USER_FACING_WORKFLOWS:
```

#### 6. Replaced `WorkflowName.*` enum references

| Before | After |
|--------|-------|
| `WorkflowName.PLANNING` | `_WORKFLOW_PLANNING` |
| `WorkflowName.GENERATE_CODE` | `_WORKFLOW_GENERATE_CODE` |
| `WorkflowName.DESIGN` | `_WORKFLOW_DESIGN` |
| `WorkflowName.TESTING` | `_WORKFLOW_TESTING` |
| `WorkflowName.REVIEW` | `_WORKFLOW_REVIEW` |
| `workflow.value` in counter | `workflow` (direct string) |

#### 7. Updated `resolve_agent_name_for_workflow()`

- Parameter type: `str | WorkflowName` → `str`
- Removed `WorkflowName(workflow)` conversion (unnecessary with `str` type)
- Replaced `WorkflowNotFoundError` → `ConfigWorkflowNotFoundError`
- Removed `.value` access on `resolved_workflow`

### Backward Compatibility

All 66 existing config model tests pass unchanged because:
- Pydantic accepts `"planning"` string values for `str` fields the same as for `WorkflowName` fields
- `WorkflowName` is a `str` subclass, so passing `WorkflowName.GENERATE_CODE` to methods expecting `str` works
- `ConfigError` inherits from `ValueError`, so `pytest.raises(ValueError, ...)` still catches it
- No YAML config schema changes

### Architectural Impact

- `config/models.py` no longer imports from `mergemate.domain`
- The `domain/` package is untouched (zero changes)
- If a domain module ever needs a config type, the dependency graph remains acyclic
- Config-local exceptions enable clean separation of concerns — application code can catch `ConfigError` without importing domain exceptions

## Acceptance Criteria

1. [x] `config/models.py` no longer imports from `mergemate.domain`
2. [x] `RoleConfig.workflow` and `AgentConfig.workflow` are typed as `str`
3. [x] `resolve_agent_name_for_workflow()` accepts `str` (not `WorkflowName`)
4. [x] `validate_provider_references()` uses config-local constants for workflow validation
5. [x] Config-local exceptions are raised instead of domain exceptions
6. [x] All existing tests pass without modification (backward compatible)
7. [x] No changes to `domain/` package
8. [x] No changes to YAML config schema