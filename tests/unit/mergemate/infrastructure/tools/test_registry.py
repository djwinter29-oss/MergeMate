from mergemate.domain.tools.entities import ToolMetadata
from mergemate.infrastructure.tools.registry import ToolRegistry


def test_tool_registry_lists_sorted_tools_and_gets_by_name() -> None:
    registry = ToolRegistry({"b": object(), "a": object()})

    assert registry.list_tools() == ["a", "b"]
    assert registry.get_tool("a") is not None
    assert registry.get_tool("missing") is None


def test_tool_registry_returns_tool_metadata_when_available() -> None:
    tool = type(
        "ToolWithMetadata",
        (),
        {"metadata": ToolMetadata(name="git_repository", runtime_mode="context")},
    )()
    registry = ToolRegistry({"git_repository": tool})

    assert registry.get_tool_metadata("git_repository") == ToolMetadata(
        name="git_repository",
        runtime_mode="context",
    )
    assert registry.get_tool_metadata("missing") is None
