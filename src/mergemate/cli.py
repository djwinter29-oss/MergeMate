"""CLI entrypoints for running MergeMate."""

from pathlib import Path

import typer

from mergemate.bootstrap import bootstrap
from mergemate.config.loader import resolve_config_path
from mergemate.interfaces.telegram.bot import TelegramBotRuntime

app = typer.Typer(help="MergeMate command line interface")


@app.command("run-bot")
def run_bot(config: Path | None = typer.Option(None, help="Path to a YAML configuration file")) -> None:
    """Start the Telegram bot runtime."""
    runtime = bootstrap(config)
    typer.echo(
        f"MergeMate configured for provider={runtime.settings.default_provider} "
        f"agent={runtime.settings.default_agent}"
    )
    TelegramBotRuntime(runtime).run_polling()


@app.command("validate-config")
def validate_config(
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file")
) -> None:
    """Validate and print the resolved configuration path."""
    resolved_path = resolve_config_path(config)
    runtime = bootstrap(config)
    typer.echo(f"Configuration is valid: {resolved_path}")
    typer.echo(f"Resolved database path: {runtime.database.path}")


@app.command("print-config-path")
def print_config_path() -> None:
    """Print the default local configuration path."""
    typer.echo(str(resolve_config_path()))


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