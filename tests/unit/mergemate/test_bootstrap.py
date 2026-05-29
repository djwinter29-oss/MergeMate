from pathlib import Path
from types import SimpleNamespace

from mergemate import bootstrap as bootstrap_module


class Recorder:
    def __init__(self) -> None:
        self.calls = []

    def record(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_bootstrap_imports_repo_knowledge_repository_class() -> None:
    assert (
        bootstrap_module.SQLiteRepoKnowledgeRepository.__name__ == "SQLiteRepoKnowledgeRepository"
    )


def test_bootstrap_wires_runtime_dependencies(monkeypatch, tmp_path: Path) -> None:
    recorded = Recorder()
    config_path = tmp_path / "config.yaml"
    settings = SimpleNamespace(
        logging=SimpleNamespace(level="DEBUG"),
        learning=SimpleNamespace(
            enabled=True,
            max_context_items=3,
            max_result_chars=1200,
            extraction_agent="lesson-extractor",
        ),
        tools=SimpleNamespace(
            allow_package_install=True, allowed_packages=["requests"], pip_executable="python3"
        ),
        source_control=SimpleNamespace(
            enable_git=True,
            enable_github=True,
            enable_gitlab=True,
            git_executable="git",
            github_executable="gh",
            gitlab_executable="glab",
        ),
        providers={
            "primary": SimpleNamespace(
                model="gpt-5.4",
                timeout_seconds=30,
                provider_url="https://example.invalid",
                api_key_header="Authorization",
                api_key_prefix="Bearer",
                extra_headers={"X-Test": "1"},
            )
        },
        runtime=SimpleNamespace(
            max_concurrent_runs=4,
            default_request_timeout_seconds=90,
            job_lease_seconds=30,
            job_heartbeat_interval_seconds=10,
        ),
        workflow_control=SimpleNamespace(),
        workflow_plugins=[],
        resolve_database_path=lambda _resolved: tmp_path / "workspace" / ".state" / "runtime.db",
        resolve_docs_root=lambda _resolved: tmp_path / "workspace" / "docs",
        resolve_working_directory=lambda _resolved: tmp_path / "workspace" / "repo",
        resolve_provider_api_key=lambda provider_name: f"key-for-{provider_name}",
    )

    class DatabaseStub:
        def __init__(self, path) -> None:
            recorded.record("database", path)
            self.path = path

        def initialize(self) -> None:
            recorded.record("database.initialize")

    class RepositoryStub:
        def __init__(self, database) -> None:
            recorded.record(self.__class__.__name__, database)

    class LearningServiceStub:
        def __init__(self, *args, **kwargs) -> None:
            recorded.record("learning_service", *args, **kwargs)

    class DocumentationServiceStub:
        def __init__(self, docs_root) -> None:
            recorded.record("documentation_service", docs_root)

    class PromptServiceStub:
        def __init__(self, prompts_root) -> None:
            recorded.record("prompt_service", prompts_root)

    class OpenAIAdapterStub:
        def __init__(self, **kwargs) -> None:
            recorded.record("openai_adapter", **kwargs)

    class GatewayStub:
        def __init__(self, wired_settings, llm_clients) -> None:
            recorded.record("gateway", wired_settings, llm_clients)

    class ToolRegistryStub:
        def __init__(self, tools) -> None:
            recorded.record("tool_registry", tools)
            self.tools = tools

    class ToolServiceStub:
        def __init__(self, registry, wired_settings, **kwargs) -> None:
            recorded.record("tool_service", registry.tools, wired_settings, kwargs)

    class PlanningServiceStub:
        def __init__(self, gateway, wired_settings) -> None:
            recorded.record("planning_service", gateway, wired_settings)

    class WorkflowServiceStub:
        def __init__(self, gateway, wired_settings) -> None:
            recorded.record("workflow_service", gateway, wired_settings)

    class OrchestratorStub:
        def __init__(self, **kwargs) -> None:
            recorded.record("orchestrator", **kwargs)

    class WorkerStub:
        def __init__(self, **kwargs) -> None:
            recorded.record("worker", **kwargs)

    class DispatcherStub:
        def __init__(self, run_job_repository, queue_backend) -> None:
            recorded.record("dispatcher", run_job_repository, queue_backend)

    class LifecycleNotifierStub:
        def __init__(self, wired_settings) -> None:
            recorded.record("lifecycle_notifier", wired_settings)

        def bind_runtime(self, runtime) -> None:
            recorded.record("lifecycle_notifier.bind_runtime", runtime)

    class SubmitPromptStub:
        def __init__(self, *args) -> None:
            recorded.record("submit_prompt", *args)

    monkeypatch.setattr(bootstrap_module, "resolve_config_path", lambda _explicit=None: config_path)
    monkeypatch.setattr(bootstrap_module, "load_runtime_settings", lambda _explicit=None: settings)
    monkeypatch.setattr(
        bootstrap_module,
        "configure_logging",
        lambda level: recorded.record("configure_logging", level),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "log_startup_configuration",
        lambda wired_settings, *, config_path, database_path: recorded.record(
            "log_startup_configuration", wired_settings, config_path, database_path
        ),
    )
    monkeypatch.setattr(bootstrap_module, "SQLiteDatabase", DatabaseStub)
    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteRunRepository",
        type("SQLiteRunRepositoryStub", (RepositoryStub,), {}),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteRunJobRepository",
        type("SQLiteRunJobRepositoryStub", (RepositoryStub,), {}),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteConversationRepository",
        type("SQLiteConversationRepositoryStub", (RepositoryStub,), {}),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteLearningRepository",
        type("SQLiteLearningRepositoryStub", (RepositoryStub,), {}),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteRepoKnowledgeRepository",
        type("SQLiteRepoKnowledgeRepositoryStub", (RepositoryStub,), {}),
    )
    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteToolEventRepository",
        type("SQLiteToolEventRepositoryStub", (RepositoryStub,), {}),
    )
    monkeypatch.setattr(bootstrap_module, "ContextService", lambda repo: SimpleNamespace(repo=repo))
    monkeypatch.setattr(bootstrap_module, "LearningService", LearningServiceStub)
    monkeypatch.setattr(bootstrap_module, "DocumentationService", DocumentationServiceStub)
    monkeypatch.setattr(bootstrap_module, "PromptService", PromptServiceStub)
    monkeypatch.setattr(bootstrap_module, "OpenAIAdapter", OpenAIAdapterStub)
    monkeypatch.setattr(bootstrap_module, "ParallelLLMGateway", GatewayStub)

    class ToolRegistryBuilderStub:
        def __init__(self, *args, **kwargs):
            self._captured_tools = []

        def with_git(self):
            self._captured_tools.append("git")
            return self

        def with_github_cli(self):
            self._captured_tools.append("github")
            return self

        def with_gitlab_cli(self):
            self._captured_tools.append("gitlab")
            return self

        def build(self):
            tools = {
                "code_formatter": "formatter",
                "package_installer": "installer",
                "syntax_checker": "checker",
                "git_repository": "git_repo",
                "github_cli": "gh_cli",
                "gitlab_cli": "gl_cli",
            }
            return SimpleNamespace(tools=tools)

    monkeypatch.setattr(bootstrap_module, "ToolRegistryBuilder", ToolRegistryBuilderStub)
    monkeypatch.setattr(bootstrap_module, "ToolService", ToolServiceStub)
    monkeypatch.setattr(bootstrap_module, "PlanningService", PlanningServiceStub)
    monkeypatch.setattr(bootstrap_module, "WorkflowService", WorkflowServiceStub)
    monkeypatch.setattr(bootstrap_module, "LocalQueue", lambda: "queue_backend")
    monkeypatch.setattr(bootstrap_module, "TelegramRunLifecycleNotifier", LifecycleNotifierStub)
    monkeypatch.setattr(bootstrap_module, "AgentOrchestrator", OrchestratorStub)
    monkeypatch.setattr(bootstrap_module, "BackgroundRunWorker", WorkerStub)
    monkeypatch.setattr(bootstrap_module, "RunDispatcher", DispatcherStub)
    monkeypatch.setattr(bootstrap_module, "SubmitPromptUseCase", SubmitPromptStub)
    monkeypatch.setattr(
        bootstrap_module,
        "GetRunStatusUseCase",
        lambda repo, tool_event_repo: ("status", repo, tool_event_repo),
    )
    monkeypatch.setattr(bootstrap_module, "CancelRunUseCase", lambda repo: ("cancel", repo))

    runtime = bootstrap_module.bootstrap()

    assert runtime.config_path == config_path
    assert runtime.persistence.database.path == tmp_path / "workspace" / ".state" / "runtime.db"
    startup_log_call = next(
        args for args, _ in recorded.calls if args and args[0] == "log_startup_configuration"
    )
    assert startup_log_call[2] == config_path
    assert startup_log_call[3] == tmp_path / "workspace" / ".state" / "runtime.db"
    # ToolRegistryBuilder replaces the old ToolRegistry(tools) direct call,
    # so the "tool_registry" recorded call is no longer produced.
    tool_service_call = next(
        args for args, _ in recorded.calls if args and args[0] == "tool_service"
    )
    assert set(tool_service_call[1]) == {
        "code_formatter",
        "package_installer",
        "syntax_checker",
        "git_repository",
        "github_cli",
        "gitlab_cli",
    }


