from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from mergemate.application.execution_plan import DirectExecutionPlan, MultiStageExecutionPlan
from mergemate.application.services.workflow_service import WorkflowService


class GatewayStub:
    def __init__(self) -> None:
        self.calls = []

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((agent_name, system_prompt, user_prompt))
        return f"response-from-{agent_name}"


@dataclass(slots=True)
class WorkflowControlStub:
    max_review_iterations: int = 5


@dataclass(slots=True)
class SettingsStub:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)
    agents: dict[str, object] = field(
        default_factory=lambda: {
            "planner": SimpleNamespace(workflow="planning"),
            "architect": SimpleNamespace(workflow="design"),
            "coder": SimpleNamespace(workflow="generate_code"),
            "tester": SimpleNamespace(workflow="testing"),
            "reviewer": SimpleNamespace(workflow="review"),
        }
    )

    def resolve_agent_name_for_workflow(
        self,
        workflow: str,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        if preferred_agent_name is not None:
            agent = self.agents.get(preferred_agent_name)
            if agent is not None and agent.workflow == workflow:
                return preferred_agent_name
        for agent_name, agent in self.agents.items():
            if agent.workflow == workflow:
                return agent_name
        raise ValueError(workflow)


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


def test_build_execution_plan_returns_expected_plan_types() -> None:
    service = WorkflowService(GatewayStub(), SettingsStub())

    assert isinstance(service.build_execution_plan("generate_code", agent_name="coder"), MultiStageExecutionPlan)
    assert isinstance(service.build_execution_plan("debug_code", agent_name="debugger"), DirectExecutionPlan)