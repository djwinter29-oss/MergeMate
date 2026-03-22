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