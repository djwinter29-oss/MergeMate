from dataclasses import dataclass

from mergemate.application.services.tool_service import ToolService
from mergemate.domain.tools.entities import ToolMetadata


class ToolStub:
    def __init__(self, response: dict[str, str], metadata: ToolMetadata | None = None) -> None:
        self._response = response
        self.metadata = metadata
        self.payloads = []

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        self.payloads.append(payload)
        return self._response


class RegistryStub:
    def __init__(self, mapping: dict[str, object]) -> None:
        self._mapping = mapping
        self._listed_tools = list(mapping)

    def get_tool(self, name: str):
        return self._mapping.get(name)

    def get_tool_metadata(self, name: str):
        tool = self.get_tool(name)
        if tool is None:
            return None
        return getattr(tool, "metadata", None)

    def list_tools(self):
        return list(self._listed_tools)


@dataclass(slots=True)
class SourceControlConfigStub:
    default_platform: str = "github"


@dataclass(slots=True)
class AgentConfigStub:
    tools: list[str]


@dataclass(slots=True)
class SettingsStub:
    source_control: SourceControlConfigStub
    agents: dict[str, AgentConfigStub]


@dataclass(slots=True)
class ToolEventRepositoryStub:
    events: list[dict[str, str]]

    def record(self, **payload) -> None:
        self.events.append(payload)


class RunRepositoryStub:
    def __init__(self) -> None:
        self.transitions = []

    def update_status(self, run_id, status, *, current_stage=None, result_text=None, error_text=None):
        self.transitions.append((run_id, status.value, current_stage))


def test_get_repository_context_uses_git_and_default_platform() -> None:
    service = ToolService(
        RegistryStub(
            {
                "git_repository": ToolStub(
                    {"status": "ok", "detail": "git status"},
                    ToolMetadata(
                        name="git_repository",
                        runtime_mode="context",
                        default_action="status",
                        read_only=True,
                        context_key="git",
                    ),
                ),
                "github_cli": ToolStub(
                    {"status": "ok", "detail": "gh repo view"},
                    ToolMetadata(
                        name="github_cli",
                        runtime_mode="context",
                        default_action="repo_view",
                        read_only=True,
                        context_key="github",
                        platform="github",
                        auth_action="auth_status",
                    ),
                ),
            }
        ),
        SettingsStub(source_control=SourceControlConfigStub(), agents={}),
    )

    context = service.get_repository_context()

    assert context["git"]["detail"] == "git status"
    assert context["github"]["detail"] == "gh repo view"


