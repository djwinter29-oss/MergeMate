from dataclasses import dataclass

from mergemate.application.services.tool_service import ToolService


class ToolStub:
    def __init__(self, response: dict[str, str]) -> None:
        self._response = response

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        return self._response


class RegistryStub:
    def __init__(self, mapping: dict[str, object]) -> None:
        self._mapping = mapping

    def get_tool(self, name: str):
        return self._mapping.get(name)


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


def test_get_repository_context_uses_git_and_default_platform() -> None:
    service = ToolService(
        RegistryStub(
            {
                "git_repository": ToolStub({"status": "ok", "detail": "git status"}),
                "github_cli": ToolStub({"status": "ok", "detail": "gh repo view"}),
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
                "git_repository": ToolStub({"status": "ok", "detail": "git status"}),
                "gitlab_cli": ToolStub({"status": "ok", "detail": "glab repo view"}),
            }
        ),
        SettingsStub(source_control=SourceControlConfigStub(default_platform="github"), agents={}),
    )

    context = service.get_repository_context("gitlab")

    assert context["gitlab"]["detail"] == "glab repo view"


def test_get_platform_auth_status_blocks_when_tool_missing() -> None:
    service = ToolService(RegistryStub({}), SettingsStub(source_control=SourceControlConfigStub(), agents={}))

    result = service.get_platform_auth_status("github")

    assert result["status"] == "blocked"