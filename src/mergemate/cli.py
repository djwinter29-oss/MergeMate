"""CLI entrypoints for running MergeMate."""

import json
from hashlib import blake2s
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import typer

from mergemate.bootstrap import bootstrap
from mergemate.config.loader import load_runtime_settings, resolve_config_path
from mergemate.domain.shared import RunStatus
from mergemate.interfaces.telegram.bot import TelegramBotRuntime

app = typer.Typer(help="MergeMate command line interface")


def _resolve_readiness_url(settings) -> str:
    telegram_settings = settings.telegram
    if telegram_settings.mode != "webhook":
        raise ValueError("Readiness probing is only available when telegram.mode is webhook")
    if not telegram_settings.webhook_healthcheck_enabled:
        raise ValueError(
            "Readiness probing is disabled because telegram.webhook_healthcheck_enabled is false"
        )
    return (
        f"http://{telegram_settings.webhook_healthcheck_listen_host}:"
        f"{telegram_settings.webhook_healthcheck_listen_port}"
        f"{telegram_settings.webhook_healthcheck_path}"
    )


def _resolve_runtime_summary(settings) -> tuple[str, str]:
    default_provider = settings.default_provider
    default_agent = settings.default_agent
    return default_provider, default_agent


def _probe_readiness_once(
    readiness_url: str, *, timeout_seconds: float
) -> tuple[str, dict[str, object], bool]:
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
def run_bot(
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
) -> None:
    """Start the Telegram bot runtime."""
    runtime = bootstrap(config)
    default_provider, default_agent = _resolve_runtime_summary(runtime.settings)
    typer.echo(f"MergeMate configured for provider={default_provider} agent={default_agent}")
    TelegramBotRuntime(runtime).run()


@app.command("validate-config")
def validate_config(
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
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
    result = runtime.services.tool_service.install_package(package_name)
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
    context = runtime.services.tool_service.get_repository_context(platform)
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
    result = runtime.services.tool_service.get_platform_auth_status(platform)
    if result["status"] != "ok":
        typer.echo(result["detail"], err=True)
        raise typer.Exit(code=1)
    typer.echo(result["detail"])


@app.command("search-runs")
def search_runs(
    query: str = typer.Argument(..., help="Search term to match against run fields"),
    limit: int = typer.Option(10, min=1, max=100, help="Maximum results to return"),
    session: str | None = typer.Option(None, help="Session name to restrict results to"),
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
) -> None:
    """Search agent runs by keyword across prompts, results, and metadata fields."""
    runtime = bootstrap(config)
    chat_id = _resolve_session_chat_id(session) if session is not None else None
    runs = runtime.persistence.run_repository.search(query, limit=limit, chat_id=chat_id)
    _print_search_results(runs)


@app.command("search-conversations")
def search_conversations(
    query: str = typer.Argument(..., help="Search term to match against conversation messages"),
    limit: int = typer.Option(10, min=1, max=100, help="Maximum results to return"),
    session: str | None = typer.Option(None, help="Session name to restrict results to"),
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
) -> None:
    """Search conversation messages by keyword."""
    runtime = bootstrap(config)
    chat_id = _resolve_session_chat_id(session) if session is not None else None
    messages = runtime.persistence.conversation_repository.search_messages(
        query, limit=limit, chat_id=chat_id
    )
    _print_message_search_results(messages)


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Search term to match against runs and messages"),
    limit: int = typer.Option(10, min=1, max=100, help="Maximum results to return"),
    session: str | None = typer.Option(None, help="Session name to restrict results to"),
    config: Path | None = typer.Option(None, help="Path to a YAML configuration file"),
) -> None:
    """Search stored runs and conversation messages in one combined result set."""
    runtime = bootstrap(config)
    chat_id = _resolve_session_chat_id(session) if session is not None else None
    runs = runtime.persistence.run_repository.search(query, limit=limit, chat_id=chat_id)
    messages = runtime.persistence.conversation_repository.search_messages(
        query, limit=limit, chat_id=chat_id
    )
    _print_combined_search_results(runs, messages, limit=limit)


def _print_search_results(runs: Sequence) -> None:
    if not runs:
        typer.echo("No matching runs found.")
        return
    for result in _build_run_search_results(runs):
        typer.echo(result)


def _print_message_search_results(messages: list[dict[str, str | int]]) -> None:
    if not messages:
        typer.echo("No matching messages found.")
        return
    for result in _build_message_search_results(messages):
        typer.echo(result)


