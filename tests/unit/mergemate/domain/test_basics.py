from datetime import UTC, datetime

from mergemate.application.jobs.progress import ProgressEvent
from mergemate.domain.agents.entities import AgentDefinition
from mergemate.domain.agents.policies import default_agent_name
from mergemate.domain.conversations.entities import Conversation
from mergemate.domain.conversations.repository import ConversationRepository
from mergemate.domain.runs.entities import AgentRun
from mergemate.domain.runs.repository import AgentRunRepository
from mergemate.domain.runs.value_objects import RunStatus
from mergemate.domain.shared.enums import WorkflowName
from mergemate.domain.tools.contracts import Tool
from mergemate.domain.tools.entities import ToolDefinition
from mergemate.infrastructure.llm.base import LLMClient
from mergemate.infrastructure.queue.base import QueueBackend


def test_domain_dataclasses_and_enums_are_constructible() -> None:
    now = datetime.now(UTC)
    agent = AgentDefinition(name="coder", workflow=WorkflowName.GENERATE_CODE, tools=["syntax_checker"])
    conversation = Conversation(chat_id=7, messages=["hello"])
    tool = ToolDefinition(name="formatter", description="formats code")
    progress = ProgressEvent(run_id="run-1", status="queued", estimate_seconds=10)
    run = AgentRun(
        run_id="run-1",
        chat_id=7,
        user_id=9,
        agent_name="coder",
        workflow=WorkflowName.GENERATE_CODE,
        status=RunStatus.QUEUED,
        current_stage="queued_for_execution",
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

    assert agent.name == "coder"
    assert conversation.messages == ["hello"]
    assert tool.description == "formats code"
    assert progress.estimate_seconds == 10
    assert run.status == RunStatus.QUEUED
    assert default_agent_name() == "coder"
    assert WorkflowName.DEBUG_CODE == "debug_code"


def test_protocol_modules_are_importable() -> None:
    assert ConversationRepository is not None
    assert AgentRunRepository is not None
    assert Tool is not None
    assert LLMClient is not None
    assert QueueBackend is not None