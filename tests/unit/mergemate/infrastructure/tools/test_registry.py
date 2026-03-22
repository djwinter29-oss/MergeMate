from mergemate.infrastructure.tools.registry import ToolRegistry


def test_tool_registry_lists_sorted_tools_and_gets_by_name() -> None:
    registry = ToolRegistry({"b": object(), "a": object()})

    assert registry.list_tools() == ["a", "b"]
    assert registry.get_tool("a") is not None
    assert registry.get_tool("missing") is None
