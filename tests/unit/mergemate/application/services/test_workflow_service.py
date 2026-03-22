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


@pytest.mark.asyncio
async def test_draft_plan_includes_prior_feedback_when_present() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.draft_plan("build login", prior_feedback="add audit logging")

    assert result == "response-from-planner"
    assert gateway.calls[0][0] == "planner"
    assert "User request:\nbuild login" in gateway.calls[0][2]
    assert "Incorporate this feedback or reviewer concern:\nadd audit logging" in gateway.calls[0][2]


@pytest.mark.asyncio
async def test_generate_code_uses_coder_agent() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.generate_code("plan", "design", "context")

    assert result == "response-from-coder"
    assert gateway.calls[0][0] == "coder"


@pytest.mark.asyncio
async def test_generate_tests_uses_tester_agent() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.generate_tests("plan", "design", "implementation")

    assert result == "response-from-tester"
    assert gateway.calls[0][0] == "tester"


@pytest.mark.asyncio
async def test_review_uses_reviewer_agent() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.review("plan", "design", "implementation", "tests")

    assert result == "response-from-reviewer"
    assert gateway.calls[0][0] == "reviewer"


@pytest.mark.asyncio
async def test_execute_direct_uses_requested_agent() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.execute_direct("debugger", "system", "user")

    assert result == "response-from-debugger"
    assert gateway.calls[0] == ("debugger", "system", "user")


def test_uses_multi_stage_delivery_is_explicit() -> None:
    assert WorkflowService.uses_multi_stage_delivery("generate_code") is True
    assert WorkflowService.uses_multi_stage_delivery("debug_code") is False
    assert WorkflowService.uses_multi_stage_delivery("explain_code") is False


def test_has_high_concerns_reads_first_line_only() -> None:
    assert WorkflowService.has_high_concerns("HIGH_CONCERNS: yes\nissue") is True
    assert WorkflowService.has_high_concerns("HIGH_CONCERNS: no\nissue") is False