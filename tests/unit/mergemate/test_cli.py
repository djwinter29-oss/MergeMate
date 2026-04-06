from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

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

        def run(self) -> None:
            observed["ran"] = True

    monkeypatch.setattr(cli, "bootstrap", lambda config: _runtime())
    monkeypatch.setattr(cli, "TelegramBotRuntime", BotRuntimeStub)

    result = runner.invoke(cli.app, ["run-bot"])

    assert result.exit_code == 0
    assert "MergeMate configured for provider=openai agent=coder" in result.stdout
    assert observed["ran"] is True


def test_validate_config_prints_resolved_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "resolve_config_path", lambda config: Path("/tmp/config.yaml"))
    settings = SimpleNamespace(
        telegram=SimpleNamespace(mode="polling"),
        resolve_telegram_token=lambda: "token",
        resolve_provider_api_key=lambda provider_name=None: "provider-token",
        resolve_agent_provider_names=lambda agent_name: ["primary"],
        agents={"coder": SimpleNamespace()},
        preview_database_path=lambda resolved: Path("/tmp/runtime.db"),
    )
    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "bootstrap", lambda config: (_ for _ in ()).throw(AssertionError("bootstrap should not be called")))

    result = runner.invoke(cli.app, ["validate-config"])

    assert result.exit_code == 0
    assert "Configuration is valid: /tmp/config.yaml" in result.stdout
    assert "Resolved database path: /tmp/runtime.db" in result.stdout


def test_validate_config_resolves_webhook_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "resolve_config_path", lambda config: Path("/tmp/config.yaml"))
    settings = SimpleNamespace(
        telegram=SimpleNamespace(mode="webhook"),
        resolve_telegram_token=lambda: "token",
        resolve_telegram_webhook_url=lambda: "https://bot.example.com/telegram/webhook",
        resolve_telegram_webhook_secret_token=lambda: "secret",
        resolve_provider_api_key=lambda provider_name=None: "provider-token",
        resolve_agent_provider_names=lambda agent_name: ["primary"],
        agents={"coder": SimpleNamespace()},
        preview_database_path=lambda resolved: Path("/tmp/runtime.db"),
    )
    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)

    result = runner.invoke(cli.app, ["validate-config"])

    assert result.exit_code == 0


def test_validate_config_fails_for_missing_explicit_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "resolve_config_path", lambda config: (_ for _ in ()).throw(FileNotFoundError("Configuration file not found: /tmp/missing.yaml")))

    result = runner.invoke(cli.app, ["validate-config", "--config", "/tmp/missing.yaml"])

    assert result.exit_code != 0
    assert isinstance(result.exception, FileNotFoundError)


def test_validate_config_fails_when_telegram_token_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "resolve_config_path", lambda config: Path("/tmp/config.yaml"))
    settings = SimpleNamespace(
        telegram=SimpleNamespace(mode="polling"),
        resolve_telegram_token=lambda: (_ for _ in ()).throw(ValueError("Telegram bot token not found in environment variable TELEGRAM_TOKEN")),
        resolve_provider_api_key=lambda provider_name=None: "provider-token",
        resolve_agent_provider_names=lambda agent_name: ["primary"],
        agents={"coder": SimpleNamespace()},
        preview_database_path=lambda resolved: Path("/tmp/runtime.db"),
    )
    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)

    result = runner.invoke(cli.app, ["validate-config"])

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)


def test_validate_config_fails_when_provider_reference_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "resolve_config_path", lambda config: Path("/tmp/config.yaml"))
    settings = SimpleNamespace(
        telegram=SimpleNamespace(mode="polling"),
        resolve_telegram_token=lambda: "token",
        resolve_provider_api_key=lambda provider_name=None: "provider-token",
        resolve_agent_provider_names=lambda agent_name: (_ for _ in ()).throw(
            ValueError("Agent coder references unknown provider missing")
        ),
        agents={"coder": SimpleNamespace()},
        preview_database_path=lambda resolved: Path("/tmp/runtime.db"),
    )
    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)

    result = runner.invoke(cli.app, ["validate-config"])

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)


