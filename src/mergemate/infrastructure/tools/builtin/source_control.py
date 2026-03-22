"""Source control tools backed by installed CLIs such as git, gh, and glab."""

from __future__ import annotations

from pathlib import Path
import subprocess


class _BaseCliTool:
    def __init__(self, executable: str, working_directory: Path) -> None:
        self._executable = executable
        self._working_directory = working_directory

    def _run(self, args: list[str]) -> dict[str, str]:
        completed = subprocess.run(
            [self._executable, *args],
            cwd=self._working_directory,
            capture_output=True,
            text=True,
            check=False,
        )
        output = completed.stdout.strip() or completed.stderr.strip()
        if completed.returncode != 0:
            return {"status": "error", "detail": output or f"{self._executable} command failed"}
        return {"status": "ok", "detail": output}


class GitRepositoryTool(_BaseCliTool):
    name = "git_repository"

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        action = payload.get("action", "status")
        command_map = {
            "status": ["status", "--short", "--branch"],
            "branch": ["branch", "--show-current"],
            "remotes": ["remote", "-v"],
            "diff_summary": ["diff", "--stat"],
        }
        args = command_map.get(action)
        if args is None:
            return {"status": "error", "detail": f"Unsupported git action: {action}"}
        return self._run(args)


class GitHubCliTool(_BaseCliTool):
    name = "github_cli"

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        action = payload.get("action", "repo_view")
        command_map = {
            "auth_status": ["auth", "status"],
            "repo_view": ["repo", "view"],
            "pr_status": ["pr", "status"],
        }
        args = command_map.get(action)
        if args is None:
            return {"status": "error", "detail": f"Unsupported GitHub action: {action}"}
        return self._run(args)


class GitLabCliTool(_BaseCliTool):
    name = "gitlab_cli"

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        action = payload.get("action", "repo_view")
        command_map = {
            "auth_status": ["auth", "status"],
            "repo_view": ["repo", "view"],
            "mr_status": ["mr", "status"],
        }
        args = command_map.get(action)
        if args is None:
            return {"status": "error", "detail": f"Unsupported GitLab action: {action}"}
        return self._run(args)