def _print_combined_search_results(
    runs: Sequence,
    messages: list[dict[str, str | int]],
    *,
    limit: int,
) -> None:
    run_results = _build_run_search_results(runs)
    message_results = _build_message_search_results(messages)
    results: list[tuple[datetime, str]] = []

    for run, result in zip(runs, run_results):
        results.append((run.updated_at, result))
    for msg, result in zip(messages, message_results):
        results.append((datetime.fromisoformat(str(msg["created_at"])), result))

    if not results:
        typer.echo("No matching runs or messages found.")
        return

    for _, result in sorted(results, key=lambda item: item[0], reverse=True)[:limit]:
        typer.echo(result)


def _build_run_search_results(runs: Sequence) -> list[str]:
    results: list[str] = []
    for run in runs:
        snippet = (run.prompt or "")[:80].replace("\n", " ")
        results.append(f"[run {run.run_id[:8]}] {run.workflow}/{run.status.value}  —  {snippet}")
    return results


def _build_message_search_results(messages: list[dict[str, str | int]]) -> list[str]:
    results: list[str] = []
    for msg in messages:
        content = str(msg["content"])[:100].replace("\n", " ")
        results.append(f"[chat:{msg['chat_id']} {msg['role']}] {content}")
    return results


# ── CLI run + chat commands ────────────────────────────────────────────

_CLI_USER_ID = 0  # synthetic user ID for CLI sessions


def _resolve_session_chat_id(session_name: str | None) -> int:
    """Derive a deterministic chat_id from a session name, or use a unique one-shot ID."""
    if session_name is None:
        import random

        return -abs(random.getrandbits(31))
    digest = blake2s(f"cli:{session_name}".encode("utf-8"), digest_size=8).digest()
    return 1 + (int.from_bytes(digest, "big") % (2**31 - 2))


def _resolve_workflow(
    agent_name: str,
    workflow: str | None,
    runtime,
) -> str:
    """Resolve the workflow for an agent, defaulting to the configured one."""
    from mergemate.config.models import ConfigWorkflowNotFoundError

    if workflow is not None:
        return workflow
    agent_cfg = runtime.settings.agents.get(agent_name)
    if agent_cfg is not None and agent_cfg.workflow is not None:
        return agent_cfg.workflow
    raise ConfigWorkflowNotFoundError(
        f"Agent {agent_name!r} has no default workflow. Use --workflow to specify one."
    )


def _print_run_result(
    run,
    *,
    quiet: bool = False,
) -> None:
    """Print the result of a completed run."""
    if quiet:
        if run.result_text:
            typer.echo(run.result_text.rstrip())
        elif run.error_text:
            typer.echo(run.error_text.rstrip(), err=True)
        return

    typer.echo(f"Status: {run.status.value}")
    if run.plan_text:
        preview = run.plan_text[:200].replace("\n", " ")
        typer.echo(f"Plan: {preview}...")
    if run.result_text:
        typer.echo(f"Result:\n{run.result_text.rstrip()}")
    elif run.error_text:
        typer.echo(f"Error: {run.error_text}", err=True)


def _print_conversation_history(runtime, chat_id: int, *, limit: int = 10) -> None:
    """Print recent conversation history for a session."""
    messages = runtime.persistence.conversation_repository.load_recent_messages(
        chat_id, limit=limit
    )
    if not messages:
        return
    typer.echo("--- Previous conversation ---")
    for msg in messages[-limit:]:
        role = (
            getattr(msg, "role", msg.get("role", "unknown")) if isinstance(msg, dict) else msg.role
        )
        content = (
            getattr(msg, "content", str(msg.get("content", "")))[:120].replace("\n", " ")
            if isinstance(msg, dict)
            else msg.content[:120].replace("\n", " ")
        )
        typer.echo(f"  [{role}] {content}")
    typer.echo("----------------------------")


def _poll_run(runtime, run_id: str, *, timeout: float | None, poll_interval: float) -> object:
    """Poll for run completion. Returns the terminal run or raises typer.Exit."""
    import time as _time

    deadline = (_time.monotonic() + timeout) if timeout is not None else float("inf")

    while _time.monotonic() < deadline:
        snapshot = runtime.services.get_run_status.execute(run_id)
        if snapshot is None:
            typer.echo("Run not found.", err=True)
            raise typer.Exit(code=2)
        if snapshot.status in RunStatus.terminal_statuses():
            return snapshot
        _time.sleep(poll_interval)

    typer.echo("Timed out waiting for run to complete.", err=True)
    raise typer.Exit(code=1)


