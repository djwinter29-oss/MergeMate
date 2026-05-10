from pathlib import Path
from types import SimpleNamespace

from mergemate.infrastructure.tools.registry import ToolRegistry, ToolRegistryBuilder


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def record(self, name: str, *args: object, **kwargs: object) -> None:
        self.calls.append((name, args, kwargs))


class _NamedTool:
    def __init__(self, name: str, recorder: _Recorder) -> None:
        self.name = name
        self.recorder = recorder


class _PathTool:
    def __init__(self, label: str, recorder: _Recorder, *args: object) -> None:
        recorder.record(label, *args)
        self.label = label


class _PackageInstallerTool:
    def __init__(self, recorder: _Recorder, **kwargs: object) -> None:
        recorder.record("package_installer", **kwargs)
        self.label = "package_installer"


def _make_settings(*, enable_git: bool, enable_github: bool, enable_gitlab: bool) -> SimpleNamespace:
    return SimpleNamespace(
        tools=SimpleNamespace(
            allow_package_install=True,
            allowed_packages=["requests"],
            pip_executable="python3",
        ),
        runtime=SimpleNamespace(default_request_timeout_seconds=45),
        source_control=SimpleNamespace(
            enable_git=enable_git,
            enable_github=enable_github,
            enable_gitlab=enable_gitlab,
            git_executable="git",
            github_executable="gh",
            gitlab_executable="glab",
        ),
    )


def test_tool_registry_builder_registers_permanent_and_conditional_tools_with_working_directory(monkeypatch) -> None:
    recorder = _Recorder()
    working_directory = Path("/workspace/repo")
    settings = _make_settings(enable_git=True, enable_github=True, enable_gitlab=True)

    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.code_formatter.CodeFormatterTool",
        lambda: _NamedTool("code_formatter", recorder),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.package_installer.PackageInstallerTool",
        lambda **kwargs: _PackageInstallerTool(recorder, **kwargs),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.syntax_checker.SyntaxCheckerTool",
        lambda: _NamedTool("syntax_checker", recorder),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.source_control.GitRepositoryTool",
        lambda executable, working_directory, timeout_seconds: _PathTool(
            "git_repository",
            recorder,
            executable,
            working_directory,
            timeout_seconds,
        ),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.source_control.GitHubCliTool",
        lambda executable, working_directory, timeout_seconds: _PathTool(
            "github_cli",
            recorder,
            executable,
            working_directory,
            timeout_seconds,
        ),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.source_control.GitLabCliTool",
        lambda executable, working_directory, timeout_seconds: _PathTool(
            "gitlab_cli",
            recorder,
            executable,
            working_directory,
            timeout_seconds,
        ),
    )

    builder = ToolRegistryBuilder(settings, working_directory=working_directory)
    registry = builder.with_git().with_github_cli().with_gitlab_cli().build()

    assert isinstance(registry, ToolRegistry)
    assert registry.list_tools() == [
        "code_formatter",
        "git_repository",
        "github_cli",
        "gitlab_cli",
        "package_installer",
        "syntax_checker",
    ]
    assert registry.get_tool("code_formatter").name == "code_formatter"
    assert registry.get_tool("syntax_checker").name == "syntax_checker"
    assert registry.get_tool("package_installer").label == "package_installer"
    assert registry.get_tool("git_repository").label == "git_repository"
    assert registry.get_tool("github_cli").label == "github_cli"
    assert registry.get_tool("gitlab_cli").label == "gitlab_cli"

    assert recorder.calls == [
        ("package_installer", (), {"allow_package_install": True, "allowed_packages": ["requests"], "pip_executable": "python3", "timeout_seconds": 45}),
        ("git_repository", ("git", working_directory, 45), {}),
        ("github_cli", ("gh", working_directory, 45), {}),
        ("gitlab_cli", ("glab", working_directory, 45), {}),
    ]


def test_tool_registry_builder_skips_conditional_tools_when_flags_disabled(monkeypatch) -> None:
    recorder = _Recorder()
    working_directory = Path("/workspace/repo")
    settings = _make_settings(enable_git=False, enable_github=False, enable_gitlab=False)

    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.code_formatter.CodeFormatterTool",
        lambda: _NamedTool("code_formatter", recorder),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.package_installer.PackageInstallerTool",
        lambda **kwargs: _PackageInstallerTool(recorder, **kwargs),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.syntax_checker.SyntaxCheckerTool",
        lambda: _NamedTool("syntax_checker", recorder),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.source_control.GitRepositoryTool",
        lambda *args, **kwargs: _PathTool("git_repository", recorder, args, kwargs),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.source_control.GitHubCliTool",
        lambda *args, **kwargs: _PathTool("github_cli", recorder, args, kwargs),
    )
    monkeypatch.setattr(
        "mergemate.infrastructure.tools.builtin.source_control.GitLabCliTool",
        lambda *args, **kwargs: _PathTool("gitlab_cli", recorder, args, kwargs),
    )

    registry = ToolRegistryBuilder(settings, working_directory=working_directory).build()

    assert registry.list_tools() == ["code_formatter", "package_installer", "syntax_checker"]
    assert registry.get_tool("git_repository") is None
    assert registry.get_tool("github_cli") is None
    assert registry.get_tool("gitlab_cli") is None
    assert [call[0] for call in recorder.calls] == ["package_installer"]
