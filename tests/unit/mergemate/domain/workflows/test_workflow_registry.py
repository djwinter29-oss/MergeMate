"""Tests for workflow registry — registration, lookup, and enumeration."""

from __future__ import annotations

import pytest

from mergemate.domain.workflows.registry import (
    _WORKFLOW_REGISTRY,
    get_all_workflows,
    get_workflow,
    known_workflow_names,
    register_workflow,
)
from mergemate.domain.workflows.stage import WorkflowDefinition


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Snapshot and restore the global registry after each test."""
    snapshot = dict(_WORKFLOW_REGISTRY)
    _WORKFLOW_REGISTRY.clear()
    yield
    _WORKFLOW_REGISTRY.clear()
    _WORKFLOW_REGISTRY.update(snapshot)


# ── Helpers ─────────────────────────────────────────────────────────────


def _dummy_definition(name: str = "test") -> WorkflowDefinition:
    return WorkflowDefinition(
        name=name,
        stages=[
            {"name": "stage1", "current_stage": "stage1"},
        ],
    )


# ── register_workflow ───────────────────────────────────────────────────


def test_register_workflow_stores_definition() -> None:
    """register_workflow adds a definition that can be retrieved."""
    wf = _dummy_definition("myworkflow")
    register_workflow("myworkflow", wf)

    assert get_workflow("myworkflow") is wf


def test_register_workflow_raises_on_duplicate() -> None:
    """Registering the same name twice raises KeyError."""
    wf1 = _dummy_definition("conflict")
    wf2 = _dummy_definition("conflict")

    register_workflow("conflict", wf1)

    with pytest.raises(KeyError, match="already registered"):
        register_workflow("conflict", wf2)


def test_register_workflow_keeps_first_on_duplicate() -> None:
    """On duplicate registration, the original entry is preserved."""
    wf1 = _dummy_definition("dup")
    wf2 = _dummy_definition("dup")

    register_workflow("dup", wf1)

    with pytest.raises(KeyError):
        register_workflow("dup", wf2)

    assert get_workflow("dup") is wf1


def test_register_workflow_multiple_names() -> None:
    """Multiple different names can be registered independently."""
    wf_a = _dummy_definition("wf_a")
    wf_b = _dummy_definition("wf_b")

    register_workflow("wf_a", wf_a)
    register_workflow("wf_b", wf_b)

    assert get_workflow("wf_a") is wf_a
    assert get_workflow("wf_b") is wf_b


# ── get_workflow ────────────────────────────────────────────────────────


def test_get_workflow_returns_none_for_unknown() -> None:
    """An unregistered name returns None, not an error."""
    result = get_workflow("nonexistent")

    assert result is None


def test_get_workflow_returns_none_for_empty_registry() -> None:
    """Empty registry returns None for any query."""
    assert get_workflow("anything") is None


# ── get_all_workflows ───────────────────────────────────────────────────


def test_get_all_workflows_returns_copy() -> None:
    """Returned dict is a copy; mutating it does not affect the registry."""
    wf = _dummy_definition("copy_test")
    register_workflow("copy_test", wf)

    all_wf = get_all_workflows()
    all_wf.clear()

    assert "copy_test" in get_all_workflows()


def test_get_all_workflows_returns_all_registered() -> None:
    """get_all_workflows returns all registered workflows."""
    register_workflow("a", _dummy_definition("a"))
    register_workflow("b", _dummy_definition("b"))
    register_workflow("c", _dummy_definition("c"))

    result = get_all_workflows()
    assert set(result.keys()) == {"a", "b", "c"}


def test_get_all_workflows_empty_registry() -> None:
    """Empty registry returns an empty dict."""
    assert get_all_workflows() == {}


# ── known_workflow_names ────────────────────────────────────────────────


def test_known_workflow_names_returns_registered_names() -> None:
    """known_workflow_names returns all registered workflow names."""
    register_workflow("alpha", _dummy_definition("alpha"))
    register_workflow("beta", _dummy_definition("beta"))

    assert known_workflow_names() == frozenset({"alpha", "beta"})


def test_known_workflow_names_empty_registry() -> None:
    """Empty registry returns an empty frozenset."""
    assert known_workflow_names() == frozenset()