def test_get_platform_auth_status_rejects_unknown_platform() -> None:
    service = ToolService(RegistryStub({}), SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    result = service.get_platform_auth_status("bitbucket")

    assert result["status"] == "error"


def test_list_enabled_tools_returns_only_registered_tools() -> None:
    service = ToolService(
        RegistryStub(
            {
                "syntax_checker": ToolStub({"status": "ok", "detail": "syntax ok"}),
                "code_formatter": ToolStub({"status": "ok", "detail": "formatted"}),
            }
        ),
        SettingsStub(
            source_control=SourceControlConfigStub(),
            agents={"coder": AgentConfigStub(tools=["syntax_checker", "code_formatter", "missing_tool"])} ,
        ),
    )

    result = service.list_enabled_tools("coder")

    assert result == ["syntax_checker", "code_formatter"]


def test_install_package_returns_blocked_when_tool_missing() -> None:
    service = ToolService(RegistryStub({}), SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    result = service.install_package("requests")

    assert result["status"] == "blocked"


def test_get_repository_context_uses_explicit_platform_when_available() -> None:
    service = ToolService(
        RegistryStub(
            {
                "git_repository": ToolStub(
                    {"status": "ok", "detail": "git status"},
                    ToolMetadata(
                        name="git_repository",
                        runtime_mode="context",
                        default_action="status",
                        read_only=True,
                        context_key="git",
                    ),
                ),
                "gitlab_cli": ToolStub(
                    {"status": "ok", "detail": "glab repo view"},
                    ToolMetadata(
                        name="gitlab_cli",
                        runtime_mode="context",
                        default_action="repo_view",
                        read_only=True,
                        context_key="gitlab",
                        platform="gitlab",
                        auth_action="auth_status",
                    ),
                ),
            }
        ),
        SettingsStub(source_control=SourceControlConfigStub(default_platform="github"), agents={}),
    )

    context = service.get_repository_context("gitlab")

    assert context["gitlab"]["detail"] == "glab repo view"


def test_get_platform_auth_status_blocks_when_tool_missing() -> None:
    service = ToolService(RegistryStub({}), SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    result = service.get_platform_auth_status("github")

    assert result["status"] == "error"


def test_list_enabled_tools_returns_empty_for_unknown_agent() -> None:
    service = ToolService(RegistryStub({}), SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    assert service.list_enabled_tools("missing") == []


def test_install_package_uses_installer_when_available() -> None:
    service = ToolService(
        RegistryStub({"package_installer": ToolStub({"status": "installed", "detail": "ok"})}),
        SettingsStub(source_control=SourceControlConfigStub(), agents={}),
    )

    assert service.install_package("requests") == {"status": "installed", "detail": "ok"}


def test_get_platform_auth_status_uses_platform_tool_when_available() -> None:
    service = ToolService(
        RegistryStub(
            {
                "github_cli": ToolStub(
                    {"status": "ok", "detail": "authenticated"},
                    ToolMetadata(
                        name="github_cli",
                        runtime_mode="context",
                        default_action="repo_view",
                        read_only=True,
                        context_key="github",
                        platform="github",
                        auth_action="auth_status",
                    ),
                )
            }
        ),
        SettingsStub(source_control=SourceControlConfigStub(), agents={}),
    )

    assert service.get_platform_auth_status("github") == {"status": "ok", "detail": "authenticated"}


def test_execute_enabled_tool_rejects_unconfigured_or_missing_tools() -> None:
    service = ToolService(
        RegistryStub({}),
        SettingsStub(source_control=SourceControlConfigStub(), agents={"coder": AgentConfigStub(tools=["syntax_checker"])}),
    )

    assert service.execute_enabled_tool("coder", "package_installer", {"package_name": "requests"})["status"] == "blocked"
    assert service.execute_enabled_tool("coder", "syntax_checker", {"source": "x = 1"})["status"] == "blocked"


def test_execute_enabled_tool_invokes_tool_when_enabled() -> None:
    tool = ToolStub(
        {"status": "ok", "detail": "done"},
        ToolMetadata(
            name="syntax_checker",
            runtime_mode="manual",
            read_only=True,
            blocks_run_state="waiting_tool",
        ),
    )
    service = ToolService(
        RegistryStub({"syntax_checker": tool}),
        SettingsStub(source_control=SourceControlConfigStub(), agents={"coder": AgentConfigStub(tools=["syntax_checker"])}),
    )

    result = service.execute_enabled_tool("coder", "syntax_checker", {"source": "x = 1"})

    assert result == {"status": "ok", "detail": "done"}
    assert tool.payloads == [{"source": "x = 1"}]


def test_build_runtime_tool_context_includes_enabled_tools_and_read_only_outputs() -> None:
    git_tool = ToolStub(
        {"status": "ok", "detail": "main"},
        ToolMetadata(
            name="git_repository",
            runtime_mode="context",
            default_action="status",
            read_only=True,
            context_key="git",
            blocks_run_state="waiting_tool",
        ),
    )
    formatter_tool = ToolStub(
        {"status": "ok", "detail": "formatted"},
        ToolMetadata(name="code_formatter", runtime_mode="manual", read_only=True),
    )
    service = ToolService(
        RegistryStub({"git_repository": git_tool, "code_formatter": formatter_tool}),
        SettingsStub(
            source_control=SourceControlConfigStub(),
            agents={"coder": AgentConfigStub(tools=["git_repository", "code_formatter"])},
        ),
    )

    context = service.build_runtime_tool_context("run-1", "coder")

    assert "Enabled runtime tools:" in context
    assert "- git_repository" in context
    assert "- code_formatter" in context
    assert "git (ok):" in context
    assert "main" in context
    assert git_tool.payloads == [{"action": "status"}]
    assert formatter_tool.payloads == []


def test_build_runtime_tool_context_returns_empty_for_agent_without_enabled_tools() -> None:
    service = ToolService(
        RegistryStub({}),
        SettingsStub(source_control=SourceControlConfigStub(), agents={"coder": AgentConfigStub(tools=[])}),
    )

    assert service.build_runtime_tool_context("run-1", "coder") == ""


def test_execute_enabled_tool_records_tool_events_and_waiting_state() -> None:
    tool = ToolStub(
        {"status": "ok", "detail": "done"},
        ToolMetadata(
            name="syntax_checker",
            runtime_mode="manual",
            read_only=True,
            blocks_run_state="waiting_tool",
        ),
    )
    run_repository = RunRepositoryStub()
    tool_event_repository = ToolEventRepositoryStub(events=[])
    service = ToolService(
        RegistryStub({"syntax_checker": tool}),
        SettingsStub(source_control=SourceControlConfigStub(), agents={"coder": AgentConfigStub(tools=["syntax_checker"])}),
        run_repository=run_repository,
        tool_event_repository=tool_event_repository,
    )

    result = service.execute_enabled_tool(
        "coder",
        "syntax_checker",
        {"action": "check", "source": "x = 1"},
        run_id="run-1",
        resume_stage="implementation",
    )

    assert result == {"status": "ok", "detail": "done"}
    assert run_repository.transitions == [
        ("run-1", "waiting_tool", "tool:syntax_checker"),
        ("run-1", "running", "implementation"),
    ]
    assert tool_event_repository.events == [
        {
            "run_id": "run-1",
            "tool_name": "syntax_checker",
            "action": "check",
            "status": "started",
            "detail": "Invoking tool.",
        },
        {
            "run_id": "run-1",
            "tool_name": "syntax_checker",
            "action": "check",
            "status": "ok",
            "detail": "done",
        },
    ]


def test_get_repository_context_skips_listed_tools_without_instances() -> None:
    registry = RegistryStub({})
    registry._listed_tools = ["git_repository"]
    service = ToolService(registry, SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    assert service.get_repository_context() == {}


def test_get_repository_context_skips_tool_when_metadata_exists_but_instance_missing() -> None:
    registry = RegistryStub({})
    registry._listed_tools = ["git_repository"]
    registry.get_tool_metadata = lambda name: ToolMetadata(
        name="git_repository",
        runtime_mode="context",
        default_action="status",
        read_only=True,
        context_key="git",
    )
    service = ToolService(registry, SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    assert service.get_repository_context() == {}


def test_get_repository_context_skips_tools_without_context_metadata() -> None:
    service = ToolService(
        RegistryStub({"syntax_checker": ToolStub({"status": "ok", "detail": "unused"})}),
        SettingsStub(source_control=SourceControlConfigStub(), agents={}),
    )

    assert service.get_repository_context() == {}


def test_get_platform_auth_status_blocks_when_platform_metadata_has_no_action() -> None:
    service = ToolService(
        RegistryStub(
            {
                "github_cli": ToolStub(
                    {"status": "ok", "detail": "unused"},
                    ToolMetadata(
                        name="github_cli",
                        runtime_mode="context",
                        default_action="repo_view",
                        read_only=True,
                        context_key="github",
                        platform="github",
                    ),
                )
            }
        ),
        SettingsStub(source_control=SourceControlConfigStub(), agents={}),
    )

    result = service.get_platform_auth_status("github")

    assert result == {"status": "blocked", "detail": "Platform tool for github is not enabled."}


def test_get_platform_auth_status_skips_other_platform_metadata() -> None:
    service = ToolService(
        RegistryStub(
            {
                "gitlab_cli": ToolStub(
                    {"status": "ok", "detail": "authenticated"},
                    ToolMetadata(
                        name="gitlab_cli",
                        runtime_mode="context",
                        default_action="repo_view",
                        read_only=True,
                        context_key="gitlab",
                        platform="gitlab",
                        auth_action="auth_status",
                    ),
                )
            }
        ),
        SettingsStub(source_control=SourceControlConfigStub(), agents={}),
    )

    result = service.get_platform_auth_status("github")

    assert result == {"status": "error", "detail": "Unsupported platform: github"}


def test_get_platform_auth_status_blocks_when_metadata_exists_but_tool_missing() -> None:
    registry = RegistryStub({})
    registry._listed_tools = ["github_cli"]
    registry.get_tool_metadata = lambda name: ToolMetadata(
        name="github_cli",
        runtime_mode="context",
        default_action="repo_view",
        read_only=True,
        context_key="github",
        platform="github",
        auth_action="auth_status",
    )
    service = ToolService(registry, SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    result = service.get_platform_auth_status("github")

    assert result == {"status": "blocked", "detail": "Platform tool github_cli is not enabled."}