# Document Kind Dispatch — Decorator Migration

- **Run ID**: (coding, no separate run)
- **Date**: 2026-05-10
- **Author**: Coder
- **Status**: Done

## Summary

Replaced the if/elif chain in `_save_document()` with a decorator-based dispatch pattern using `_DOCUMENT_KINDS` registry.

## Changed File

`src/mergemate/domain/workflows/handlers.py`

## Changes Made

### 1. New imports
- `import warnings` — for duplicate-registration warning (forward-compat)
- `from pathlib import Path` — type hint for `_save_to_artifacts`

### 2. Document kind registry (after built-in handlers)
- `DocumentSaver = Callable[..., None]` — type alias
- `_DOCUMENT_KINDS: dict[str, DocumentSaver] = {}` — registry dict
- `register_document_kind(kind: str)` — decorator with duplicate warning

### 3. Four extracted saver functions
- `_save_architecture_document` — calls `write_architecture_design`
- `_save_testing_document` — calls `write_test_plan`
- `_save_review_document` — calls `write_review_report`
- `_save_lessons_document` — calls `write_lesson`

Each is decorated with `@register_document_kind(...)` and uses the shared `_save_to_artifacts` helper.

### 4. `_save_to_artifacts` helper
A private function that stores a `Path` in `artifacts` under a given key, reducing boilerplate in the four saver functions.

### 5. Refactored `_save_document`
The if/elif body was replaced with a single lookup:
```python
saver = _DOCUMENT_KINDS.get(kind)
if saver is None:
    raise ValueError(
        f"Unknown document kind {kind!r}. "
        f"Registered kinds: {sorted(_DOCUMENT_KINDS)}"
    )
saver(runtime, artifacts, kind, agent_name=agent_name, **extra)
```

## Verification
- 21 integration tests pass (covers all 4 document kinds via handler dispatch)
- Registry contains exactly 4 keys: `architecture`, `testing`, `review`, `lessons`
- Unknown kind raises `ValueError` with sorted list of registered kinds
- No behavioral change — existing tests pass unchanged