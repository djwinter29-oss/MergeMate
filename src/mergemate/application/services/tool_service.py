"""Tool selection and invocation service."""


class ToolService:
    def __init__(self, tool_registry, settings) -> None:
        self._tool_registry = tool_registry
        self._settings = settings

    def list_enabled_tools(self, agent_name: str) -> list[str]:
        agent = self._settings.agents.get(agent_name)
        if agent is None:
            return []
        return [tool_name for tool_name in agent.tools if self._tool_registry.get_tool(tool_name) is not None]

    def install_package(self, package_name: str) -> dict[str, str]:
        installer = self._tool_registry.get_tool("package_installer")
        if installer is None:
            return {"status": "blocked", "detail": "Package installer tool is not available."}
        return installer.invoke({"package_name": package_name})

    def get_repository_context(self, platform: str | None = None) -> dict[str, dict[str, str]]:
        context: dict[str, dict[str, str]] = {}

        git_tool = self._tool_registry.get_tool("git_repository")
        if git_tool is not None:
            context["git"] = git_tool.invoke({"action": "status"})

        platform_name = platform or self._settings.source_control.default_platform
        tool_name_by_platform = {
            "github": "github_cli",
            "gitlab": "gitlab_cli",
        }
        tool_name = tool_name_by_platform.get(platform_name)
        if tool_name is not None:
            platform_tool = self._tool_registry.get_tool(tool_name)
            if platform_tool is not None:
                action = "repo_view" if platform_name == "github" else "repo_view"
                context[platform_name] = platform_tool.invoke({"action": action})

        return context

    def get_platform_auth_status(self, platform: str) -> dict[str, str]:
        tool_name_by_platform = {
            "github": "github_cli",
            "gitlab": "gitlab_cli",
        }
        tool_name = tool_name_by_platform.get(platform)
        if tool_name is None:
            return {"status": "error", "detail": f"Unsupported platform: {platform}"}
        tool = self._tool_registry.get_tool(tool_name)
        if tool is None:
            return {"status": "blocked", "detail": f"Platform tool {tool_name} is not enabled."}
        return tool.invoke({"action": "auth_status"})