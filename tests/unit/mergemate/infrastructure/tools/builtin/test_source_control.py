from pathlib import Path

from mergemate.infrastructure.tools.builtin.source_control import (
    GitHubCliTool,
    GitLabCliTool,
    GitRepositoryTool,
)


def test_git_repository_tool_rejects_unknown_action() -> None:
    tool = GitRepositoryTool("git", Path("."))

    result = tool.invoke({"action": "unknown"})

    assert result["status"] == "error"


def test_github_cli_tool_rejects_unknown_action() -> None:
    tool = GitHubCliTool("gh", Path("."))

    result = tool.invoke({"action": "unknown"})

    assert result["status"] == "error"


def test_gitlab_cli_tool_rejects_unknown_action() -> None:
    tool = GitLabCliTool("glab", Path("."))

    result = tool.invoke({"action": "unknown"})

    assert result["status"] == "error"