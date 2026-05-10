"""Tests for repo-level knowledge base feature.

Covers:
- SQLiteRepoKnowledgeRepository (record, list_recent)
- LearningService (remember_repo_knowledge, load_repo_knowledge)
- PromptService.render with repo_knowledge
- Orchestrator passes repo_knowledge through to render()
- Bootstrap wires SQLiteRepoKnowledgeRepository into LearningService
- AppConfig.repo_name field
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mergemate.application.orchestrator import AgentOrchestrator
from mergemate.application.services.learning_service import LearningService
from mergemate.application.services.prompt_service import PromptService
from mergemate.config.models import AppConfig
from mergemate.infrastructure.persistence.sqlite import (
    SQLiteDatabase,
    SQLiteRepoKnowledgeRepository,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _async_return(value):
    """Create an async function that returns the given value."""
    async def _fn(*args, **kwargs):
        return value
    return _fn


def _make_learning_service(repo_knowledge_repository=None, enabled=True):
    """Build a LearningService with a minimal learning repo and optional repo knowledge repo."""
    learning_repo = MagicMock()
    learning_repo.record = MagicMock()
    learning_repo.list_recent = MagicMock(return_value=[])
    learning_repo.list_grouped_by_workflow = MagicMock(return_value=[])
    return LearningService(
        learning_repository=learning_repo,
        enabled=enabled,
        max_context_items=5,
        max_result_chars=200,
        llm_gateway=None,
        repo_knowledge_repository=repo_knowledge_repository,
    )


# ══════════════════════════════════════════════════════════════════════════════
# SQLiteRepoKnowledgeRepository
# ══════════════════════════════════════════════════════════════════════════════


class TestSQLiteRepoKnowledgeRepository:
    """Tests 1-4: SQLiteRepoKnowledgeRepository record and list_recent."""

    def test_record_inserts_row(self, tmp_path: Path) -> None:
        """1. record() inserts a row correctly."""
        database = SQLiteDatabase(tmp_path / "test.db")
        database.initialize()
        repo = SQLiteRepoKnowledgeRepository(database)

        repo.record(chat_id=1, repo_name="mergemate", topic="architecture", summary="Uses SQLite for persistence")

        with database.connection() as conn:
            rows = conn.execute(
                "SELECT chat_id, repo_name, topic, summary FROM repo_knowledge"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0]["chat_id"] == 1
        assert rows[0]["repo_name"] == "mergemate"
        assert rows[0]["topic"] == "architecture"
        assert rows[0]["summary"] == "Uses SQLite for persistence"

    def test_list_recent_with_repo_name_filters_correctly(self, tmp_path: Path) -> None:
        """2. list_recent() with repo_name returns only that repo's knowledge."""
        database = SQLiteDatabase(tmp_path / "test.db")
        database.initialize()
        repo = SQLiteRepoKnowledgeRepository(database)

        repo.record(1, "repo-a", "topic-1", "summary-1")
        repo.record(1, "repo-b", "topic-2", "summary-2")
        repo.record(1, "repo-a", "topic-3", "summary-3")

        results = repo.list_recent(chat_id=1, repo_name="repo-a")
        assert len(results) == 2
        assert all(r["repo_name"] == "repo-a" for r in results)

        results_b = repo.list_recent(chat_id=1, repo_name="repo-b")
        assert len(results_b) == 1
        assert results_b[0]["repo_name"] == "repo-b"
        assert results_b[0]["topic"] == "topic-2"

    def test_list_recent_without_repo_name_returns_all(self, tmp_path: Path) -> None:
        """3. list_recent() without repo_name returns all repos' knowledge."""
        database = SQLiteDatabase(tmp_path / "test.db")
        database.initialize()
        repo = SQLiteRepoKnowledgeRepository(database)

        repo.record(1, "repo-a", "topic-1", "summary-1")
        repo.record(1, "repo-b", "topic-2", "summary-2")

        results = repo.list_recent(chat_id=1)
        assert len(results) == 2
        repo_names = {r["repo_name"] for r in results}
        assert repo_names == {"repo-a", "repo-b"}

    def test_list_recent_with_no_rows_returns_empty_list(self, tmp_path: Path) -> None:
        """4. list_recent() with no rows returns []."""
        database = SQLiteDatabase(tmp_path / "test.db")
        database.initialize()
        repo = SQLiteRepoKnowledgeRepository(database)

        results = repo.list_recent(chat_id=1)
        assert results == []

        results_filtered = repo.list_recent(chat_id=1, repo_name="nonexistent")
        assert results_filtered == []

    def test_list_recent_honours_limit(self, tmp_path: Path) -> None:
        """Boundary: list_recent() respects the limit parameter."""
        database = SQLiteDatabase(tmp_path / "test.db")
        database.initialize()
        repo = SQLiteRepoKnowledgeRepository(database)

        for i in range(10):
            repo.record(1, "repo-a", f"topic-{i}", f"summary-{i}")

        results = repo.list_recent(chat_id=1, limit=3)
        assert len(results) == 3


