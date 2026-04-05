from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from mergemate.application.services.planning_service import PlanningService


class GatewayStub:
    def __init__(self) -> None:
        self.calls = []

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((agent_name, system_prompt, user_prompt))
        return f"response-from-{agent_name}"


@dataclass(slots=True)
class SettingsStub:
    agents: dict[str, object] = field(
        default_factory=lambda: {
            "planner": SimpleNamespace(workflow="planning"),
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
    service = PlanningService(gateway, SettingsStub())

    result = await service.draft_plan("build feature")

    assert result == "response-from-planner"
    assert gateway.calls[0][0] == "planner"


@pytest.mark.asyncio
async def test_draft_plan_includes_prior_feedback_when_present() -> None:
    gateway = GatewayStub()
    service = PlanningService(gateway, SettingsStub())

    result = await service.draft_plan("build login", prior_feedback="add audit logging")

    assert result == "response-from-planner"
    assert gateway.calls[0][0] == "planner"
    assert "User request:\nbuild login" in gateway.calls[0][2]
    assert "Incorporate this feedback or reviewer concern:\nadd audit logging" in gateway.calls[0][2]


@pytest.mark.asyncio
async def test_revise_plan_merges_feedback_before_redrafting() -> None:
    gateway = GatewayStub()
    service = PlanningService(gateway, SettingsStub())

    updated_prompt, plan_text = await service.revise_plan("build feature", "cover edge cases")

    assert updated_prompt == "build feature\n\nAdditional user feedback:\ncover edge cases"
    assert plan_text == "response-from-planner"
    assert "User request:\nbuild feature\n\nAdditional user feedback:\ncover edge cases" in gateway.calls[0][2]