# mypy: allow-untyped-defs
"""Tool registry and builder pattern."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mergemate.domain.tools import ToolInvoker

if TYPE_CHECKING:
    from pathlib import Path

    from mergemate.config.models import AppConfig


class ToolRegistry:
    def __init__(self, tools: dict[str, ToolInvoker]) -> None:
        self._tools = tools

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def get_tool(self, name: str) -> ToolInvoker | None:
        return self._tools.get(name)

    def get_tool_metadata(self, name: str):
        tool = self.get_tool(name)
        if tool is None:
            return None
        return getattr(tool, "metadata", None)


class ToolRegistryBuilder:
    """Builder pattern for constructing a ToolRegistry with conditional tools.

    Usage:
        builder = ToolRegistryBuilder(settings, working_directory=working_directory)
        if settings.source_control.enable_git:
            builder.with_git()
        if settings.source_control.enable_github:
            builder.with_github_cli()
        if settings.source_control.enable_gitlab:
            builder.with_gitlab_cli()
        tool_registry = builder.build()
    """

    def __init__(self, settings: AppConfig, working_directory: Path) -> None:
        from mergemate.infrastructure.tools.builtin.code_formatter import CodeFormatterTool
        from mergemate.infrastructure.tools.builtin.package_installer import PackageInstallerTool
        from mergemate.infrastructure.tools.builtin.syntax_checker import SyntaxCheckerTool

        self._tools: dict[str, ToolInvoker] = {
            "code_formatter": CodeFormatterTool(),
            "package_installer": PackageInstallerTool(
                allow_package_install=settings.tools.allow_package_install,
                allowed_packages=settings.tools.allowed_packages,
                pip_executable=settings.tools.pip_executable,
                timeout_seconds=settings.runtime.default_request_timeout_seconds,
            ),
            "syntax_checker": SyntaxCheckerTool(),
        }
        self._settings = settings
        self._working_directory = working_directory

    def with_git(self) -> ToolRegistryBuilder:
        from mergemate.infrastructure.tools.builtin.source_control import GitRepositoryTool

        self._tools["git_repository"] = GitRepositoryTool(
            self._settings.source_control.git_executable,
            self._working_directory,
            self._settings.runtime.default_request_timeout_seconds,
        )
        return self

    def with_github_cli(self) -> ToolRegistryBuilder:
        from mergemate.infrastructure.tools.builtin.source_control import GitHubCliTool

        self._tools["github_cli"] = GitHubCliTool(
            self._settings.source_control.github_executable,
            self._working_directory,
            self._settings.runtime.default_request_timeout_seconds,
        )
        return self

    def with_gitlab_cli(self) -> ToolRegistryBuilder:
        from mergemate.infrastructure.tools.builtin.source_control import GitLabCliTool

        self._tools["gitlab_cli"] = GitLabCliTool(
            self._settings.source_control.gitlab_executable,
            self._working_directory,
            self._settings.runtime.default_request_timeout_seconds,
        )
        return self

    def build(self) -> ToolRegistry:
        return ToolRegistry(self._tools)