# ══════════════════════════════════════════════════════════════════════════════
# LearningService
# ══════════════════════════════════════════════════════════════════════════════


class TestLearningServiceRepoKnowledge:
    """Tests 5-7: LearningService delegates to repo knowledge repository."""

    def test_remember_repo_knowledge_delegates_to_repository(self) -> None:
        """5. remember_repo_knowledge() delegates to repository."""
        repo_knowledge_repo = MagicMock()
        service = _make_learning_service(repo_knowledge_repository=repo_knowledge_repo)

        service.remember_repo_knowledge(
            chat_id=1, repo_name="mergemate", topic="testing", summary="Uses pytest"
        )

        repo_knowledge_repo.record.assert_called_once_with(
            1, "mergemate", "testing", "Uses pytest"
        )

    def test_load_repo_knowledge_delegates_to_repository(self) -> None:
        """6. load_repo_knowledge() delegates to repository."""
        repo_knowledge_repo = MagicMock()
        repo_knowledge_repo.list_recent = MagicMock(return_value=[
            {"repo_name": "mergemate", "topic": "architecture", "summary": "SQLite"},
        ])
        service = _make_learning_service(repo_knowledge_repository=repo_knowledge_repo)

        result = service.load_repo_knowledge(chat_id=1, repo_name="mergemate")

        repo_knowledge_repo.list_recent.assert_called_once()
        assert len(result) == 1
        assert result[0]["repo_name"] == "mergemate"
        assert result[0]["topic"] == "architecture"

    def test_load_repo_knowledge_without_repo_name(self) -> None:
        """load_repo_knowledge() passes repo_name=None to repository."""
        repo_knowledge_repo = MagicMock()
        repo_knowledge_repo.list_recent = MagicMock(return_value=[])
        service = _make_learning_service(repo_knowledge_repository=repo_knowledge_repo)

        result = service.load_repo_knowledge(chat_id=1)

        repo_knowledge_repo.list_recent.assert_called_once_with(
            1, repo_name=None, limit=5
        )
        assert result == []

    def test_remember_repo_knowledge_is_noop_when_repo_knowledge_repo_is_none(self) -> None:
        """7. Both methods are no-ops when _repo_knowledge_repository is None."""
        service = _make_learning_service(repo_knowledge_repository=None)

        # Should not raise
        service.remember_repo_knowledge(
            chat_id=1, repo_name="mergemate", topic="arch", summary="test"
        )

        result = service.load_repo_knowledge(chat_id=1, repo_name="mergemate")
        assert result == []

    def test_remember_and_load_are_noops_when_learning_disabled(self) -> None:
        """Both methods are no-ops when enabled=False even with repo knowledge repo."""
        repo_knowledge_repo = MagicMock()
        service = _make_learning_service(
            repo_knowledge_repository=repo_knowledge_repo,
            enabled=False,
        )

        service.remember_repo_knowledge(
            chat_id=1, repo_name="mergemate", topic="arch", summary="test"
        )
        repo_knowledge_repo.record.assert_not_called()

        result = service.load_repo_knowledge(chat_id=1, repo_name="mergemate")
        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# PromptService.render with repo_knowledge
# ══════════════════════════════════════════════════════════════════════════════


