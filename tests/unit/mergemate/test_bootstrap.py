from pathlib import Path
from types import SimpleNamespace

from mergemate import bootstrap as bootstrap_module


class Recorder:
    def __init__(self) -> None:
        self.calls = []

    def record(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_bootstrap_wires_runtime_dependencies(monkeypatch, tmp_path: Path) -> None:
    recorded = Recorder()
    config_path = tmp_path / "config.yaml"
    settings = SimpleNamespace(
        logging=SimpleNamespace(level="DEBUG"),
        learning=SimpleNamespace(enabled=True, max_context_items=3, max_result_chars=1200),
        tools=SimpleNamespace(allow_package_install=True, allowed_packages=["requests"], pip_executable="python3"),
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
        runtime=SimpleNamespace(max_concurrent_runs=4),
        workflow_control=SimpleNamespace(),
        resolve_database_path=lambda resolved: tmp_path / "workspace" / ".state" / "runtime.db",
        resolve_docs_root=lambda resolved: tmp_path / "workspace" / "docs",
        resolve_working_directory=lambda resolved: tmp_path / "workspace" / "repo",
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
        def __init__(self, worker) -> None:
            recorded.record("dispatcher", worker)

    class SubmitPromptStub:
        def __init__(self, *args) -> None:
            recorded.record("submit_prompt", *args)

    monkeypatch.setattr(bootstrap_module, "resolve_config_path", lambda explicit=None: config_path)
    monkeypatch.setattr(bootstrap_module, "load_runtime_settings", lambda explicit=None: settings)
    monkeypatch.setattr(bootstrap_module, "configure_logging", lambda level: recorded.record("configure_logging", level))
    monkeypatch.setattr(bootstrap_module, "SQLiteDatabase", DatabaseStub)
    monkeypatch.setattr(bootstrap_module, "SQLiteRunRepository", type("SQLiteRunRepositoryStub", (RepositoryStub,), {}))
    monkeypatch.setattr(bootstrap_module, "SQLiteConversationRepository", type("SQLiteConversationRepositoryStub", (RepositoryStub,), {}))
    monkeypatch.setattr(bootstrap_module, "SQLiteLearningRepository", type("SQLiteLearningRepositoryStub", (RepositoryStub,), {}))
    monkeypatch.setattr(bootstrap_module, "SQLiteToolEventRepository", type("SQLiteToolEventRepositoryStub", (RepositoryStub,), {}))
    monkeypatch.setattr(bootstrap_module, "ContextService", lambda repo: SimpleNamespace(repo=repo))
    monkeypatch.setattr(bootstrap_module, "LearningService", LearningServiceStub)
    monkeypatch.setattr(bootstrap_module, "DocumentationService", DocumentationServiceStub)
    monkeypatch.setattr(bootstrap_module, "PromptService", PromptServiceStub)
    monkeypatch.setattr(bootstrap_module, "OpenAIAdapter", OpenAIAdapterStub)
    monkeypatch.setattr(bootstrap_module, "ParallelLLMGateway", GatewayStub)
    monkeypatch.setattr(bootstrap_module, "CodeFormatterTool", lambda: "formatter")
    monkeypatch.setattr(bootstrap_module, "PackageInstallerTool", lambda **kwargs: ("package_installer", kwargs))
    monkeypatch.setattr(bootstrap_module, "SyntaxCheckerTool", lambda: "syntax_checker")
    monkeypatch.setattr(bootstrap_module, "GitRepositoryTool", lambda executable, cwd: ("git_repository", executable, cwd))
    monkeypatch.setattr(bootstrap_module, "GitHubCliTool", lambda executable, cwd: ("github_cli", executable, cwd))
    monkeypatch.setattr(bootstrap_module, "GitLabCliTool", lambda executable, cwd: ("gitlab_cli", executable, cwd))
    monkeypatch.setattr(bootstrap_module, "ToolRegistry", ToolRegistryStub)
    monkeypatch.setattr(bootstrap_module, "ToolService", ToolServiceStub)
    monkeypatch.setattr(bootstrap_module, "WorkflowService", WorkflowServiceStub)
    monkeypatch.setattr(bootstrap_module, "AgentOrchestrator", OrchestratorStub)
    monkeypatch.setattr(bootstrap_module, "BackgroundRunWorker", WorkerStub)
    monkeypatch.setattr(bootstrap_module, "RunDispatcher", DispatcherStub)
    monkeypatch.setattr(bootstrap_module, "SubmitPromptUseCase", SubmitPromptStub)
    monkeypatch.setattr(bootstrap_module, "ApproveRunUseCase", lambda submit: ("approve", submit))
    monkeypatch.setattr(bootstrap_module, "GetRunStatusUseCase", lambda repo: ("status", repo))
    monkeypatch.setattr(bootstrap_module, "CancelRunUseCase", lambda repo: ("cancel", repo))

    runtime = bootstrap_module.bootstrap()

    assert runtime.config_path == config_path
    assert runtime.database.path == tmp_path / "workspace" / ".state" / "runtime.db"
    assert runtime.approve_run[0] == "approve"
    tool_registry_tools = next(args[1] for args, _ in recorded.calls if args and args[0] == "tool_registry")
    assert set(tool_registry_tools) == {
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
        learning=SimpleNamespace(enabled=False, max_context_items=1, max_result_chars=100),
        tools=SimpleNamespace(allow_package_install=False, allowed_packages=[], pip_executable="python3"),
        source_control=SimpleNamespace(
            enable_git=False,
            enable_github=False,
            enable_gitlab=False,
            git_executable="git",
            github_executable="gh",
            gitlab_executable="glab",
        ),
        providers={},
        runtime=SimpleNamespace(max_concurrent_runs=1),
        workflow_control=SimpleNamespace(),
        resolve_database_path=lambda resolved: tmp_path / "db.sqlite",
        resolve_docs_root=lambda resolved: tmp_path / "docs",
        resolve_working_directory=lambda resolved: tmp_path,
        resolve_provider_api_key=lambda provider_name: None,
    )
    captured = {}

    monkeypatch.setattr(bootstrap_module, "resolve_config_path", lambda explicit=None: tmp_path / "config.yaml")
    monkeypatch.setattr(bootstrap_module, "load_runtime_settings", lambda explicit=None: settings)
    monkeypatch.setattr(bootstrap_module, "configure_logging", lambda level: None)
    monkeypatch.setattr(bootstrap_module, "SQLiteDatabase", lambda path: SimpleNamespace(path=path, initialize=lambda: None))
    monkeypatch.setattr(bootstrap_module, "SQLiteRunRepository", lambda database: "run_repo")
    monkeypatch.setattr(bootstrap_module, "SQLiteConversationRepository", lambda database: "conversation_repo")
    monkeypatch.setattr(bootstrap_module, "SQLiteLearningRepository", lambda database: "learning_repo")
    monkeypatch.setattr(bootstrap_module, "SQLiteToolEventRepository", lambda database: "tool_event_repo")
    monkeypatch.setattr(bootstrap_module, "ContextService", lambda repo: "context_service")
    monkeypatch.setattr(bootstrap_module, "LearningService", lambda *args, **kwargs: "learning_service")
    monkeypatch.setattr(bootstrap_module, "DocumentationService", lambda docs_root: "documentation_service")
    monkeypatch.setattr(bootstrap_module, "PromptService", lambda prompts_root: "prompt_service")
    monkeypatch.setattr(bootstrap_module, "ParallelLLMGateway", lambda wired_settings, llm_clients: "gateway")
    monkeypatch.setattr(bootstrap_module, "ToolService", lambda registry, wired_settings, **kwargs: "tool_service")
    monkeypatch.setattr(bootstrap_module, "WorkflowService", lambda gateway, wired_settings: "workflow_service")
    monkeypatch.setattr(bootstrap_module, "AgentOrchestrator", lambda **kwargs: "orchestrator")
    monkeypatch.setattr(bootstrap_module, "BackgroundRunWorker", lambda **kwargs: "worker")
    monkeypatch.setattr(bootstrap_module, "RunDispatcher", lambda worker: "dispatcher")
    monkeypatch.setattr(bootstrap_module, "SubmitPromptUseCase", lambda *args: "submit_prompt")
    monkeypatch.setattr(bootstrap_module, "ApproveRunUseCase", lambda submit: "approve_run")
    monkeypatch.setattr(bootstrap_module, "GetRunStatusUseCase", lambda repo: "get_run_status")
    monkeypatch.setattr(bootstrap_module, "CancelRunUseCase", lambda repo: "cancel_run")
    monkeypatch.setattr(bootstrap_module, "CodeFormatterTool", lambda: "formatter")
    monkeypatch.setattr(bootstrap_module, "PackageInstallerTool", lambda **kwargs: "package_installer")
    monkeypatch.setattr(bootstrap_module, "SyntaxCheckerTool", lambda: "syntax_checker")

    class ToolRegistryStub:
        def __init__(self, tools) -> None:
            captured["tools"] = tools

    monkeypatch.setattr(bootstrap_module, "ToolRegistry", ToolRegistryStub)

    runtime = bootstrap_module.bootstrap()

    assert set(captured["tools"]) == {"code_formatter", "package_installer", "syntax_checker"}
    assert runtime.tool_service == "tool_service"