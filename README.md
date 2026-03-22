# MergeMate

MergeMate is a Python-first, AI-powered code-generation agent for Telegram. Users send natural-language prompts in chat and receive runnable code, debugging help, explanations, and status updates while long-running work continues in the background.

## MVP Goals

- Keep Telegram chat responsive with immediate acknowledgements and progress updates.
- Support code generation, debugging help, and explanation workflows.
- Preserve conversation context per chat.
- Ship as an installable Python package that can later be released to PyPI.
- Expose an extensible architecture for custom tools, workflows, and provider adapters.

## Architecture Direction

The MVP is a modular Python monolith with clear internal boundaries:

- `interfaces`: Telegram-specific delivery concerns.
- `application`: orchestration, job dispatch, and use cases.
- `domain`: entities, policies, and repository contracts.
- `infrastructure`: provider adapters, persistence, queue, and telemetry.
- `config`: local default configuration and runtime loading.

The bot should acknowledge requests quickly and hand off longer work to a background execution path. This keeps chat unblocked while still providing status and estimated progress.

## Configuration Model

MergeMate uses YAML for user-editable configuration.

Default config resolution order:

1. Package defaults.
2. Local workspace config at `./config/config.yaml`.
3. Explicit config path passed at startup, for example `mergemate run-bot --config /path/to/config.yaml`.
4. Environment variables for secrets and deployment overrides.

This supports both project-local use and user-space service deployment.

## Current MVP Draft

The current implementation includes:

- Telegram polling mode
- requirement capture and plan confirmation before execution
- plan revision by sending more requirements before approval
- background run execution with local concurrency control
- SQLite-backed run and conversation persistence
- learning memory from successful prior runs within the same chat
- optional multi-model fan-out for an agent, with parallel execution across configured provider aliases
- static planner, coder, tester, and reviewer agent roles in config
- bounded review-driven replanning up to a configurable maximum iteration count
- `/start`, `/status`, `/approve`, and `/cancel` commands
- local config plus explicit `--config` override at startup
- OpenAI provider adapter with a clear fallback message when no API key is configured
- config-gated package installation support through the runtime CLI

## Commands

- `mergemate run-bot`
- `mergemate validate-config`
- `mergemate print-config-path`
- `mergemate install-package <package-name>`

## Local State

By default, runtime state is stored in a SQLite database at `.state/mergemate.db` relative to the active config file directory.

## Quick Start

1. Install the package in editable mode.
2. Set `TELEGRAM_BOT_TOKEN`.
3. Optionally set `OPENAI_API_KEY`.
4. Review or edit `config/config.yaml`.
5. Start the bot with `mergemate run-bot` or pass an explicit config path.

Use `mergemate validate-config` to verify which config file and database path will be used before startup.

## Learning And Package Installation

MergeMate now persists short excerpts from successful runs and feeds recent learned examples back into later prompts for the same chat.

MergeMate can also fan out one request to multiple configured model aliases in parallel. The default `coder` agent is now configured to call two provider aliases concurrently and return a sectioned combined result.

The current execution sequence is:

1. capture requirements
2. ask clarification questions and draft a plan
3. wait for user confirmation
4. retrieve context
5. produce design and save it internally
6. use configured coding model to generate implementation output
7. use configured testing model to generate tests and test approach
8. use configured review model to review design and implementation
9. if review reports high concerns, send those concerns back to the planning model and repeat up to the configured iteration limit

Package installation is supported, but intentionally gated by configuration:

- set `tools.allow_package_install: true`
- optionally restrict allowed installs with `tools.allowed_packages`

This keeps the capability available without making arbitrary package installation the default behavior.

## Parallel Models

Agents can declare multiple `provider_names` and set `parallel_mode: parallel` in config. In that mode, MergeMate calls those models simultaneously and combines the results.

The current MVP combine strategies are:

- `sectioned`: return each model output in labeled sections
- `first_success`: return the first successful model result

## Repository Layout

See the architecture documentation in `docs/architecture/` for the planned runtime, job lifecycle, config model, and packaging strategy.
