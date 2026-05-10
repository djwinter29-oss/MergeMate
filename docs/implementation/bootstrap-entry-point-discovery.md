# Bootstrap Entry-Point Discovery

## Overview

Adds two plugin discovery functions to `src/mergemate/bootstrap.py` that are
called early during application startup, **before** any service instances are
created.  This ensures that externally-defined workflows are registered in the
`WorkflowRegistry` (via `register_workflow()`) before any service code tries to
look them up.

## Functions

### `discover_workflow_plugins()`

- Scans the `mergemate.workflows` entry-point group using
  `importlib.metadata.entry_points()`.
- Calls each discovered entry-point's `load()` result — that function is
  expected to invoke `register_workflow()` or `register_validation_hook()` at
  call time.
- Failures are caught and logged as warnings; a broken plugin does not block
  startup.

### `_load_workflow_config_plugins(settings: AppConfig)`

- Iterates `settings.workflow_plugins` (a `list[str | dict]`).
- `str` entries are treated as Python package module names and imported via
  `importlib.import_module()`.  The module's `register_workflow()` calls fire
  at import time.
- `dict` entries must have a `"path"` key pointing to a `.py` file.  The file
  is read and executed via `exec()` with `__file__` and `__name__` set so that
  relative imports inside the plugin work.
- Failures for individual entries are logged as warnings.

## Bootstrap wiring

Both calls are inserted in `bootstrap()` right after:

```python
resolved_config_path = resolve_config_path(config_path)
settings = load_runtime_settings(config_path)
configure_logging(settings.logging.level)
```

...and right before database initialisation.

## Files changed

- `src/mergemate/bootstrap.py` — added `discover_workflow_plugins()`,
  `_load_workflow_config_plugins()`, and two calls in `bootstrap()`.

## Decisions

| Decision | Rationale |
|---|---|
| Lazy imports inside functions | `importlib.metadata.entry_points` is a 3.9+ API; keeping it inside the function avoids module-level side effects.  Also keeps the import section short. |
| Warning-level logging on failure | A broken third-party plugin should not take down the whole application. |
| `exec()` for file-based plugins | Simple, no wrapper module needed.  The `__file__` and `__name__` globals give the executed code a reasonable context. |
| Config plugins loaded **after** entry points | If entry-point plugins register the "framework" workflows first, file-based config plugins can use them (e.g. extend a framework workflow with additional stages). |