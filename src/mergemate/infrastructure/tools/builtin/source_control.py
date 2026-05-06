"""Source control tools backed by installed CLIs such as git, gh, and glab."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import ClassVar

from mergemate.domain.tools.entities import ToolMetadata


class _BaseCliTool:
    _default_action: ClassVar[str]
    _command_map: ClassVar[dict[str, list[str]]]
    _unsupported_action_label: ClassVar[str]

    def __init__(self, executable: str, working_directory: Path, timeout_seconds: int) -> None:
        self._executable = executable
        self._working_directory = working_directory
        self._timeout_seconds = timeout_seconds

    def _run(self, args: list[str]) -> dict[str, str]:
        try:
            completed = subprocess.run(
                [self._executable, *args],
                cwd=self._working_directory,
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError:
            return {
                "status": "error",
                "detail": f"Executable {self._executable} was not found.",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "detail": f"{self._executable} command timed out after {self._timeout_seconds}s.",
            }
        output = completed.stdout.strip() or completed.stderr.strip()
        if completed.returncode != 0:
            return {"status": "error", "detail": output or f"{self._executable} command failed"}
        return {"status": "ok", "detail": output}

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        action = payload.get("action", self._default_action)
        args = self._command_map.get(action)
        if args is None:
            return {"status": "error", "detail": f"Unsupported {self._unsupported_action_label} action: {action}"}
        return self._run(args)


class GitRepositoryTool(_BaseCliTool):
    name = "git_repository"
    metadata = ToolMetadata(
        name=name,
        runtime_mode="context",
        default_action="status",
        read_only=True,
        blocks_run_state="waiting_tool",
        context_key="git",
    )
    _default_action = "status"
    _unsupported_action_label = "git"
    _command_map = {
        "status": ["status", "--short", "--branch"],
        "branch": ["branch", "--show-current"],
        "remotes": ["remote", "-v"],
        "diff_summary": ["diff", "--stat"],
    }


class GitHubCliTool(_BaseCliTool):
    name = "github_cli"
    metadata = ToolMetadata(
        name=name,
        runtime_mode="context",
        default_action="repo_view",
        read_only=True,
        blocks_run_state="waiting_tool",
        context_key="github",
        auth_action="auth_status",
        platform="github",
    )
    _default_action = "repo_view"
    _unsupported_action_label = "GitHub"
    _command_map = {
        "auth_status": ["auth", "status"],
        "repo_view": ["repo", "view"],
        "pr_status": ["pr", "status"],
    }


class GitLabCliTool(_BaseCliTool):
    name = "gitlab_cli"
    metadata = ToolMetadata(
        name=name,
        runtime_mode="context",
        default_action="repo_view",
        read_only=True,
        blocks_run_state="waiting_tool",
        context_key="gitlab",
        auth_action="auth_status",
        platform="gitlab",
    )
    _default_action = "repo_view"
    _unsupported_action_label = "GitLab"
    _command_map = {
        "auth_status": ["auth", "status"],
        "repo_view": ["repo", "view"],
        "mr_status": ["mr", "status"],
    }

