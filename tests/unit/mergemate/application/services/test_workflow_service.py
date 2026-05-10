from dataclasses import dataclass, field
from types import SimpleNamespace

import asyncio
import pytest

from mergemate.application.execution_plan import DirectExecutionPlan, MultiStageExecutionPlan
from mergemate.application.services.workflow_service import WorkflowService
from mergemate.domain.shared import WorkflowName
from mergemate.domain.policies import uses_multi_stage_delivery
from mergemate.domain.shared.exceptions import ParallelWorkerError, StageExecutionError


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
async def test_create_design_uses_architect_agent() -> None:
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStub())

    result = await service.create_design("approved plan", "repo context")

    assert result == "response-from-architect"
    assert gateway.calls[0][0] == "architect"


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
    """Policy returns True only for workflows registered as multi-stage."""
    # generate_code is registered as multi-stage in the built-in workflow registry
    assert uses_multi_stage_delivery("generate_code") is True
    assert uses_multi_stage_delivery("debug_code") is False
    assert uses_multi_stage_delivery("explain_code") is False
    assert uses_multi_stage_delivery(WorkflowName.GENERATE_CODE) is True


def test_has_high_concerns_reads_first_line_only() -> None:
    assert WorkflowService.has_high_concerns("HIGH_CONCERNS: yes\nissue") is True
    assert WorkflowService.has_high_concerns("HIGH_CONCERNS: no\nissue") is False


def test_has_high_concerns_returns_false_for_blank_output() -> None:
    assert WorkflowService.has_high_concerns("") is False
    assert WorkflowService.has_high_concerns("   \n\n") is False


def test_build_execution_plan_returns_expected_plan_types() -> None:
    service = WorkflowService(GatewayStub(), SettingsStub())

    assert isinstance(service.build_execution_plan("generate_code", agent_name="coder"), MultiStageExecutionPlan)
    assert isinstance(service.build_execution_plan("debug_code", agent_name="debugger"), DirectExecutionPlan)


def test_build_execution_plan_accepts_workflow_enum() -> None:
    service = WorkflowService(GatewayStub(), SettingsStub())

    assert isinstance(
        service.build_execution_plan(WorkflowName.DEBUG_CODE, agent_name="debugger"),
        DirectExecutionPlan,
    )


def test_execution_plans_report_tool_context_requirement_from_shared_base() -> None:
    from mergemate.domain.workflows.stage import get_workflow_definitions

    direct_plan = DirectExecutionPlan(agent_name="debugger")
    multi_stage_plan = MultiStageExecutionPlan(
        agent_name="coder",
        max_iterations=2,
        workflow_definition=get_workflow_definitions()[WorkflowName.GENERATE_CODE],
    )

    assert direct_plan.requires_tool_context is True
    assert multi_stage_plan.requires_tool_context is True


def test_build_execution_plan_rejects_non_positive_review_iterations() -> None:
    """MultiStageExecutionPlan constructors validate max_iterations >= 1."""
    from mergemate.application.execution_plan import MultiStageExecutionPlan
    with pytest.raises(StageExecutionError, match="max_iterations must be at least 1"):
        MultiStageExecutionPlan(
            agent_name="coder",
            max_iterations=0,
        )


# ── Parallel execution tests ──────────────────────────────────────────────


_dc = dataclass


class DelayedGatewayStub:
    """Gateway that records calls and introduces a controlled delay."""

    def __init__(self, delay: float = 0.1) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._delay = delay

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        await asyncio.sleep(self._delay)
        self.calls.append((agent_name, system_prompt, user_prompt))
        return f"response-from-{agent_name}"


class FailingWorkerGatewayStub:
    """Gateway where specific agents fail, for testing error handling."""

    def __init__(self, failing_agents: set[str]) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._failing = failing_agents

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((agent_name, system_prompt, user_prompt))
        if agent_name in self._failing:
            raise RuntimeError(f"Worker {agent_name} failed")
        return f"response-from-{agent_name}"


@_dc(slots=True)
class ParallelRoleStub:
    parallel_mode: str = "parallel"
    combine_strategy: str = "sectioned"
    workers: list[object] = field(
        default_factory=lambda: [
            SimpleNamespace(name="worker-alpha"),
            SimpleNamespace(name="worker-beta"),
        ]
    )


@_dc(slots=True)
class FirstSuccessRoleStub:
    parallel_mode: str = "parallel"
    combine_strategy: str = "first_success"
    workers: list[object] = field(
        default_factory=lambda: [
            SimpleNamespace(name="worker-alpha"),
            SimpleNamespace(name="worker-beta"),
        ]
    )


