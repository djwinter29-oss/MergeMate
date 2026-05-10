"""Tests for deprecation wrapper functions in mergemate.domain.shared."""

from __future__ import annotations

import sys

import pytest

from mergemate.domain import shared as shared_module
from mergemate.domain.policies import (
    is_user_facing_workflow as policies_is_user_facing_workflow,
    resolve_workflow_name as policies_resolve_workflow_name,
    uses_multi_stage_delivery as policies_uses_multi_stage_delivery,
    workflow_prompt_file as policies_workflow_prompt_file,
)
from mergemate.domain.shared.enums import WorkflowName
from mergemate.domain.workflows.registry import _WORKFLOW_REGISTRY, register_workflow
from mergemate.domain.workflows.stage import WorkflowDefinition


@pytest.fixture(autouse=True)
def _isolate_registry() -> None:
    """Snapshot and restore the workflow registry around each test."""
    snapshot = dict(_WORKFLOW_REGISTRY)
    _WORKFLOW_REGISTRY.clear()
    yield
    _WORKFLOW_REGISTRY.clear()
    _WORKFLOW_REGISTRY.update(snapshot)


def _force_lazy_policy_import() -> None:
    """Remove the policies module so the wrapper must import it lazily."""
    sys.modules.pop("mergemate.domain.policies", None)


def test_is_user_facing_workflow_wrapper_emits_warning_and_matches_policy() -> None:
    expected = policies_is_user_facing_workflow("generate_code")
    _force_lazy_policy_import()

    with pytest.warns(DeprecationWarning, match="is_user_facing_workflow"):
        result = shared_module.is_user_facing_workflow("generate_code")

    assert result == expected


def test_resolve_workflow_name_wrapper_emits_warning_and_matches_policy() -> None:
    expected = policies_resolve_workflow_name("generate_code")
    _force_lazy_policy_import()

    with pytest.warns(DeprecationWarning, match="resolve_workflow_name"):
        result = shared_module.resolve_workflow_name("generate_code")

    assert result == expected
    assert result == WorkflowName.GENERATE_CODE


def test_uses_multi_stage_delivery_wrapper_emits_warning_and_matches_policy() -> None:
    workflow = WorkflowDefinition(
        name="wrapper_test_workflow",
        stages=[{"name": "step1", "current_stage": "step1"}],
    )
    register_workflow("wrapper_test_workflow", workflow)

    expected = policies_uses_multi_stage_delivery("wrapper_test_workflow")
    _force_lazy_policy_import()

    with pytest.warns(DeprecationWarning, match="uses_multi_stage_delivery"):
        result = shared_module.uses_multi_stage_delivery("wrapper_test_workflow")

    assert result == expected
    assert result is True


def test_workflow_prompt_file_wrapper_emits_warning_and_matches_policy() -> None:
    expected = policies_workflow_prompt_file(WorkflowName.GENERATE_CODE)
    _force_lazy_policy_import()

    with pytest.warns(DeprecationWarning, match="workflow_prompt_file"):
        result = shared_module.workflow_prompt_file(WorkflowName.GENERATE_CODE)

    assert result == expected
    assert result == "code_generation.md"
