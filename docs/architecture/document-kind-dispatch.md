# Document Kind Dispatch: if/elif -> dict + decorator

- Run ID: (design doc, no run)
- Date: 2026-05-10
- Author: Architect
- Status: Draft

## 1. Problem Statement

In `src/mergemate/domain/workflows/handlers.py` lines 280-340,
`_save_document()` dispatches on `kind` through a 4-branch if/elif chain:

```python
def _save_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    ...
    if kind == "architecture":
        ...
    elif kind == "testing":
        ...
    elif kind == "review":
        ...
    elif kind == "lessons":
        ...
```

Adding a new document kind (e.g., `requirements` was recently added to
`DocumentationService.write_requirement()` but has no `_save_document` branch)
requires:
1. Adding another `elif` branch.
2. Remembering which handlers call `_save_document` — no single registration point.

This violates the Open/Closed Principle: the module is open to extension but the
dispatch logic forces modification of an existing function.

---

## 2. Proposed Design

Replace the if/elif chain with a dispatch dict (`{kind: callable}`) and a
`@register_document_kind(kind)` decorator, mirroring the existing
`@register_handler(key)` pattern already used in the same file for stage
handlers.

### 2.1 Decorator + Registry

```python
# ── Document kind registry ───────────────────────────────────────────────

_DOCUMENT_KINDS: dict[str, DocumentSaver] = {}


def register_document_kind(kind: str) -> Callable[[DocumentSaver], DocumentSaver]:
    """Decorator that registers a document-saver function under *kind*."""
    def _decorator(fn: DocumentSaver) -> DocumentSaver:
        _DOCUMENT_KINDS[kind] = fn
        return fn
    return _decorator
```

### 2.2 DocumentSaver Protocol

Each saver function accepts a standard bag of parameters and writes into
`artifacts`.  No Protocol class is strictly needed (runtime duck-typing is
fine) but for clarity the type alias below documents the contract:

```python
DocumentSaver = Callable[
    ...,
    None,
]
```

Concretely, every registered function has this signature:

```python
def _save_<kind>(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,                 # passed for symmetry / future
    agent_name: str | None,
    **extra: Any,
) -> None: ...
```

### 2.3 Refactored _save_document

The if/elif function shrinks to a single lookup:

```python
def _save_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    """Write a documentation artifact and store its path in ``artifacts``."""
    saver = _DOCUMENT_KINDS.get(kind)
    if saver is None:
        raise ValueError(
            f"Unknown document kind {kind!r}. "
            f"Registered kinds: {sorted(_DOCUMENT_KINDS)}"
        )
    saver(runtime, artifacts, kind, agent_name=agent_name, **extra)
```

This makes `_save_document` a stable dispatcher — new kinds never touch it.

---

## 3. Decorator API Reference

### `@register_document_kind(kind: str)`

- **kind**: A unique string key matching the `kind` argument passed to
  `_save_document()`.

- **Decorated function contract**:
  - Must accept `(runtime, artifacts, kind, agent_name, **extra)`.
  - Must mutate `artifacts` with the document path key (e.g.
    `artifacts["_design_document_path"] = path`).
  - Should call `runtime.deps.documentation_service.write_<kind>(...)`.

- **Registration happens at import time**: functions decorated at module scope
  populate `_DOCUMENT_KINDS` when the module is loaded.

- **Duplicate detection**: registering the same `kind` twice overwrites the
  previous entry (same semantics as `_HANDLERS`).  A `stacklevel`-aware warning
  via `warnings.warn()` is RECOMMENDED but not required for the initial
  migration.

---

## 4. Migration Plan

The migration is purely structural — no behavioral change expected (verified by
existing tests passing).

### Phase 1: Add registry + decorator (same file)

1. After the `_HANDLERS` registry block (line 73) add `_DOCUMENT_KINDS` dict
   and `register_document_kind` decorator.

2. Define a private helper to reduce boilerplate in the four saver functions:

```python
def _save_to_artifacts(
    artifacts: dict[str, Any],
    path: Path,
    artifact_key: str,
) -> None:
    """Store a document path in artifacts under the appropriate key."""
    artifacts[artifact_key] = str(path)
```

This can be shared by all saver functions.

### Phase 2: Extract four saver functions

Replace the inline bodies in `_save_document` with top-level decorated
functions, each placed right before the function that calls it (so they stay
near their call site visually):

#### architecture

```python
@register_document_kind("architecture")
def _save_architecture_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_architecture_design(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            design_text=extra.get("design_text", ""),
            role_name=agent_name,
        ),
        "_design_document_path",
    )
```

#### testing

