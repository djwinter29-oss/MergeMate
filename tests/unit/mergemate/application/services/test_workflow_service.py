from dataclasses import dataclass, field

import pytest

from mergemate.application.services.workflow_service import WorkflowService


class GatewayStub:
    def __init__(self) -> None:
        self.calls = []

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((agent_name, system_prompt, user_prompt))
        return f"response-from-{agent_name}"


@dataclass(slots=True)
class WorkflowControlStub:
    planner_agent_name: str = "planner"
    architect_agent_name: str = "architect"
    coder_agent_name: str = "coder"
    tester_agent_name: str = "tester"
    reviewer_agent_name: str = "reviewer"


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)


@pytest.mark.asyncio
async def test_draft_plan_uses_planner_agent() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.draft_plan("build feature")

    assert result == "response-from-planner"
    assert gateway.calls[0][0] == "planner"


@pytest.mark.asyncio
async def test_create_design_uses_architect_agent() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.create_design("approved plan", "repo context")

    assert result == "response-from-architect"
    assert gateway.calls[0][0] == "architect"