class TestPromptServiceRepoKnowledge:
    """Tests 8-10: PromptService.render with repo_knowledge parameter."""

    def _write_prompt(self, root: Path, content: str = "system prompt") -> Path:
        system_dir = root / "system"
        system_dir.mkdir(parents=True, exist_ok=True)
        (system_dir / "code_generation.md").write_text(content, encoding="utf-8")
        return root

    def test_render_with_repo_knowledge_renders_section(self, tmp_path: Path) -> None:
        """8. render() with repo_knowledge renders section correctly."""
        prompts_root = self._write_prompt(tmp_path)
        service = PromptService(prompts_root)

        _, user_prompt = service.render(
            "generate_code",
            [],
            [],
            "build feature",
            repo_knowledge=[
                {"repo_name": "mergemate", "topic": "architecture", "summary": "Uses SQLite"},
                {"repo_name": "mergemate", "topic": "testing", "summary": "Uses pytest"},
            ],
        )

        assert "Current repository knowledge:" in user_prompt
        assert "[mergemate] architecture: Uses SQLite" in user_prompt
        assert "[mergemate] testing: Uses pytest" in user_prompt
        assert "build feature" in user_prompt

    def test_render_with_empty_repo_knowledge_list(self, tmp_path: Path) -> None:
        """9. render() with repo_knowledge empty list renders nothing extra."""
        prompts_root = self._write_prompt(tmp_path)
        service = PromptService(prompts_root)

        _, user_prompt = service.render(
            "generate_code",
            [],
            [],
            "build feature",
            repo_knowledge=[],
        )

        assert "Current repository knowledge:" not in user_prompt
        assert "build feature" in user_prompt

    def test_render_with_repo_knowledge_none(self, tmp_path: Path) -> None:
        """10. render() with repo_knowledge=None renders nothing extra (backward compat)."""
        prompts_root = self._write_prompt(tmp_path)
        service = PromptService(prompts_root)

        _, user_prompt = service.render(
            "generate_code",
            [],
            [],
            "build feature",
            repo_knowledge=None,
        )

        assert "Current repository knowledge:" not in user_prompt
        assert "build feature" in user_prompt

    def test_render_with_learning_and_repo_knowledge(self, tmp_path: Path) -> None:
        """render() combines learning section and repo knowledge section."""
        prompts_root = self._write_prompt(tmp_path)
        service = PromptService(prompts_root)

        _, user_prompt = service.render(
            "generate_code",
            [],
            [{"workflow": "generate_code", "prompt": "p1", "result_excerpt": "excerpt"}],
            "build feature",
            repo_knowledge=[
                {"repo_name": "mergemate", "topic": "arch", "summary": "Uses SQLite"},
            ],
        )

        assert "Previously successful patterns:" in user_prompt
        assert "Current repository knowledge:" in user_prompt
        assert "[mergemate] arch: Uses SQLite" in user_prompt
        # repo knowledge should appear after learning section
        assert user_prompt.index("Current repository knowledge:") > user_prompt.index("Previously successful patterns:")


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator - process_run passes repo_knowledge to render()
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_orchestrator_passes_repo_knowledge_to_render() -> None:
    """11. process_run() calls load_repo_knowledge() and passes to render()."""
    from mergemate.application.execution_plan import OrchestratorDependencies  # noqa: F811
    from mergemate.domain.runs.entities import AgentRun
    from mergemate.domain.shared import RunStatus
    from datetime import UTC, datetime

    # Build a minimal run
    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-1",
        chat_id=123,
        user_id=456,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.QUEUED,
        current_stage="queued_for_execution",
        prompt="build a feature",
        estimate_seconds=30,
        plan_text="approved plan",
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=True,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )

    # Track calls to load_repo_knowledge and render
    class TrackingLearningService:
        def __init__(self):
            self.load_repo_knowledge_calls = []
            self.load_grouped_learnings_calls = []

        def load_grouped_learnings(self, chat_id, current_workflow):
            self.load_grouped_learnings_calls.append((chat_id, current_workflow))
            return []

        def load_repo_knowledge(self, chat_id, repo_name=None):
            self.load_repo_knowledge_calls.append((chat_id, repo_name))
            return [{"repo_name": repo_name, "topic": "arch", "summary": "test"}]

        def remember_success(self, **payload):
            pass

    class RunRepositoryStub:
        def __init__(self, run):
            self.run = run
            self._get_calls = 0

        def get(self, run_id):
            self._get_calls += 1
            if self.run.run_id == run_id:
                return self.run
            return None

        def try_update_status(self, run_id, status, expected_current_status=None, current_stage=None, result_text=None, error_text=None):
            return SimpleNamespace(run=self.run, transitioned=True)

    class PromptServiceTracker:
        def __init__(self):
            self.render_calls = []

        def render(self, workflow, recent_messages, learned_items, prompt, repo_knowledge=None):
            self.render_calls.append({
                "workflow": workflow,
                "recent_messages": recent_messages,
                "learned_items": learned_items,
                "prompt": prompt,
                "repo_knowledge": repo_knowledge,
            })
            return ("system", "context")

    class ToolServiceStub:
        async def build_runtime_tool_context_async(self, run_id, agent_name, resume_stage="retrieve_context"):
            return ""

    learning_service = TrackingLearningService()
    prompt_service = PromptServiceTracker()

    orchestrator = AgentOrchestrator(
        deps=OrchestratorDependencies(
            run_repository=RunRepositoryStub(run),
            context_service=SimpleNamespace(load_recent_messages=lambda chat_id: []),
            documentation_service=SimpleNamespace(),
            learning_service=learning_service,
            planning_service=SimpleNamespace(),
            prompt_service=prompt_service,
            tool_service=ToolServiceStub(),
            workflow_service=SimpleNamespace(
                build_execution_plan=lambda workflow, agent_name: SimpleNamespace(
                    requires_tool_context=False,
                    execute=_async_return(run),
                ),
                uses_multi_stage_delivery=lambda w: False,
            ),
            llm_gateway=None,
            settings=SimpleNamespace(repo_name="mergemate"),
        ),
    )

    result = await orchestrator.process_run("run-1")

    # Verify load_repo_knowledge was called with the settings.repo_name
    assert len(learning_service.load_repo_knowledge_calls) == 1
    assert learning_service.load_repo_knowledge_calls[0] == (123, "mergemate")

    # Verify render() was called with repo_knowledge
    assert len(prompt_service.render_calls) >= 1
    last_render_call = prompt_service.render_calls[-1]
    assert last_render_call["repo_knowledge"] is not None
    assert len(last_render_call["repo_knowledge"]) == 1
    assert last_render_call["repo_knowledge"][0]["repo_name"] == "mergemate"

    assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator - backward compat: no repo_name on settings
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_orchestrator_passes_none_repo_name_when_settings_missing() -> None:
    """Orchestrator calls load_repo_knowledge() with None when settings has no repo_name."""
    from mergemate.application.execution_plan import OrchestratorDependencies
    from mergemate.domain.runs.entities import AgentRun
    from mergemate.domain.shared import RunStatus
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    run = AgentRun(
        run_id="run-1",
        chat_id=123,
        user_id=456,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.QUEUED,
        current_stage="queued_for_execution",
        prompt="build a feature",
        estimate_seconds=30,
        plan_text="approved plan",
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=True,
        result_text=None,
        error_text=None,
        created_at=now,
        updated_at=now,
    )

    class TrackingLearningService:
        def __init__(self):
            self.calls = []

        def load_grouped_learnings(self, chat_id, current_workflow):
            return []

        def load_repo_knowledge(self, chat_id, repo_name=None):
            self.calls.append((chat_id, repo_name))
            return []

        def remember_success(self, **payload):
            pass

    learning_service = TrackingLearningService()

    orchestrator = AgentOrchestrator(
        deps=OrchestratorDependencies(
            run_repository=SimpleNamespace(
                get=lambda run_id: run,
                try_update_status=lambda run_id, status, **kw: SimpleNamespace(run=run, transitioned=True),
            ),
            context_service=SimpleNamespace(load_recent_messages=lambda chat_id: []),
            documentation_service=SimpleNamespace(),
            learning_service=learning_service,
            planning_service=SimpleNamespace(),
            prompt_service=SimpleNamespace(
                render=lambda workflow, recent_messages, learned_items, prompt, repo_knowledge=None: ("system", "context")
            ),
            tool_service=SimpleNamespace(
                build_runtime_tool_context_async=lambda run_id, agent_name, resume_stage="retrieve_context": "",
            ),
            workflow_service=SimpleNamespace(
                build_execution_plan=lambda workflow, agent_name: SimpleNamespace(
                    requires_tool_context=False,
                    execute=_async_return(run),
                ),
            ),
            llm_gateway=None,
            settings=SimpleNamespace(repo_name=None),
        ),
    )

    await orchestrator.process_run("run-1")

    assert len(learning_service.calls) == 1
    assert learning_service.calls[0] == (123, None)