def _temporary_auto_approve(runtime):
    """Context manager that temporarily disables confirmation requirements."""
    import contextlib

    @contextlib.contextmanager
    def _manager():
        original = runtime.settings.workflow_control.require_confirmation
        runtime.settings.workflow_control.require_confirmation = False
        try:
            yield
        finally:
            runtime.settings.workflow_control.require_confirmation = original

    return _manager()


@dataclass
class _ConfigOption:
    """Helper to share the --config option across commands."""

    value: Path | None = None


_CONFIG_OPTION = typer.Option(None, help="Path to a YAML configuration file")


@app.command("run")
def run_cli(
    prompt: str = typer.Argument(..., help="Prompt to submit for execution"),
    agent: str | None = typer.Option(None, help="Agent name to use"),
    workflow: str | None = typer.Option(
        None, help="Workflow name (generate_code, debug_code, explain_code)"
    ),
    quiet: bool = typer.Option(False, help="Suppress banner/estimate; print only the final result"),
    timeout: float | None = typer.Option(None, min=1, help="Max seconds to wait for completion"),
    session: str | None = typer.Option(
        None, help="Session name for persistent conversation history"
    ),
    poll_interval: float = typer.Option(2.0, min=0.5, help="Polling interval in seconds"),
    config: Path | None = _CONFIG_OPTION,  # type: ignore[arg-type]
) -> None:
    """Submit a one-shot prompt and wait for completion."""
    import asyncio

    runtime = bootstrap(config)
    chat_id = _resolve_session_chat_id(session)
    agent_name = agent or runtime.settings.default_agent
    resolved_workflow = _resolve_workflow(agent_name, workflow, runtime)

    # Submit the prompt with auto-approve (CLI user explicitly asked for execution)
    with _temporary_auto_approve(runtime):
        result = asyncio.run(
            runtime.services.submit_prompt.execute(
                chat_id=chat_id,
                user_id=_CLI_USER_ID,
                agent_name=agent_name,
                workflow=resolved_workflow,
                prompt=prompt,
            )
        )

    if not quiet:
        typer.echo(f"Run ID: {result.run_id}")
        typer.echo(f"Workflow: {resolved_workflow}")
        typer.echo(f"Estimated duration: ~{result.estimate_seconds}s")
        if result.plan_text:
            preview = result.plan_text[:300]
            typer.echo(f"\nPlan:\n{preview}")

    # Poll until terminal
    run = _poll_run(runtime, result.run_id, timeout=timeout, poll_interval=poll_interval)
    _print_run_result(run, quiet=quiet)


@app.command("chat")
def chat_cli(
    session: str | None = typer.Option(
        None, help="Session name for persistent conversation history"
    ),
    agent: str | None = typer.Option(None, help="Agent name to use"),
    workflow: str | None = typer.Option(
        None, help="Workflow name (generate_code, debug_code, explain_code)"
    ),
    timeout: float | None = typer.Option(None, min=1, help="Max seconds to wait per run"),
    poll_interval: float = typer.Option(2.0, min=0.5, help="Polling interval in seconds"),
    config: Path | None = _CONFIG_OPTION,  # type: ignore[arg-type]
) -> None:
    """Interactive REPL for multi-turn conversation with session persistence."""
    import asyncio

    runtime = bootstrap(config)
    chat_id = _resolve_session_chat_id(session)
    agent_name = agent or runtime.settings.default_agent
    resolved_workflow = _resolve_workflow(agent_name, workflow, runtime)

    # Show conversation history on resume
    _print_conversation_history(runtime, chat_id)

    session_label = session or "(anonymous)"
    typer.echo(f"MergeMate chat session [{session_label}]")
    typer.echo('Type "exit" or "quit" to leave.')

    with _temporary_auto_approve(runtime):
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                typer.echo()
                break
            if user_input.lower() in ("exit", "quit"):
                break
            if not user_input:
                continue

            # Submit the prompt
            result = asyncio.run(
                runtime.services.submit_prompt.execute(
                    chat_id=chat_id,
                    user_id=_CLI_USER_ID,
                    agent_name=agent_name,
                    workflow=resolved_workflow,
                    prompt=user_input,
                )
            )

            typer.echo(f"  [Run {result.run_id[:8]}] ~{result.estimate_seconds}s ...")
            if result.plan_text:
                plan_preview = result.plan_text[:200].replace("\n", " ")
                typer.echo(f"  Plan: {plan_preview}...")

            # Poll until terminal
            run = _poll_run(runtime, result.run_id, timeout=timeout, poll_interval=poll_interval)
            _print_run_result(run)
