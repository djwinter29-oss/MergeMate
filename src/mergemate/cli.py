"""CLI entrypoints for running MergeMate."""

from pathlib import Path

import typer

from mergemate.bootstrap import bootstrap
from mergemate.config.loader import DEFAULT_LOCAL_CONFIG_PATH, resolve_config_path
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
    typer.echo(str(DEFAULT_LOCAL_CONFIG_PATH))


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