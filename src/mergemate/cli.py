"""CLI entrypoints for running MergeMate."""

import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import typer

from mergemate.bootstrap import bootstrap
from mergemate.config.loader import load_runtime_settings, resolve_config_path
from mergemate.interfaces.telegram.bot import TelegramBotRuntime

app = typer.Typer(help="MergeMate command line interface")


def _resolve_readiness_url(settings) -> str:
    telegram_settings = settings.telegram
    if telegram_settings.mode != "webhook":
        raise ValueError("Readiness probing is only available when telegram.mode is webhook")
    if not telegram_settings.webhook_healthcheck_enabled:
        raise ValueError("Readiness probing is disabled because telegram.webhook_healthcheck_enabled is false")
    return (
        f"http://{telegram_settings.webhook_healthcheck_listen_host}:"
        f"{telegram_settings.webhook_healthcheck_listen_port}"
        f"{telegram_settings.webhook_healthcheck_path}"
    )


def _resolve_runtime_summary(settings) -> tuple[str, str]:
    default_provider = settings.default_provider
    default_agent = settings.default_agent
    return default_provider, default_agent


def _probe_readiness_once(readiness_url: str, *, timeout_seconds: float) -> tuple[str, dict[str, object], bool]:
    try:
        with urlopen(readiness_url, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            payload = json.loads(response_body)
    except HTTPError as error:
        response_body = error.read().decode("utf-8")
        try:
            payload = json.loads(response_body)
        except json.JSONDecodeError:
            payload = {"status": "http_error", "detail": response_body}
        return response_body, payload, False
    except URLError as error:
        return f"Readiness probe failed: {error.reason}", {"status": "connection_error"}, False

    is_ready = payload.get("status") == "ready"
    return response_body, payload, is_ready


@app.command("run-bot")
def run_bot(config: Path | None = typer.Option(None, help="Path to a YAML configuration file")) -> None:
    """Start the Telegram bot runtime."""
    runtime = bootstrap(config)
    default_provider, default_agent = _resolve_runtime_summary(runtime.settings)
    typer.echo(
        f"MergeMate configured for provider={default_provider} "
        f"agent={default_agent}"
    )
    TelegramBotRuntime(runtime).run()


@app.command("validate-config")
def validate_config(
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file")
) -> None:
    """Validate and print the resolved configuration path."""
    resolved_path = resolve_config_path(config)
    settings = load_runtime_settings(config)
    settings.resolve_telegram_token()
    if settings.telegram.mode == "webhook":
        settings.resolve_telegram_webhook_url()
        settings.resolve_telegram_webhook_secret_token()
    settings.resolve_provider_api_key()
    for agent_name in settings.agents:
        settings.resolve_agent_provider_names(agent_name)
    resolved_database_path = settings.preview_database_path(resolved_path)
    typer.echo(f"Configuration is valid: {resolved_path}")
    typer.echo(f"Resolved database path: {resolved_database_path}")


@app.command("print-config-path")
def print_config_path() -> None:
    """Print the default local configuration path."""
    typer.echo(str(resolve_config_path()))


def _report_not_ready(response_body: str, payload: dict[str, object]) -> None:
    """Print readiness failure and exit."""
    if payload.get("status") == "connection_error":
        typer.echo(response_body, err=True)
    else:
        typer.echo(response_body)
    raise typer.Exit(code=1)


@app.command("probe-readiness")
def probe_readiness(
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
    timeout_seconds: float = typer.Option(2.0, min=0.1, help="HTTP timeout in seconds"),
    wait: bool = typer.Option(False, help="Wait until the readiness endpoint reports ready"),
    interval_seconds: float = typer.Option(
        1.0,
        min=0.1,
        help="Polling interval in seconds when --wait is enabled",
    ),
    max_wait_seconds: float | None = typer.Option(
        None,
        min=0.1,
        help="Optional maximum total wait time in seconds when --wait is enabled",
    ),
) -> None:
    """Probe the local webhook readiness endpoint and exit nonzero until it is ready."""
    settings = load_runtime_settings(config)
    readiness_url = _resolve_readiness_url(settings)
    start_time = time.monotonic()

    while True:
        response_body, payload, is_ready = _probe_readiness_once(
            readiness_url,
            timeout_seconds=timeout_seconds,
        )

        if is_ready:
            typer.echo(response_body)
            return

        if not wait:
            _report_not_ready(response_body, payload)

        if max_wait_seconds is not None and time.monotonic() - start_time >= max_wait_seconds:
            _report_not_ready(response_body, payload)

        time.sleep(interval_seconds)


@app.command("install-package")
def install_package(
    package_name: str,
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
) -> None:
    """Install an additional Python package when explicitly allowed by config."""
    runtime = bootstrap(config)
    result = runtime.tool_service.install_package(package_name)
    if result["status"] not in {"installed", "blocked"}:
        typer.echo(result["detail"], err=True)
        raise typer.Exit(code=1)
    typer.echo(result["detail"])


@app.command("repo-context")
def repo_context(
    platform: str | None = typer.Option(None, help="Source platform to inspect: github or gitlab"),
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
) -> None:
    """Print local repository context using git and an authenticated platform CLI."""
    runtime = bootstrap(config)
    context = runtime.tool_service.get_repository_context(platform)
    for name, result in context.items():
        typer.echo(f"[{name}] {result['status']}")
        typer.echo(result["detail"])


@app.command("platform-auth")
def platform_auth(
    platform: str = typer.Argument(..., help="Platform to inspect: github or gitlab"),
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
) -> None:
    """Check whether a logged-in platform CLI is available for GitHub or GitLab."""
    runtime = bootstrap(config)
    result = runtime.tool_service.get_platform_auth_status(platform)
    if result["status"] != "ok":
        typer.echo(result["detail"], err=True)
        raise typer.Exit(code=1)
    typer.echo(result["detail"])