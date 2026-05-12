"""Tests for scattered uncovered lines across multiple files.

Covers:
1. dispatcher.py line 31: ensure_queued_job returns job=None -> raises JobQueueError
2. orchestrator.py line 41: run.status != QUEUED -> returns run early
3. orchestrator.py line 52: start_decision.transitioned is False -> returns run
4. tool_service.py line 71: current_run is None -> returns early
5. tool_service.py line 96: _is_runtime_context_metadata returns False -> filtered
6. workflow_service.py line 181: error_text present in chronicle prompt
7. cancel_run.py line 29: run not found -> returns None
8. submit_prompt.py line 108: run is None -> returns None
9. submit_prompt.py line 132: approval.run is None -> raises PromptSubmissionError
10. submit_prompt.py line 204: approved_run is None -> returns None
11. config/loader.py line 19: no pyproject.toml found -> falls back to cwd
12. soul.py line 272: all_souls returns all built-in souls
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, MagicMock

import pytest

from mergemate.domain.shared import RunJobType, RunStatus
from mergemate.domain.shared.exceptions import JobQueueError
from mergemate.config import loader as config_loader
from mergemate.domain.agents import soul as soul_module
from mergemate.application.use_cases.submit_prompt import (
    SubmitPromptUseCase,
    PromptSubmissionError,
)


# ── dispatcher.py ─────────────────────────────────────────────────────


class TestDispatcher:
    def test_dispatch_raises_when_ensure_queued_job_returns_none(self) -> None:
        """Line 31: ensure_queued_job returns job=None -> JobQueueError."""
        from mergemate.application.jobs.dispatcher import RunDispatcher

        repo = Mock()
        repo.ensure_queued_job.return_value = SimpleNamespace(job=None)
        queue = Mock()

        dispatcher = RunDispatcher(repo, queue)
        with pytest.raises(JobQueueError, match="Unable to queue background job"):
            dispatcher.dispatch_run("run-1", job_type=RunJobType.EXECUTE_RUN)


# ── orchestrator.py ───────────────────────────────────────────────────


class TestOrchestrator:
    @pytest.fixture
    def deps(self):
        return SimpleNamespace(
            run_repository=Mock(),
            context_service=AsyncMock(),
            documentation_service=AsyncMock(),
            learning_service=Mock(),
            planning_service=AsyncMock(),
            prompt_service=Mock(),
            tool_service=Mock(),
            workflow_service=AsyncMock(),
            llm_gateway=AsyncMock(),
            settings=Mock(),
        )

    @pytest.mark.asyncio
    async def test_process_run_returns_early_when_not_queued(self, deps) -> None:
        """Line 41: run.status != QUEUED -> returns run early."""
        from mergemate.application.orchestrator import AgentOrchestrator

        run = SimpleNamespace(
            run_id="run-1",
            status=RunStatus.RUNNING,  # not QUEUED
            approved=True,
        )
        deps.run_repository.get.return_value = run

        orchestrator = AgentOrchestrator(deps)

        result = await orchestrator.process_run("run-1")
        assert result is run

    @pytest.mark.asyncio
    async def test_process_run_returns_early_when_transition_fails(self, deps) -> None:
        """Line 52: try_update_status fails -> returns run early."""
        from mergemate.application.orchestrator import AgentOrchestrator

        run = SimpleNamespace(
            run_id="run-2",
            status=RunStatus.QUEUED,
            approved=True,
        )
        deps.run_repository.get.return_value = run
        deps.run_repository.try_update_status.return_value = SimpleNamespace(
            run=run, transitioned=False
        )

        orchestrator = AgentOrchestrator(deps)

        result = await orchestrator.process_run("run-2")
        assert result is run
        assert deps.run_repository.try_update_status.called


# ── tool_service.py ───────────────────────────────────────────────────


class TestToolService:
    def test_transition_run_returns_when_current_run_is_none(self) -> None:
        """Line 71: current_run is None -> returns early."""
        from mergemate.application.services.tool_service import ToolService

        repo = Mock()
        repo.get.return_value = None
        settings = MagicMock()
        settings.agents = {}

        service = ToolService(
            tool_registry=MagicMock(),
            settings=settings,
            run_repository=repo,
        )

        # entering=False, current_run=None -> early return at _transition_run_for_tool
        result = service._transition_run_for_tool(
            "run-none",
            blocks_run_state=RunStatus.WAITING_TOOL.value,
            tool_name="some_tool",
            resume_stage="test",
            entering=False,
        )
        assert result is None

    def test_iter_context_filters_non_context_tools(self) -> None:
        """Line 96: _is_runtime_context_metadata returns False -> filtered out."""
        from mergemate.application.services.tool_service import ToolService

        registry = MagicMock()
        registry.list_tools.return_value = ["tool1"]
        registry.get_tool.return_value = None  # no platform metadata

        settings = MagicMock()
        settings.agents = {}

        service = ToolService(
            tool_registry=registry,
            settings=settings,
        )

        # With no tools returning metadata, the iterator should be empty
        result = list(service._iter_repository_context_metadata("linux"))
        assert result == []


# ── workflow_service.py ───────────────────────────────────────────────


class TestWorkflowService:
    @pytest.mark.asyncio
    async def test_record_lesson_includes_error_text(self) -> None:
        """Line 181: error_text present in chronicle prompt for record_lesson."""
        from mergemate.application.services.workflow_service import WorkflowService

        settings = Mock()
        settings.agents = {}
        gateway = Mock()

        service = WorkflowService(
            llm_gateway=gateway,
            settings=settings,
        )

        recorded_prompt = None

        async def capture_generate(workflow, system_prompt, user_prompt, **kw):
            nonlocal recorded_prompt
            recorded_prompt = user_prompt
            return "lesson result"

        service._generate_stage_output = capture_generate

        result = await service.record_lesson(
            plan_text="plan",
            design_text="",
            implementation_text="",
            test_text="",
            review_text="",
            result_text="",
            error_text="something went wrong",
        )
        assert result == "lesson result"
        assert recorded_prompt is not None
        assert "## Error" in recorded_prompt
        assert "something went wrong" in recorded_prompt


# ── cancel_run.py ────────────────────────────────────────────────────


class TestCancelRun:
    def test_execute_returns_none_when_run_not_found(self) -> None:
        """Line 29: run_id provided but not found -> returns None."""
        from mergemate.application.use_cases.cancel_run import CancelRunUseCase

        repo = Mock()
        repo.get.return_value = None
        cancel_run = CancelRunUseCase(run_repository=repo)

        result = cancel_run.execute("nonexistent-run", chat_id=123)
        assert result is None


# ── submit_prompt.py ─────────────────────────────────────────────────


class TestSubmitPromptUseCase:
    @pytest.mark.asyncio
    async def test_complete_planning_returns_none_when_run_not_found(self) -> None:
        """Line 108: run is None -> returns None."""
        repo = Mock()
        repo.get.return_value = None
        submit = SubmitPromptUseCase(
            run_repository=repo,
            planning_service=Mock(),
            dispatcher=Mock(),
            context_service=Mock(),
            settings=Mock(),
        )

        result = await submit.complete_planning("missing-run")
        assert result is None

    @pytest.mark.asyncio
    async def test_complete_planning_raises_when_approval_run_none(self) -> None:
        """Line 132: approval.run is None -> raises PromptSubmissionError."""
        run = SimpleNamespace(
            run_id="run-1",
            status=RunStatus.QUEUED,
            prompt="test",
            estimate_seconds=30,
        )
        repo = Mock()
        repo.get.return_value = run

        # Simulate approve returning run=None
        repo.approve.return_value = SimpleNamespace(run=None, transitioned=False)

        submit = SubmitPromptUseCase(
            run_repository=repo,
            planning_service=AsyncMock(draft_plan=AsyncMock(return_value="plan text")),
            dispatcher=Mock(),
            context_service=Mock(),
            settings=SimpleNamespace(workflow_control=SimpleNamespace(require_confirmation=False)),
        )

        with pytest.raises(PromptSubmissionError, match="Run approval failed before dispatch"):
            await submit.complete_planning("run-1")

    def test_approve_returns_none_when_approval_fails(self) -> None:
        """Line 204: approved_run is None -> returns None."""
        run = SimpleNamespace(
            run_id="run-1",
            status=RunStatus.AWAITING_CONFIRMATION,
            approved=False,
            plan_text="plan",
            current_stage="planning",
        )
        repo = Mock()
        repo.get.return_value = run
        repo.approve.return_value = SimpleNamespace(run=None, transitioned=False)

        submit = SubmitPromptUseCase(
            run_repository=repo,
            planning_service=Mock(),
            dispatcher=Mock(),
            context_service=Mock(),
            settings=Mock(),
        )

        result = submit.approve("run-1")
        assert result is None


# ── config/loader.py ─────────────────────────────────────────────────


def test_discover_default_local_config_path_fallback(tmp_path) -> None:
    """Line 19: no pyproject.toml found -> returns <cwd>/config/config.yaml."""
    original_cwd = Path.cwd()
    try:
        import os

        os.chdir(tmp_path)
        import importlib

        importlib.reload(config_loader)
        path = config_loader.DEFAULT_LOCAL_CONFIG_PATH
        assert str(path).endswith("config/config.yaml")
    finally:
        os.chdir(original_cwd)


# ── soul.py ──────────────────────────────────────────────────────────


class TestSoul:
    def test_all_souls_returns_all_builtin_souls(self) -> None:
        """Line 272: all_souls returns list of all registered Souls."""
        souls = soul_module.all_souls()
        assert len(souls) > 0
        names = {s.name for s in souls}
        assert "architect" in names
        assert "coder" in names
        assert "tester" in names
        assert "reviewer" in names
