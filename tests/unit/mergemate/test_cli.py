from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from mergemate import cli


runner = CliRunner()


class ToolServiceStub:
    def __init__(self, *, install_result=None, context_result=None, auth_result=None) -> None:
        self.install_result = install_result or {"status": "installed", "detail": "installed ok"}
        self.context_result = context_result or {"git": {"status": "ok", "detail": "git detail"}}
        self.auth_result = auth_result or {"status": "ok", "detail": "auth ok"}

    def install_package(self, package_name: str):
        return self.install_result

    def get_repository_context(self, platform: str | None = None):
        return self.context_result

    def get_platform_auth_status(self, platform: str):
        return self.auth_result


def _runtime(tool_service=None):
    return SimpleNamespace(
        settings=SimpleNamespace(default_provider="openai", default_agent="coder"),
        database=SimpleNamespace(path=Path("/tmp/runtime.db")),
        tool_service=tool_service or ToolServiceStub(),
    )


def test_run_bot_prints_config_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    observed = {"ran": False}

    class BotRuntimeStub:
        def __init__(self, runtime) -> None:
            self.runtime = runtime

        def run_polling(self) -> None:
            observed["ran"] = True

    monkeypatch.setattr(cli, "bootstrap", lambda config: _runtime())
    monkeypatch.setattr(cli, "TelegramBotRuntime", BotRuntimeStub)

    result = runner.invoke(cli.app, ["run-bot"])

    assert result.exit_code == 0
    assert "MergeMate configured for provider=openai agent=coder" in result.stdout
    assert observed["ran"] is True


def test_validate_config_prints_resolved_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "resolve_config_path", lambda config: Path("/tmp/config.yaml"))
    monkeypatch.setattr(cli, "bootstrap", lambda config: _runtime())

    result = runner.invoke(cli.app, ["validate-config"])

    assert result.exit_code == 0
    assert "Configuration is valid: /tmp/config.yaml" in result.stdout
    assert "Resolved database path: /tmp/runtime.db" in result.stdout


def test_print_config_path_outputs_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "DEFAULT_LOCAL_CONFIG_PATH", Path("/tmp/default.yaml"))

    result = runner.invoke(cli.app, ["print-config-path"])

    assert result.exit_code == 0
    assert "/tmp/default.yaml" in result.stdout


def test_install_package_exits_nonzero_for_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "bootstrap",
        lambda config: _runtime(ToolServiceStub(install_result={"status": "error", "detail": "failed"})),
    )

    result = runner.invoke(cli.app, ["install-package", "requests"])

    assert result.exit_code == 1
    assert "failed" in (result.stdout + result.stderr)


def test_install_package_allows_blocked_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "bootstrap",
        lambda config: _runtime(ToolServiceStub(install_result={"status": "blocked", "detail": "blocked"})),
    )

    result = runner.invoke(cli.app, ["install-package", "requests"])

    assert result.exit_code == 0
    assert "blocked" in result.stdout


def test_repo_context_prints_each_tool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "bootstrap",
        lambda config: _runtime(
            ToolServiceStub(context_result={"git": {"status": "ok", "detail": "git detail"}, "github": {"status": "error", "detail": "gh detail"}})
        ),
    )

    result = runner.invoke(cli.app, ["repo-context"])

    assert result.exit_code == 0
    assert "[git] ok" in result.stdout
    assert "git detail" in result.stdout
    assert "[github] error" in result.stdout
    assert "gh detail" in result.stdout


def test_platform_auth_exits_nonzero_for_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "bootstrap",
        lambda config: _runtime(ToolServiceStub(auth_result={"status": "error", "detail": "no auth"})),
    )

    result = runner.invoke(cli.app, ["platform-auth", "github"])

    assert result.exit_code == 1
    assert "no auth" in (result.stdout + result.stderr)


def test_platform_auth_prints_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "bootstrap", lambda config: _runtime())

    result = runner.invoke(cli.app, ["platform-auth", "github"])

    assert result.exit_code == 0
    assert "auth ok" in result.stdout