def test_print_config_path_outputs_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "resolve_config_path", lambda config=None: Path("/tmp/default.yaml"))

    result = runner.invoke(cli.app, ["print-config-path"])

    assert result.exit_code == 0
    assert "/tmp/default.yaml" in result.stdout


def test_probe_readiness_reports_ready_status(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )

    class ResponseStub:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"status": "ready"}'

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "urlopen", lambda url, timeout: ResponseStub())

    result = runner.invoke(cli.app, ["probe-readiness"])

    assert result.exit_code == 0
    assert '{"status": "ready"}' in result.stdout


def test_probe_readiness_fails_for_disabled_healthcheck(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=False,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)

    result = runner.invoke(cli.app, ["probe-readiness"])

    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)


def test_probe_readiness_fails_for_non_ready_status(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )

    class ResponseStub:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"status": "starting"}'

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "urlopen", lambda url, timeout: ResponseStub())

    result = runner.invoke(cli.app, ["probe-readiness"])

    assert result.exit_code == 1
    assert '{"status": "starting"}' in result.stdout


def test_probe_readiness_fails_for_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )

    class ErrorStub(HTTPError):
        def __init__(self) -> None:
            super().__init__("http://127.0.0.1:8081/healthz", 503, "Service Unavailable", hdrs=None, fp=None)

        def read(self) -> bytes:
            return b'{"status": "starting"}'

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "urlopen", lambda url, timeout: (_ for _ in ()).throw(ErrorStub()))

    result = runner.invoke(cli.app, ["probe-readiness"])

    assert result.exit_code == 1
    assert '{"status": "starting"}' in result.stdout


def test_probe_readiness_fails_for_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "urlopen", lambda url, timeout: (_ for _ in ()).throw(URLError("connection refused")))

    result = runner.invoke(cli.app, ["probe-readiness"])

    assert result.exit_code == 1
    assert "Readiness probe failed: connection refused" in (result.stdout + result.stderr)


def test_probe_readiness_waits_until_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )
    responses = [b'{"status": "starting"}', b'{"status": "ready"}']
    sleep_calls = []

    class ResponseStub:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    def fake_urlopen(url, timeout):
        return ResponseStub(responses.pop(0))

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = runner.invoke(cli.app, ["probe-readiness", "--wait", "--interval-seconds", "0.5"])

    assert result.exit_code == 0
    assert '{"status": "ready"}' in result.stdout
    assert sleep_calls == [0.5]


def test_probe_readiness_wait_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )
    monotonic_values = iter([0.0, 0.0, 0.6])
    sleep_calls = []

    class ResponseStub:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"status": "starting"}'

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "urlopen", lambda url, timeout: ResponseStub())
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(cli.time, "monotonic", lambda: next(monotonic_values))

    result = runner.invoke(
        cli.app,
        ["probe-readiness", "--wait", "--interval-seconds", "0.5", "--max-wait-seconds", "0.5"],
    )

    assert result.exit_code == 1
    assert '{"status": "starting"}' in result.stdout
    assert sleep_calls == [0.5]


def test_probe_readiness_wait_retries_connection_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        )
    )
    attempts = iter([URLError("connection refused"), b'{"status": "ready"}'])
    sleep_calls = []

    class ResponseStub:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._body

    def fake_urlopen(url, timeout):
        next_attempt = next(attempts)
        if isinstance(next_attempt, Exception):
            raise next_attempt
        return ResponseStub(next_attempt)

    monkeypatch.setattr(cli, "load_runtime_settings", lambda config: settings)
    monkeypatch.setattr(cli, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    result = runner.invoke(cli.app, ["probe-readiness", "--wait", "--interval-seconds", "0.2"])

    assert result.exit_code == 0
    assert '{"status": "ready"}' in result.stdout
    assert sleep_calls == [0.2]


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