# ══════════════════════════════════════════════════════════════════════════════
# Bootstrap wiring
# ══════════════════════════════════════════════════════════════════════════════


def test_bootstrap_wires_repo_knowledge_repository(monkeypatch, tmp_path: Path) -> None:
    """12. Wires SQLiteRepoKnowledgeRepository into LearningService."""
    import mergemate.bootstrap as bootstrap_module

    class RepoKnowledgeRepositoryRecorder:
        instances = []

        def __init__(self, database):
            self.database = database
            self.__class__.instances.append(self)

    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteRepoKnowledgeRepository",
        RepoKnowledgeRepositoryRecorder,
    )

    captured_kwargs = {}

    class LearningServiceRecorder:
        def __init__(self, *args, **kwargs):
            captured_kwargs.update(kwargs)

    monkeypatch.setattr(bootstrap_module, "LearningService", LearningServiceRecorder)
    monkeypatch.setattr(bootstrap_module, "resolve_config_path", lambda _explicit=None: tmp_path / "config.yaml")
    monkeypatch.setattr(
        bootstrap_module,
        "load_runtime_settings",
        lambda _explicit=None: SimpleNamespace(
            logging=SimpleNamespace(level="INFO"),
            learning=SimpleNamespace(enabled=True, max_context_items=3, max_result_chars=200, extraction_agent=None),
            tools=SimpleNamespace(allow_package_install=False, allowed_packages=[], pip_executable="python3"),
            source_control=SimpleNamespace(enable_git=False, enable_github=False, enable_gitlab=False),
            providers={},
            runtime=SimpleNamespace(max_concurrent_runs=1, default_request_timeout_seconds=90, job_lease_seconds=30, job_heartbeat_interval_seconds=10),
            workflow_control=SimpleNamespace(),
            workflow_plugins=[],
            resolve_database_path=lambda _resolved: tmp_path / "db.sqlite",
            resolve_docs_root=lambda _resolved: tmp_path / "docs",
            resolve_working_directory=lambda _resolved: tmp_path,
            resolve_provider_api_key=lambda _pn: None,
        ),
    )
    monkeypatch.setattr(bootstrap_module, "configure_logging", lambda _level: None)
    monkeypatch.setattr(bootstrap_module, "log_startup_configuration", lambda *a, **kw: None)
    monkeypatch.setattr(bootstrap_module, "SQLiteDatabase", lambda path: SimpleNamespace(path=path, initialize=lambda: None))
    monkeypatch.setattr(bootstrap_module, "SQLiteRunRepository", lambda _db: "run_repo")
    monkeypatch.setattr(bootstrap_module, "SQLiteRunJobRepository", lambda _db: "run_job_repo")
    monkeypatch.setattr(bootstrap_module, "SQLiteConversationRepository", lambda _db: "conv_repo")
    monkeypatch.setattr(bootstrap_module, "SQLiteLearningRepository", lambda _db: "learning_repo")
    monkeypatch.setattr(bootstrap_module, "SQLiteToolEventRepository", lambda _db: "tool_event_repo")
    monkeypatch.setattr(bootstrap_module, "ContextService", lambda _repo: "context_service")
    monkeypatch.setattr(bootstrap_module, "DocumentationService", lambda _dr: "doc_service")
    monkeypatch.setattr(bootstrap_module, "PromptService", lambda _pr: "prompt_service")
    monkeypatch.setattr(bootstrap_module, "ParallelLLMGateway", lambda _s, _c: "gateway")
    monkeypatch.setattr(bootstrap_module, "ToolService", lambda *a, **kw: "tool_service")
    monkeypatch.setattr(bootstrap_module, "PlanningService", lambda *a, **kw: "planning_service")
    monkeypatch.setattr(bootstrap_module, "WorkflowService", lambda *a, **kw: "workflow_service")
    monkeypatch.setattr(bootstrap_module, "LocalQueue", lambda: "queue")
    monkeypatch.setattr(bootstrap_module, "TelegramRunLifecycleNotifier", lambda _s: SimpleNamespace(bind_runtime=lambda _r: None))
    monkeypatch.setattr(bootstrap_module, "AgentOrchestrator", lambda **kw: "orchestrator")
    monkeypatch.setattr(bootstrap_module, "BackgroundRunWorker", lambda **kw: "worker")
    monkeypatch.setattr(bootstrap_module, "RunDispatcher", lambda *a, **kw: "dispatcher")
    monkeypatch.setattr(bootstrap_module, "SubmitPromptUseCase", lambda *a: "submit")
    monkeypatch.setattr(bootstrap_module, "GetRunStatusUseCase", lambda *a: "status")
    monkeypatch.setattr(bootstrap_module, "CancelRunUseCase", lambda *a: "cancel")
    # ToolRegistryBuilder replaces direct ToolRegistry construction in main; these
    # no longer live on bootstrap_module so we mock the builder instead.
    mock_builder = SimpleNamespace()
    mock_builder.tools = {}
    mock_builder.with_git = lambda: mock_builder
    mock_builder.with_github_cli = lambda: mock_builder
    mock_builder.with_gitlab_cli = lambda: mock_builder
    mock_builder.build = lambda: SimpleNamespace(tools=mock_builder.tools)
    monkeypatch.setattr(bootstrap_module, "ToolRegistryBuilder", lambda *_a, **_kw: mock_builder)

    bootstrap_module.bootstrap()

    # LearningService should have received repo_knowledge_repository
    rk_repo = captured_kwargs.get("repo_knowledge_repository")
    assert rk_repo is not None, "LearningService was not wired with repo_knowledge_repository"
    assert isinstance(
        rk_repo, RepoKnowledgeRepositoryRecorder
    ), f"Expected RepoKnowledgeRepositoryRecorder, got {type(rk_repo)}"

    # The repo knowledge repository should be a real instance
    assert len(RepoKnowledgeRepositoryRecorder.instances) == 1


