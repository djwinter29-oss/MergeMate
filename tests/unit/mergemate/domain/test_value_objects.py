"""Tests for shared domain value objects — enums and helpers."""

import pytest

from mergemate.domain.shared import (
    RunJobStatus,
    RunJobType,
    RunStage,
    RunStatus,
    tool_stage,
)
from mergemate.domain.shared.enums import (
    MULTI_STAGE_WORKFLOWS,
    PROMPT_FILE_BY_WORKFLOW,
    USER_FACING_WORKFLOWS,
    WorkflowName,
)
from mergemate.domain.policies import (
    is_user_facing_workflow,
    resolve_workflow_name,
    uses_multi_stage_delivery,
    workflow_prompt_file,
)


# ── RunStatus enum ────────────────────────────────────────────────────────


def test_run_status_values() -> None:
    """RunStatus enum values match expected strings."""
    assert RunStatus.AWAITING_CONFIRMATION.value == "awaiting_confirmation"
    assert RunStatus.QUEUED.value == "queued"
    assert RunStatus.RUNNING.value == "running"
    assert RunStatus.WAITING_TOOL.value == "waiting_tool"
    assert RunStatus.COMPLETED.value == "completed"
    assert RunStatus.FAILED.value == "failed"
    assert RunStatus.CANCELLED.value == "cancelled"


def test_run_status_terminal_statuses() -> None:
    """terminal_statuses are COMPLETED, FAILED, CANCELLED."""
    terminal = RunStatus.terminal_statuses()
    assert terminal == frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})


def test_run_status_skip_process_statuses() -> None:
    """skip_process_statuses includes terminal + running + waiting_tool."""
    skip = RunStatus.skip_process_statuses()
    expected = frozenset(
        {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.RUNNING,
            RunStatus.WAITING_TOOL,
        }
    )
    assert skip == expected


def test_run_status_not_terminal() -> None:
    """Non-terminal statuses are not in terminal_statuses."""
    terminal = RunStatus.terminal_statuses()
    assert RunStatus.QUEUED not in terminal
    assert RunStatus.RUNNING not in terminal


def test_run_status_is_str_enum() -> None:
    """RunStatus can be compared to plain strings."""
    assert RunStatus("completed") == RunStatus.COMPLETED
    assert isinstance(RunStatus.COMPLETED, str)


# ── RunStage enum ─────────────────────────────────────────────────────────


def test_run_stage_values() -> None:
    """RunStage values match expected stage names."""
    assert RunStage.PLANNING.value == "planning"
    assert RunStage.AWAITING_USER_CONFIRMATION.value == "awaiting_user_confirmation"
    assert RunStage.QUEUED_FOR_EXECUTION.value == "queued_for_execution"
    assert RunStage.RETRIEVE_CONTEXT.value == "retrieve_context"
    assert RunStage.EXECUTION.value == "execution"
    assert RunStage.DESIGN.value == "design"
    assert RunStage.IMPLEMENTATION.value == "implementation"
    assert RunStage.TESTING.value == "testing"
    assert RunStage.REVIEW.value == "review"
    assert RunStage.INTERNAL_REPLANNING.value == "internal_replanning"
    assert RunStage.COMPLETED.value == "completed"


def test_run_stage_all_members() -> None:
    """RunStage covers all 11 expected stages."""
    expected_names = {
        "PLANNING",
        "AWAITING_USER_CONFIRMATION",
        "QUEUED_FOR_EXECUTION",
        "RETRIEVE_CONTEXT",
        "EXECUTION",
        "DESIGN",
        "IMPLEMENTATION",
        "TESTING",
        "REVIEW",
        "INTERNAL_REPLANNING",
        "COMPLETED",
    }
    assert {m.name for m in RunStage} == expected_names


# ── RunStatus enum completeness ──────────────────────────────────────────