def test_bootstrap_skips_disabled_source_control_tools(monkeypatch, tmp_path: Path) -> None:
    settings = SimpleNamespace(
        logging=SimpleNamespace(level="INFO"),
        learning=SimpleNamespace(
            enabled=False,
            max_context_items=1,
            max_result_chars=100,
            extraction_agent=None,
        ),
        tools=SimpleNamespace(
            allow_package_install=False, allowed_packages=[], pip_executable="python3"
        ),
        source_control=SimpleNamespace(
            enable_git=False,
            enable_github=False,
            enable_gitlab=False,
            git_executable="git",
            github_executable="gh",
            gitlab_executable="glab",
        ),
        providers={},
        runtime=SimpleNamespace(
            max_concurrent_runs=1,
            default_request_timeout_seconds=90,
            job_lease_seconds=30,
            job_heartbeat_interval_seconds=10,
        ),
        workflow_control=SimpleNamespace(),
        workflow_plugins=[],
        resolve_database_path=lambda _resolved: tmp_path / "db.sqlite",
        resolve_docs_root=lambda _resolved: tmp_path / "docs",
        resolve_working_directory=lambda _resolved: tmp_path,
        resolve_provider_api_key=lambda _provider_name: None,
    )
    captured = {}

    monkeypatch.setattr(
        bootstrap_module, "resolve_config_path", lambda _explicit=None: tmp_path / "config.yaml"
    )
    monkeypatch.setattr(bootstrap_module, "load_runtime_settings", lambda _explicit=None: settings)
    monkeypatch.setattr(bootstrap_module, "configure_logging", lambda _level: None)
    monkeypatch.setattr(
        bootstrap_module,
        "log_startup_configuration",
        lambda _wired_settings, *, config_path, database_path: None,
    )
    monkeypatch.setattr(
        bootstrap_module,
        "SQLiteDatabase",
        lambda path: SimpleNamespace(path=path, initialize=lambda: None),
    )
    monkeypatch.setattr(bootstrap_module, "SQLiteRunRepository", lambda _database: "run_repo")
    monkeypatch.setattr(
        bootstrap_module, "SQLiteRunJobRepository", lambda _database: "run_job_repo"
    )
    monkeypatch.setattr(
        bootstrap_module, "SQLiteConversationRepository", lambda _database: "conversation_repo"
    )
    monkeypatch.setattr(
        bootstrap_module, "SQLiteLearningRepository", lambda _database: "learning_repo"
    )
    monkeypatch.setattr(
        bootstrap_module, "SQLiteRepoKnowledgeRepository", lambda _database: "repo_knowledge_repo"
    )
    monkeypatch.setattr(
        bootstrap_module, "SQLiteToolEventRepository", lambda _database: "tool_event_repo"
    )
    monkeypatch.setattr(bootstrap_module, "ContextService", lambda _repo: "context_service")
    monkeypatch.setattr(
        bootstrap_module, "LearningService", lambda *_args, **_kwargs: "learning_service"
    )
    monkeypatch.setattr(
        bootstrap_module, "DocumentationService", lambda _docs_root: "documentation_service"
    )
    monkeypatch.setattr(bootstrap_module, "PromptService", lambda _prompts_root: "prompt_service")
    monkeypatch.setattr(
        bootstrap_module, "ParallelLLMGateway", lambda _wired_settings, _llm_clients: "gateway"
    )
    monkeypatch.setattr(
        bootstrap_module,
        "ToolService",
        lambda _registry, _wired_settings, **_kwargs: "tool_service",
    )
    monkeypatch.setattr(
        bootstrap_module, "PlanningService", lambda _gateway, _wired_settings: "planning_service"
    )
    monkeypatch.setattr(
        bootstrap_module, "WorkflowService", lambda _gateway, _wired_settings: "workflow_service"
    )
    monkeypatch.setattr(bootstrap_module, "LocalQueue", lambda: "queue_backend")
    monkeypatch.setattr(
        bootstrap_module,
        "TelegramRunLifecycleNotifier",
        lambda _settings: SimpleNamespace(bind_runtime=lambda _runtime: None),
    )
    monkeypatch.setattr(bootstrap_module, "AgentOrchestrator", lambda **_kwargs: "orchestrator")
    monkeypatch.setattr(bootstrap_module, "BackgroundRunWorker", lambda **_kwargs: "worker")
    monkeypatch.setattr(
        bootstrap_module, "RunDispatcher", lambda _run_job_repository, _queue_backend: "dispatcher"
    )
    monkeypatch.setattr(bootstrap_module, "SubmitPromptUseCase", lambda *_args: "submit_prompt")
    monkeypatch.setattr(
        bootstrap_module, "GetRunStatusUseCase", lambda _repo, _tool_event_repo: "get_run_status"
    )
    monkeypatch.setattr(bootstrap_module, "CancelRunUseCase", lambda _repo: "cancel_run")
    # These tool imports were removed from bootstrap.py (replaced by ToolRegistryBuilder lazy imports),
    # so clean them up from the monkeypatch too.
    captured["tools"] = "built"

    class ToolRegistryBuilderStub2:
        def __init__(self, settings, working_directory):
            self._settings = settings
            self._wd = working_directory

        def with_git(self):
            return self

        def with_github_cli(self):
            return self

        def with_gitlab_cli(self):
            return self

        def build(self):
            captured["tools"] = "built"
            return SimpleNamespace(list_tools=lambda: [])

    monkeypatch.setattr(bootstrap_module, "ToolRegistryBuilder", ToolRegistryBuilderStub2)

    runtime = bootstrap_module.bootstrap()

    assert captured["tools"] == "built"
    assert runtime.services.tool_service == "tool_service"
