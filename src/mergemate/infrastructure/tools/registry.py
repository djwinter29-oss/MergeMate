"""Tool registry."""


class ToolRegistry:
    def __init__(self, tools: dict[str, object]) -> None:
        self._tools = tools

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_tool(self, name: str):
        return self._tools.get(name)

    def get_tool_metadata(self, name: str):
        tool = self.get_tool(name)
        if tool is None:
            return None
        return getattr(tool, "metadata", None)