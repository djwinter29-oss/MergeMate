from pathlib import Path

from mergemate.domain.tools import ToolInvoker
from mergemate.domain.tools.entities import ToolMetadata
from mergemate.infrastructure.tools.registry import ToolRegistry


def test_tool_registry_lists_sorted_tools_and_gets_by_name() -> None:
    class _ToolStub:
        name = "stub"
        metadata = ToolMetadata(name="stub")

        def invoke(self, payload: dict[str, str]) -> dict[str, str]:
            return {"status": "ok", "detail": payload.get("action", "")}

    registry = ToolRegistry({"b": _ToolStub(), "a": _ToolStub()})

    assert registry.list_tools() == ["a", "b"]
    assert registry.get_tool("a") is not None
    assert registry.get_tool("missing") is None


def test_tool_registry_returns_tool_metadata_when_available() -> None:
    class _ToolStub:
        name = "stub"
        metadata = ToolMetadata(name="git_repository", runtime_mode="context")

        def invoke(self, payload: dict[str, str]) -> dict[str, str]:
            return {"status": "ok", "detail": payload.get("action", "")}

    registry = ToolRegistry({"git_repository": _ToolStub()})

    assert registry.get_tool_metadata("git_repository") == ToolMetadata(
        name="git_repository",
        runtime_mode="context",
    )
    assert registry.get_tool_metadata("missing") is None


def test_tool_protocol_matches_built_in_tools() -> None:
    from mergemate.infrastructure.tools.builtin.code_formatter import CodeFormatterTool
    from mergemate.infrastructure.tools.builtin.package_installer import PackageInstallerTool
    from mergemate.infrastructure.tools.builtin.source_control import (
        GitHubCliTool,
        GitLabCliTool,
        GitRepositoryTool,
    )
    from mergemate.infrastructure.tools.builtin.syntax_checker import SyntaxCheckerTool

    tools = [
        CodeFormatterTool(),
        SyntaxCheckerTool(),
        PackageInstallerTool(
            allow_package_install=False,
            allowed_packages=[],
            pip_executable="pip",
            timeout_seconds=1,
        ),
        GitRepositoryTool("git", Path("."), 1),
        GitHubCliTool("gh", Path("."), 1),
        GitLabCliTool("glab", Path("."), 1),
    ]

    assert all(isinstance(tool, ToolInvoker) for tool in tools)