# ══════════════════════════════════════════════════════════════════════════════
# config/models.py — AppConfig.repo_name
# ══════════════════════════════════════════════════════════════════════════════


class TestAppConfigRepoName:
    """Tests 13-14: AppConfig.repo_name field."""

    def _minimal_config(self) -> dict:
        return {
            "default_agent": "coder",
            "default_provider": "primary",
            "providers": {
                "primary": {"api_key_env": "KEY", "model": "gpt-4"},
            },
            "telegram": {"bot_token_env": "BOT_TOKEN"},
            "agents": {
                "coder": {"workflow": "generate_code"},
                "planner": {"workflow": "planning"},
                "architect": {"workflow": "design"},
                "tester": {"workflow": "testing"},
                "reviewer": {"workflow": "review"},
                "explainer": {"workflow": "explain_code"},
            },
            "runtime": {"max_concurrent_runs": 2},
        }

    def test_repo_name_defaults_to_none(self) -> None:
        """13. AppConfig.repo_name is None by default."""
        config = AppConfig.model_validate(self._minimal_config())
        assert config.repo_name is None

    def test_repo_name_accepts_string_value(self) -> None:
        """14. AppConfig.repo_name accepts a string value."""
        config = AppConfig.model_validate({
            **self._minimal_config(),
            "repo_name": "MergeMate",
        })
        assert config.repo_name == "MergeMate"

    def test_repo_name_accessible_via_settings_property(self) -> None:
        """repo_name is accessible via settings.repo_name in orchestrator."""
        config = AppConfig.model_validate({
            **self._minimal_config(),
            "repo_name": "my-repo",
        })
        assert config.repo_name == "my-repo"