"""Tests for shared enums — covering all branch paths."""

from mergemate.domain.shared.enums import (
    WorkflowName,
    PROMPT_FILE_BY_WORKFLOW,
)
from mergemate.domain.policies import (
    resolve_workflow_name,
    uses_multi_stage_delivery,
    is_user_facing_workflow,
    workflow_prompt_file,
)


class TestResolveWorkflowName:
    def test_returns_workflow_name_when_already_is_one(self) -> None:
        """Line 35-36: isinstance check returns workflow directly."""
        result = resolve_workflow_name(WorkflowName.GENERATE_CODE)
        assert result is WorkflowName.GENERATE_CODE

    def test_returns_workflow_name_from_valid_string(self) -> None:
        """Line 38: WorkflowName(string) succeeds."""
        result = resolve_workflow_name("generate_code")
        assert result == WorkflowName.GENERATE_CODE

    def test_returns_none_for_unknown_string(self) -> None:
        """Line 39-40: ValueError caught, returns None."""
        result = resolve_workflow_name("unknown_workflow")
        assert result is None


class TestUsesMultiStageDelivery:
    def test_returns_true_for_multi_stage_workflow(self) -> None:
        """Line 44-45: workflow is in MULTI_STAGE_WORKFLOWS."""
        assert uses_multi_stage_delivery("generate_code") is True

    def test_returns_false_for_direct_workflow(self) -> None:
        """Line 44-45: workflow not in MULTI_STAGE_WORKFLOWS."""
        assert uses_multi_stage_delivery("debug_code") is False

    def test_returns_false_for_unknown_workflow(self) -> None:
        """Line 44-45: resolve returns None, not in frozenset."""
        assert uses_multi_stage_delivery("unknown_workflow") is False


class TestIsUserFacingWorkflow:
    def test_returns_true_for_user_facing_workflow(self) -> None:
        """Line 49-50: workflow is in USER_FACING_WORKFLOWS."""
        assert is_user_facing_workflow("generate_code") is True

    def test_returns_false_for_internal_workflow(self) -> None:
        """Line 49-50: workflow not in USER_FACING_WORKFLOWS."""
        assert is_user_facing_workflow("planning") is False

    def test_returns_false_for_unknown_workflow(self) -> None:
        """Line 49-50: resolve returns None."""
        assert is_user_facing_workflow("bogus") is False


class TestWorkflowPromptFile:
    def test_returns_file_for_known_workflow(self) -> None:
        """Line 57: workflow found in PROMPT_FILE_BY_WORKFLOW."""
        result = workflow_prompt_file("generate_code")
        assert result == PROMPT_FILE_BY_WORKFLOW[WorkflowName.GENERATE_CODE]

    def test_returns_base_for_workflow_with_no_dedicated_prompt(self) -> None:
        """Line 57: .get returns 'base.md' for workflows not in dict."""
        result = workflow_prompt_file("testing")
        assert result == "base.md"

    def test_returns_base_when_resolve_returns_none(self) -> None:
        """Line 54-56: resolve_workflow_name returns None -> returns 'base.md'."""
        result = workflow_prompt_file("nonexistent_workflow")
        assert result == "base.md"

    def test_accepts_workflowname_input(self) -> None:
        """Line 54: accepts WorkflowName directly."""
        result = workflow_prompt_file(WorkflowName.DESIGN)
        assert result == "base.md"