```python
@register_document_kind("testing")
def _save_testing_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_test_plan(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            design_text=extra.get("design_text", ""),
            test_text=extra.get("test_text", ""),
            role_name=agent_name,
        ),
        "_test_document_path",
    )
```

#### review

```python
@register_document_kind("review")
def _save_review_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_review_report(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            design_text=extra.get("design_text", ""),
            implementation_text=extra.get("implementation_text", ""),
            test_text=extra.get("test_text", ""),
            review_text=extra.get("review_text", ""),
            role_name=agent_name,
        ),
        "_review_document_path",
    )
```

#### lessons

```python
@register_document_kind("lessons")
def _save_lessons_document(
    runtime: HandlerContext,
    artifacts: dict[str, Any],
    kind: str,
    agent_name: str | None = None,
    **extra: Any,
) -> None:
    _save_to_artifacts(
        artifacts,
        runtime.deps.documentation_service.write_lesson(
            run_id=artifacts["run_id"],
            iteration=artifacts.get("_iteration", 0),
            plan_text=artifacts.get("plan_text", ""),
            lesson_text=extra.get("lesson_text", ""),
            role_name=agent_name,
        ),
        "_lesson_document_path",
    )
```

### Phase 3: Replace _save_document body

Replace the if/elif chain with the single-lookup version shown in §2.3.

### Phase 4: Update __all__

No new names need to be public — `_DOCUMENT_KINDS` and
`register_document_kind` are module-private.  `__all__` is unchanged.

### Phase 5: Run tests

```bash
pytest tests/ -k "handler" -x
```

All four existing document kinds should produce identical paths, same
`artifacts` keys, same file content.  No test changes required.

---

## 5. Files to Change

| File | Change |
|---|---|
| `src/mergemate/domain/workflows/handlers.py` | Add registry + decorator, extract 4 saver functions, replace if/elif body |

No other files need changes.  The `DocumentationService` is untouched — its
interface is consumed by the extracted functions, not altered.

---

## 6. Test Strategy

### No behavioral change (gating criteria)

All existing tests MUST continue to pass without modification.

### Verification points

1. **Registration** — `_DOCUMENT_KINDS` contains exactly the four keys
   `{"architecture", "testing", "review", "lessons"}` after module load.
2. **Dispatch correctness** — `_save_document` with `kind="architecture"` calls
   the architecture saver (verify via mock).
3. **Unknown kind** — `_save_document` with `kind="requirements"` raises
   `ValueError` with registered kinds in the message.
4. **Artifact keys** — each saver sets the correct `_<kind>_document_path`
   key in artifacts.

### Suggested test file

Add a small test module at `tests/unit/workflows/test_document_kind_dispatch.py`
that covers these four points.  The existing handler tests already cover end-to-
end behavior; this unit-level test covers the dispatch mechanism alone.

---

## 7. Alternative Considered: Class-based Strategy Pattern

A class hierarchy (`SaveArchitectureDocument`, `SaveTestingDocument`, etc.)
implementing a `DocumentSaver` protocol was considered but rejected because:

- The existing codebase uses function-level decorator-based dispatch
  (`@register_handler`) — consistency wins.
- The saver functions are thin wrappers (each ~10 lines); classes add
  ceremony disproportionate to the logic.
- A class hierarchy makes it harder to add a new kind in a single file
  (you'd need a new class in a new file or a long file of small classes).

The decorator approach keeps all document kind logic co-located in the same
module as the callers, minimizing the diff and cognitive load.

---

## 8. Future Concerns

### Duplicate registration protection

If `_DOCUMENT_KINDS` is populated by entry-point discovery in a future plugin
system, the `register_document_kind` decorator should warn on duplicate kinds:

```python
import warnings

def register_document_kind(kind: str) -> Callable:
    def _decorator(fn):
        if kind in _DOCUMENT_KINDS:
            warnings.warn(
                f"Document kind {kind!r} already registered by "
                f"{_DOCUMENT_KINDS[kind].__module__}.{_DOCUMENT_KINDS[kind].__qualname__}; "
                f"overwriting with {fn.__module__}.{fn.__qualname__}.",
                stacklevel=2,
            )
        _DOCUMENT_KINDS[kind] = fn
        return fn
    return _decorator
```

This is NOT needed in the initial migration (module-level decorators cannot
collide at import time) but is cheap to add now for forward compatibility.

### Plugin-extensible kinds

In a future plugin architecture, external packages could register document
kinds via entry points (e.g. `mergemate.document_kinds`).  This design
requires no changes for that — entry-point loading would just call
`register_document_kind` for each discovered saver.