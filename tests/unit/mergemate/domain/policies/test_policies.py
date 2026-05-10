"""Tests for workflow policies — workflow classification and routing."""

from __future__ import annotations

import pytest

from mergemate.domain.policies import (
    is_user_facing_workflow,
    uses_multi_stage_delivery,
    workflow_prompt_file,
)
from mergemate.domain.shared.enums import WorkflowName
from mergemate.domain.workflows.registry import (
    _WORKFLOW_REGISTRY,
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


# ── uses_multi_stage_delivery ───────────────────────────────────────────


def test_uses_multi_stage_delivery_known_builtin_returns_true() -> None:
    """A known WorkflowName that has a registered definition returns True."""
    from mergemate.domain.shared.enums import MULTI_STAGE_WORKFLOWS

    # Pick any multi-stage workflow that has stages defined
    if "implementation" in MULTI_STAGE_WORKFLOWS:
        assert uses_multi_stage_delivery("implementation") is True


def test_uses_multi_stage_delivery_unknown_enum_returns_false() -> None:
    """A WorkflowName with no registered definition returns False."""
    result = uses_multi_stage_delivery(WorkflowName.LEARNING)

    assert result is False


def test_uses_multi_stage_delivery_plugin_workflow_string_returns_true() -> None:
    """A raw plugin workflow string that IS registered returns True."""
    wf = WorkflowDefinition(
        name="my_plugin",
        stages=[{"name": "step1", "current_stage": "step1"}],
    )
    register_workflow("my_plugin", wf)

    result = uses_multi_stage_delivery("my_plugin")

    assert result is True


def test_uses_multi_stage_delivery_plugin_workflow_string_returns_false() -> None:
    """A raw plugin workflow string that is NOT registered returns False."""
    result = uses_multi_stage_delivery("unknown_plugin")

    assert result is False


def test_uses_multi_stage_delivery_non_string_non_enum_returns_false() -> None:
    """Passing a non-str, non-WorkflowName value returns False without error."""
    result = uses_multi_stage_delivery(42)  # type: ignore[arg-type]

    assert result is False


# ── is_user_facing_workflow ─────────────────────────────────────────────


def test_is_user_facing_workflow_known_returns_true() -> None:
    """A WorkflowName in USER_FACING_WORKFLOWS returns True."""
    result = is_user_facing_workflow(WorkflowName.GENERATE_CODE)

    assert result is True


def test_is_user_facing_workflow_non_facing_returns_false() -> None:
    """A WorkflowName not in USER_FACING_WORKFLOWS returns False."""
    result = is_user_facing_workflow(WorkflowName.PLANNING)

    assert result is False


def test_is_user_facing_workflow_unresolvable_returns_false() -> None:
    """An unresolvable string returns False."""
    result = is_user_facing_workflow("nonexistent_workflow")

    assert result is False


# ── workflow_prompt_file ────────────────────────────────────────────────


def test_workflow_prompt_file_known_returns_correct_file() -> None:
    """A known WorkflowName returns its associated prompt file."""
    result = workflow_prompt_file(WorkflowName.GENERATE_CODE)

    assert result == "code_generation.md"


def test_workflow_prompt_file_unresolvable_returns_base() -> None:
    """An unresolvable workflow falls back to base.md."""
    result = workflow_prompt_file("nonexistent")

    assert result == "base.md"


def test_workflow_prompt_file_workflowname_with_no_prompt_returns_base() -> None:
    """A known WorkflowName that has no prompt file mapping returns base.md."""
    from mergemate.domain.shared.enums import PROMPT_FILE_BY_WORKFLOW

    unmapped = next(
        wf
        for wf in WorkflowName
        if wf not in PROMPT_FILE_BY_WORKFLOW
    )
    result = workflow_prompt_file(unmapped)

    assert result == "base.md"