def test_run_status_all_members() -> None:
    """RunStatus covers all 7 expected statuses."""
    expected_names = {
        "AWAITING_CONFIRMATION",
        "QUEUED",
        "RUNNING",
        "WAITING_TOOL",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    assert {m.name for m in RunStatus} == expected_names


def test_run_status_equality_via_value() -> None:
    """RunStatus members compare equal by value."""
    from_str = RunStatus("completed")
    assert from_str == RunStatus.COMPLETED


# ── RunJobStatus enum ────────────────────────────────────────────────────


def test_run_job_status_values() -> None:
    """RunJobStatus values match expected job lifecycle strings."""
    assert RunJobStatus.QUEUED.value == "queued"
    assert RunJobStatus.RUNNING.value == "running"
    assert RunJobStatus.COMPLETED.value == "completed"
    assert RunJobStatus.FAILED.value == "failed"


def test_run_job_status_all_members() -> None:
    """RunJobStatus covers 4 lifecycle statuses."""
    assert set(RunJobStatus) == {
        RunJobStatus.QUEUED,
        RunJobStatus.RUNNING,
        RunJobStatus.COMPLETED,
        RunJobStatus.FAILED,
    }


# ── RunJobType enum ──────────────────────────────────────────────────────


def test_run_job_type_values() -> None:
    """RunJobType values match expected type strings."""
    assert RunJobType.PLAN_RUN.value == "plan_run"
    assert RunJobType.EXECUTE_RUN.value == "execute_run"


def test_run_job_type_all_members() -> None:
    """RunJobType covers 2 job types."""
    assert set(RunJobType) == {RunJobType.PLAN_RUN, RunJobType.EXECUTE_RUN}


# ── tool_stage helper ────────────────────────────────────────────────────


def test_tool_stage_simple() -> None:
    """tool_stage prefix formats correctly."""
    assert tool_stage("git_repository") == "tool:git_repository"
    assert tool_stage("code_formatter") == "tool:code_formatter"


def test_tool_stage_special_chars() -> None:
    """tool_stage handles names with special characters."""
    assert tool_stage("my-tool") == "tool:my-tool"
    assert tool_stage("tool_123") == "tool:tool_123"


# ── WorkflowName enum ────────────────────────────────────────────────────


def test_workflow_name_all_members() -> None:
    """WorkflowName covers all 8 expected workflows."""
    expected_names = {
        "PLANNING",
        "DESIGN",
        "GENERATE_CODE",
        "DEBUG_CODE",
        "EXPLAIN_CODE",
        "TESTING",
        "REVIEW",
        "LEARNING",
    }
    assert {m.name for m in WorkflowName} == expected_names


def test_workflow_name_values() -> None:
    """WorkflowName enum values match expected strings."""
    assert WorkflowName.PLANNING.value == "planning"
    assert WorkflowName.DESIGN.value == "design"
    assert WorkflowName.GENERATE_CODE.value == "generate_code"
    assert WorkflowName.DEBUG_CODE.value == "debug_code"
    assert WorkflowName.EXPLAIN_CODE.value == "explain_code"
    assert WorkflowName.TESTING.value == "testing"
    assert WorkflowName.REVIEW.value == "review"
    assert WorkflowName.LEARNING.value == "learning"


def test_workflow_name_is_str_enum() -> None:
    """WorkflowName can be compared to plain strings."""
    assert WorkflowName("generate_code") == WorkflowName.GENERATE_CODE
    assert isinstance(WorkflowName.GENERATE_CODE, str)


# ── USER_FACING_WORKFLOWS ────────────────────────────────────────────────


def test_user_facing_workflows_contents() -> None:
    """USER_FACING_WORKFLOWS is a frozenset with code-gen workflows."""
    assert isinstance(USER_FACING_WORKFLOWS, frozenset)
    assert WorkflowName.GENERATE_CODE in USER_FACING_WORKFLOWS
    assert WorkflowName.DEBUG_CODE in USER_FACING_WORKFLOWS
    assert WorkflowName.EXPLAIN_CODE in USER_FACING_WORKFLOWS
    assert WorkflowName.PLANNING not in USER_FACING_WORKFLOWS
    assert WorkflowName.DESIGN not in USER_FACING_WORKFLOWS
    assert WorkflowName.TESTING not in USER_FACING_WORKFLOWS
    assert WorkflowName.REVIEW not in USER_FACING_WORKFLOWS
    assert WorkflowName.LEARNING not in USER_FACING_WORKFLOWS


# ── MULTI_STAGE_WORKFLOWS ────────────────────────────────────────────────


def test_multi_stage_workflows_contents() -> None:
    """MULTI_STAGE_WORKFLOWS is a frozenset with GENERATE_CODE."""
    assert isinstance(MULTI_STAGE_WORKFLOWS, frozenset)
    assert WorkflowName.GENERATE_CODE in MULTI_STAGE_WORKFLOWS
    assert WorkflowName.LEARNING not in MULTI_STAGE_WORKFLOWS
    assert WorkflowName.PLANNING not in MULTI_STAGE_WORKFLOWS


# ── PROMPT_FILE_BY_WORKFLOW ──────────────────────────────────────────────


def test_prompt_file_by_workflow() -> None:
    """PROMPT_FILE_BY_WORKFLOW maps each user-facing workflow to its prompt file."""
    assert PROMPT_FILE_BY_WORKFLOW[WorkflowName.GENERATE_CODE] == "code_generation.md"
    assert PROMPT_FILE_BY_WORKFLOW[WorkflowName.DEBUG_CODE] == "debugging.md"
    assert PROMPT_FILE_BY_WORKFLOW[WorkflowName.EXPLAIN_CODE] == "explanation.md"
    assert len(PROMPT_FILE_BY_WORKFLOW) == 3


# ── resolve_workflow_name ────────────────────────────────────────────────


def test_resolve_workflow_name_from_string():
    """resolve_workflow_name converts valid string to WorkflowName."""
    assert resolve_workflow_name("generate_code") == WorkflowName.GENERATE_CODE
    assert resolve_workflow_name("planning") == WorkflowName.PLANNING


def test_resolve_workflow_name_from_enum():
    """resolve_workflow_name returns the same WorkflowName when passed an enum."""
    assert resolve_workflow_name(WorkflowName.DEBUG_CODE) == WorkflowName.DEBUG_CODE


def test_resolve_workflow_name_unknown():
    """resolve_workflow_name returns None for invalid input."""
    assert resolve_workflow_name("nonexistent") is None
    assert resolve_workflow_name("") is None


# ── uses_multi_stage_delivery ────────────────────────────────────────────


def test_uses_multi_stage_delivery_returns_true() -> None:
    """uses_multi_stage_delivery returns True for GENERATE_CODE."""
    assert uses_multi_stage_delivery("generate_code") is True
    assert uses_multi_stage_delivery(WorkflowName.GENERATE_CODE) is True


def test_uses_multi_stage_delivery_returns_false() -> None:
    """uses_multi_stage_delivery returns False for non-multi-stage workflows."""
    assert uses_multi_stage_delivery("planning") is False
    assert uses_multi_stage_delivery("debug_code") is False
    assert uses_multi_stage_delivery("learning") is False
    assert uses_multi_stage_delivery("testing") is False


def test_uses_multi_stage_delivery_unknown() -> None:
    """uses_multi_stage_delivery returns False for unknown workflow."""
    assert uses_multi_stage_delivery("unknown") is False


# ── is_user_facing_workflow ──────────────────────────────────────────────


def test_is_user_facing_workflow_true() -> None:
    """is_user_facing_workflow returns True for user-facing workflows."""
    assert is_user_facing_workflow("generate_code") is True
    assert is_user_facing_workflow("debug_code") is True
    assert is_user_facing_workflow("explain_code") is True
    assert is_user_facing_workflow(WorkflowName.GENERATE_CODE) is True


def test_is_user_facing_workflow_false() -> None:
    """is_user_facing_workflow returns False for internal workflows."""
    assert is_user_facing_workflow("planning") is False
    assert is_user_facing_workflow("design") is False
    assert is_user_facing_workflow("testing") is False
    assert is_user_facing_workflow("review") is False
    assert is_user_facing_workflow("learning") is False
    assert is_user_facing_workflow(WorkflowName.PLANNING) is False


def test_is_user_facing_workflow_unknown() -> None:
    """is_user_facing_workflow returns False for unknown workflow."""
    assert is_user_facing_workflow("unknown_workflow") is False


# ── workflow_prompt_file ──────────────────────────────────────────────────


def test_workflow_prompt_file_known() -> None:
    """workflow_prompt_file returns the correct prompt file for known workflows."""
    assert workflow_prompt_file("generate_code") == "code_generation.md"
    assert workflow_prompt_file("debug_code") == "debugging.md"
    assert workflow_prompt_file("explain_code") == "explanation.md"


def test_workflow_prompt_file_internal() -> None:
    """workflow_prompt_file returns 'base.md' for internal workflows."""
    assert workflow_prompt_file("planning") == "base.md"
    assert workflow_prompt_file("design") == "base.md"
    assert workflow_prompt_file("testing") == "base.md"
    assert workflow_prompt_file("review") == "base.md"


def test_workflow_prompt_file_unknown() -> None:
    """workflow_prompt_file returns 'base.md' for unknown workflows."""
    assert workflow_prompt_file("unknown_workflow") == "base.md"
    assert workflow_prompt_file("nonexistent") == "base.md"


def test_workflow_prompt_file_with_enum() -> None:
    """workflow_prompt_file works with WorkflowName enum value."""
    assert workflow_prompt_file(WorkflowName.GENERATE_CODE) == "code_generation.md"


# ── Edge cases ───────────────────────────────────────────────────────────


def test_empty_string_workflow() -> None:
    """resolve_workflow_name('') returns None (not WorkflowName)."""
    assert resolve_workflow_name("") is None


def test_case_sensitivity() -> None:
    """WorkflowName is an enum, so string comparison is exact (case-sensitive)."""
    # 'GENERATE_CODE' (uppercase) is not a valid enum value; only lower case works
    with pytest.raises(ValueError):
        WorkflowName("GENERATE_CODE")
