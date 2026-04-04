from pathlib import Path
import subprocess

from mergemate.infrastructure.tools.builtin.source_control import (
    GitHubCliTool,
    GitLabCliTool,
    GitRepositoryTool,
)


def test_git_repository_tool_rejects_unknown_action() -> None:
    tool = GitRepositoryTool("git", Path("."), 30)

    result = tool.invoke({"action": "unknown"})

    assert result["status"] == "error"


def test_github_cli_tool_rejects_unknown_action() -> None:
    tool = GitHubCliTool("gh", Path("."), 30)

    result = tool.invoke({"action": "unknown"})

    assert result["status"] == "error"


def test_gitlab_cli_tool_rejects_unknown_action() -> None:
    tool = GitLabCliTool("glab", Path("."), 30)

    result = tool.invoke({"action": "unknown"})

    assert result["status"] == "error"


def test_cli_tools_run_expected_commands_and_surface_errors(monkeypatch) -> None:
    calls = []

    def fake_run(command, cwd, capture_output, text, check, timeout):
        calls.append((command, cwd))
        if command[0] == "glab":
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="denied")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    cwd = Path("/tmp/repo")

    git_result = GitRepositoryTool("git", cwd, 30).invoke({"action": "branch"})
    github_result = GitHubCliTool("gh", cwd, 30).invoke({"action": "auth_status"})
    gitlab_result = GitLabCliTool("glab", cwd, 30).invoke({"action": "mr_status"})

    assert git_result == {"status": "ok", "detail": "ok"}
    assert github_result == {"status": "ok", "detail": "ok"}
    assert gitlab_result == {"status": "error", "detail": "denied"}
    assert calls == [
        (["git", "branch", "--show-current"], cwd),
        (["gh", "auth", "status"], cwd),
        (["glab", "mr", "status"], cwd),
    ]


def test_git_repository_tool_uses_all_supported_actions(monkeypatch) -> None:
    commands = []

    def fake_run(command, cwd, capture_output, text, check, timeout):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    tool = GitRepositoryTool("git", Path("."), 30)

    tool.invoke({"action": "status"})
    tool.invoke({"action": "remotes"})
    tool.invoke({"action": "diff_summary"})

    assert commands == [
        ["git", "status", "--short", "--branch"],
        ["git", "remote", "-v"],
        ["git", "diff", "--stat"],
    ]


def test_cli_tools_surface_missing_executables(monkeypatch) -> None:
    def fake_run(command, cwd, capture_output, text, check, timeout):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    git_result = GitRepositoryTool("git", Path("."), 30).invoke({"action": "status"})
    github_result = GitHubCliTool("gh", Path("."), 30).invoke({"action": "auth_status"})
    gitlab_result = GitLabCliTool("glab", Path("."), 30).invoke({"action": "mr_status"})

    assert git_result == {"status": "error", "detail": "Executable git was not found."}
    assert github_result == {"status": "error", "detail": "Executable gh was not found."}
    assert gitlab_result == {"status": "error", "detail": "Executable glab was not found."}


def test_cli_tools_surface_timeout(monkeypatch) -> None:
    def fake_run(command, cwd, capture_output, text, check, timeout):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    git_result = GitRepositoryTool("git", Path("."), 12).invoke({"action": "status"})

    assert git_result == {"status": "error", "detail": "git command timed out after 12s."}