@_dc(slots=True)
class SettingsStubWithParallel:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)
    agents: dict[str, object] = field(
        default_factory=lambda: {
            "coder": SimpleNamespace(workflow="generate_code"),
            "worker-alpha": SimpleNamespace(workflow="generate_code"),
            "worker-beta": SimpleNamespace(workflow="generate_code"),
        }
    )
    roles: dict[str, object] = field(
        default_factory=lambda: {
            "coder": ParallelRoleStub(),
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


@_dc(slots=True)
class SettingsStubWithParallelFirstSuccess:
    workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)
    agents: dict[str, object] = field(
        default_factory=lambda: {
            "coder": SimpleNamespace(workflow="generate_code"),
            "worker-alpha": SimpleNamespace(workflow="generate_code"),
            "worker-beta": SimpleNamespace(workflow="generate_code"),
        }
    )
    roles: dict[str, object] = field(
        default_factory=lambda: {
            "coder": FirstSuccessRoleStub(),
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
async def test_parallel_mode_calls_all_workers() -> None:
    """With parallel_mode=parallel and 2 workers, generate_code should call both."""
    gateway = DelayedGatewayStub()
    service = WorkflowService(gateway, SettingsStubWithParallel())

    await service.generate_code("plan", "design", "context")

    # Both workers should have been called
    worker_names = {c[0] for c in gateway.calls}
    assert worker_names == {"worker-alpha", "worker-beta"}, f"Got agents: {worker_names}"


@pytest.mark.asyncio
async def test_parallel_mode_runs_concurrently() -> None:
    """Workers should run concurrently (total time < sum of individual delays)."""
    import time

    gateway = DelayedGatewayStub(delay=0.15)
    service = WorkflowService(gateway, SettingsStubWithParallel())

    start = time.monotonic()
    await service.generate_code("plan", "design", "context")
    elapsed = time.monotonic() - start

    # 2 workers at 0.15s each: concurrent should be ~0.15-0.25s, not 0.30+
    assert elapsed < 0.30, f"Parallel execution took {elapsed:.3f}s (expected <0.30s)"


@pytest.mark.asyncio
async def test_parallel_mode_sectioned_combines_results() -> None:
    """With sectioned combine strategy, all results appear in output."""
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStubWithParallel())

    result = await service.generate_code("plan", "design", "context")

    assert "worker-alpha" in result
    assert "worker-beta" in result
    assert "response-from-worker-alpha" in result
    assert "response-from-worker-beta" in result


@pytest.mark.asyncio
async def test_parallel_mode_first_success_returns_only_one() -> None:
    """With first_success strategy, only the first non-error result is returned."""
    gateway = GatewayStub()
    service = WorkflowService(gateway, SettingsStubWithParallelFirstSuccess())

    result = await service.generate_code("plan", "design", "context")

    # The result should be a bare response (not sectioned with ## headers)
    assert not result.startswith("## "), f"Got sectioned output: {result[:100]}"
    assert result == "response-from-worker-alpha"


@pytest.mark.asyncio
async def test_parallel_mode_raises_when_all_workers_fail() -> None:
    """If all workers fail, a RuntimeError should be raised."""
    gateway = FailingWorkerGatewayStub(failing_agents={"worker-alpha", "worker-beta"})
    service = WorkflowService(gateway, SettingsStubWithParallel())

    with pytest.raises(ParallelWorkerError, match="All parallel workers failed"):
        await service.generate_code("plan", "design", "context")


@pytest.mark.asyncio
async def test_parallel_mode_reports_failed_workers_in_sectioned_output() -> None:
    """With sectioned strategy, failed workers show (FAILED) in output."""
    gateway = FailingWorkerGatewayStub(failing_agents={"worker-beta"})
    service = WorkflowService(gateway, SettingsStubWithParallel())

    result = await service.generate_code("plan", "design", "context")

    assert "worker-alpha" in result
    assert "response-from-worker-alpha" in result
    assert "worker-beta (FAILED)" in result


@pytest.mark.asyncio
async def test_parallel_mode_skips_single_worker() -> None:
    """With only 1 worker, parallel mode should fall through to normal path."""
    gateway = GatewayStub()

    @_dc(slots=True)
    class SingleWorkerRoleStub:
        parallel_mode: str = "parallel"
        combine_strategy: str = "sectioned"
        workers: list[object] = field(
            default_factory=lambda: [SimpleNamespace(name="worker-alpha")]
        )

    @_dc(slots=True)
    class SingleWorkerSettings:
        workflow_control: WorkflowControlStub = field(default_factory=WorkflowControlStub)
        agents: dict[str, object] = field(
            default_factory=lambda: {
                "coder": SimpleNamespace(workflow="generate_code"),
            }
        )
        roles: dict[str, object] = field(
            default_factory=lambda: {"coder": SingleWorkerRoleStub()}
        )

        def resolve_agent_name_for_workflow(self, workflow: str, *, preferred_agent_name: str | None = None) -> str:
            return "coder"

    service = WorkflowService(gateway, SingleWorkerSettings())
    result = await service.generate_code("plan", "design", "context")

    assert result == "response-from-coder"
    assert len(gateway.calls) == 1