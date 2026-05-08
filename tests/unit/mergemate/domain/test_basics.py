from datetime import UTC, datetime

from mergemate.domain.conversations.entities import Conversation
from mergemate.domain.conversations.repository import ConversationRepository
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.value_objects import RunStage, RunStatus, tool_stage
from mergemate.domain.shared.enums import (
    WorkflowName,
    is_user_facing_workflow,
    resolve_workflow_name,
    workflow_prompt_file,
)
from mergemate.domain.tools.entities import ToolDefinition
from mergemate.infrastructure.llm.base import LLMClient


def test_domain_dataclasses_and_enums_are_constructible() -> None:
    now = datetime.now(UTC)
    conversation = Conversation(chat_id=7, messages=["hello"])
    tool = ToolDefinition(name="formatter", description="formats code")
    run = AgentRun(
        run_id="run-1",
        chat_id=7,
        user_id=9,
        agent_name="coder",
        workflow=WorkflowName.GENERATE_CODE,
        status=RunStatus.QUEUED,
        current_stage=RunStage.QUEUED_FOR_EXECUTION,
        prompt="build feature",
        estimate_seconds=10,
        plan_text=None,
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )

    assert conversation.messages == ["hello"]
    assert tool.description == "formats code"
    assert run.status == RunStatus.QUEUED
    assert tool_stage("git_repository") == "tool:git_repository"
    assert WorkflowName.DEBUG_CODE == "debug_code"


def test_is_user_facing_workflow() -> None:
    assert is_user_facing_workflow("generate_code") is True
    assert is_user_facing_workflow("debug_code") is True
    assert is_user_facing_workflow("explain_code") is True
    assert is_user_facing_workflow("planning") is False
    assert is_user_facing_workflow("design") is False
    assert is_user_facing_workflow("testing") is False
    assert is_user_facing_workflow("review") is False
    assert is_user_facing_workflow(WorkflowName.GENERATE_CODE) is True
    assert is_user_facing_workflow(WorkflowName.PLANNING) is False
    assert is_user_facing_workflow("unknown_workflow") is False


def test_workflow_prompt_file() -> None:
    assert workflow_prompt_file("generate_code") == "code_generation.md"
    assert workflow_prompt_file("debug_code") == "debugging.md"
    assert workflow_prompt_file("explain_code") == "explanation.md"
    assert workflow_prompt_file("planning") == "base.md"
    assert workflow_prompt_file("design") == "base.md"
    assert workflow_prompt_file("testing") == "base.md"
    assert workflow_prompt_file("review") == "base.md"
    assert workflow_prompt_file(WorkflowName.GENERATE_CODE) == "code_generation.md"
    assert workflow_prompt_file("unknown_workflow") == "base.md"


def test_resolve_workflow_name() -> None:
    assert resolve_workflow_name("generate_code") == WorkflowName.GENERATE_CODE
    assert resolve_workflow_name("planning") == WorkflowName.PLANNING
    assert resolve_workflow_name(WorkflowName.DEBUG_CODE) == WorkflowName.DEBUG_CODE
    assert resolve_workflow_name("nonexistent") is None


def test_edge_cases_are_importable() -> None:
    assert ConversationRepository is not None
    assert LLMClient is not None