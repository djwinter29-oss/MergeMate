"""Workflow registry — string-keyed lookup for ``WorkflowDefinition``.

Replaces the frozen ``_BUILTIN_WORKFLOWS`` dict in ``stage.py``
as the canonical source of truth for known workflows.  New
workflows can be registered at import time by in-repo code or
by third-party plugin packages via ``mergemate.workflows``
entry points.
"""

from __future__ import annotations

from mergemate.domain.workflows.stage import WorkflowDefinition


_WORKFLOW_REGISTRY: dict[str, WorkflowDefinition] = {}


def register_workflow(name: str, definition: WorkflowDefinition) -> None:
    """Register a named workflow definition.

    Raises ``KeyError`` if *name* is already registered (to prevent
    silent overwrites from conflicting plugins).

    Called at import time by in-repo modules or by third-party
    plugin packages using ``mergemate.workflows`` entry points.
    """
    if name in _WORKFLOW_REGISTRY:
        raise KeyError(
            f"Workflow {name!r} is already registered. Existing: {_WORKFLOW_REGISTRY[name].name!r}"
        )
    _WORKFLOW_REGISTRY[name] = definition


def get_workflow(name: str) -> WorkflowDefinition | None:
    """Look up a workflow definition by name.

    Returns ``None`` when *name* is unknown.  Callers handle this
    the same way they handle an unknown ``WorkflowName`` value today.
    """
    return _WORKFLOW_REGISTRY.get(name)


def get_all_workflows() -> dict[str, WorkflowDefinition]:
    """Return a copy of the full registry."""
    return dict(_WORKFLOW_REGISTRY)


def known_workflow_names() -> frozenset[str]:
    """Return all registered workflow names."""
    return frozenset(_WORKFLOW_REGISTRY)
