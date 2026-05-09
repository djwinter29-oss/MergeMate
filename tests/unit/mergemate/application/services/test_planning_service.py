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


@pytest.mark.asyncio
async def test_extract_tasks_parses_breakdown_section() -> None:
    """extract_tasks should parse well-formed task breakdown."""
    plan = """## Task Breakdown
- [ ] Design auth flow — define API endpoints (@architect)
- [ ] Implement login — build sign-in logic (@coder)
- [ ] Write unit tests — cover login edge cases (@tester)
- [ ] Review code — check auth flow and tests (@reviewer)
"""
    tasks = PlanningService.extract_tasks(plan)
    assert len(tasks) == 4
    assert tasks[0] == {"description": "Design auth flow — define API endpoints", "owner": "architect"}
    assert tasks[1] == {"description": "Implement login — build sign-in logic", "owner": "coder"}
    assert tasks[2] == {"description": "Write unit tests — cover login edge cases", "owner": "tester"}
    assert tasks[3] == {"description": "Review code — check auth flow and tests", "owner": "reviewer"}


def test_extract_tasks_returns_empty_when_no_breakdown() -> None:
    """extract_tasks should return [] when no ## Task Breakdown section exists."""
    plan = "# Approved Plan\n1. Do something\n"
    assert PlanningService.extract_tasks(plan) == []


def test_extract_tasks_stops_at_next_section() -> None:
    """extract_tasks should stop parsing at the next heading after breakdown."""
    plan = """## Task Breakdown
- [ ] Task 1 — something (@coder)
- [ ] Task 2 — something else (@tester)
## Other Section
- [ ] Task 3 — should be ignored (@reviewer)
"""
    tasks = PlanningService.extract_tasks(plan)
    assert len(tasks) == 2


def test_extract_tasks_skips_malformed_lines() -> None:
    """extract_tasks should skip lines without the (@role) pattern."""
    plan = """## Task Breakdown
- [ ] Good task — works (@coder)
- [ ] Bad line without owner
- [ ] Another good — works (@tester)
  Some sub-text
"""
    tasks = PlanningService.extract_tasks(plan)
    assert len(tasks) == 2


def test_build_progress_summary_returns_empty_for_no_tasks() -> None:
    """build_progress_summary returns '' when task list is empty."""
    assert PlanningService.build_progress_summary([], []) == ""


def test_build_progress_summary_marks_all_done() -> None:
    """build_progress_summary marks ✅ for completed roles."""
    tasks = [
        {"description": "Design API", "owner": "architect"},
        {"description": "Implement API", "owner": "coder"},
    ]
    summary = PlanningService.build_progress_summary(tasks, ["architect", "coder"])
    assert "✅" in summary
    assert "❌" not in summary
    assert "2/2 tasks completed" in summary


def test_build_progress_summary_marks_partial_progress() -> None:
    """build_progress_summary shows ❌ for incomplete tasks."""
    tasks = [
        {"description": "Design API", "owner": "architect"},
        {"description": "Implement API", "owner": "coder"},
        {"description": "Write tests", "owner": "tester"},
    ]
    summary = PlanningService.build_progress_summary(tasks, ["architect"])
    assert "✅" in summary
    assert "❌" in summary
    assert "1/3 tasks completed" in summary