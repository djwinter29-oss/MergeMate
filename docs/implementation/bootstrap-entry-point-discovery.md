# Bootstrap: Entry-Point Discovery for Workflow Plugins

## Overview

Two new functions added to `src/mergemate/bootstrap.py` that load workflow
plugin registrations at startup, before any service is instantiated.

## Functions

### `discover_workflow_plugins()`

Uses `importlib.metadata.entry_points` to scan the `mergemate.workflows`
entry point group. Each registered callable is invoked immediately.

Plugin authors package their plugins via:

```toml
[project.entry-points."mergemate.workflows"]
my_plugin = "my_plugin_package:register"
```

Errors from individual plugins are swallowed and logged as warnings — a
single misbehaving plugin never blocks the bootstrap sequence.

### `_load_workflow_config_plugins(settings: AppConfig)`

Reads the `workflow_plugins` field from `AppConfig` (a `list[str | dict]`).
Each entry is either:

- A **str**: treated as a Python module path; its `register()` function
  is called with no arguments.
- A **dict**: must contain a `module` key; all other keys are collected
  into a `config` dict and passed to `register(config)`.

Errors are logged as warnings (same resilience pattern).

## Config model change

Added `workflow_plugins: list[str | dict] = Field(default_factory=list)`
to the `AppConfig` class in `src/mergemate/config/models.py`.

## Bootstrap execution order

Both functions are called in `bootstrap()` immediately after
`configure_logging()` and before `SQLiteDatabase(...)`:

1. `resolve_config_path`
2. `load_runtime_settings`
3. `configure_logging`
4. **`discover_workflow_plugins()`**
5. **`_load_workflow_config_plugins(settings)`**
6. database init, service wiring, etc.

This ensures workflow definitions are in the `_WORKFLOW_REGISTRY` dict
before any service (RunDispatcher, WorkflowService, AgentOrchestrator)
tries to look them up.

## Files changed

- `src/mergemate/bootstrap.py` — added 2 functions + 2 callers (72 lines)
- `src/mergemate/config/models.py` — added `workflow_plugins` field (1 line)