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

Relative runtime paths are scoped under `storage.workspace_root`, which now defaults to `./workspace` and is created automatically if missing. This keeps process state, final workflow documents, and relative repository context under one configurable workspace folder.

## Current MVP Draft

The current implementation includes:

- Telegram polling and webhook runtime modes
- requirement capture and plan confirmation before execution
- plan revision by sending more requirements before approval
- background run execution with local concurrency control
- proactive Telegram progress updates while a run is in flight
- plan-based architecture documents written under `docs/architecture/`
- separate test plans under `docs/testing/` and runtime-generated review reports under `docs/reviews/` (the repository also keeps curated review notes under `docs/review/`)
- SQLite-backed run and conversation persistence
- FTS5-backed search across stored runs and conversation messages, with phrase-aware ranking and a LIKE fallback when SQLite FTS is unavailable
- learning memory from successful prior runs within the same chat
- optional repository-scoped knowledge keyed by `repo_name` in config, with each run persisting the repository scope that was active when it was submitted
- optional multi-model fan-out for an agent, with parallel execution across configured provider aliases
- static planner, architect, coder, tester, and reviewer agent roles in config
- bounded review-driven replanning up to a configurable maximum iteration count
- `/start`, `/status`, `/tools`, `/approve`, and `/cancel` commands
- local config plus explicit `--config` override at startup
- OpenAI provider adapter with a clear fallback message when no API key is configured
- config-gated package installation support through the runtime CLI
- source-control integration through logged-in `git`, `gh`, and `glab` CLIs
- named CLI sessions that surface the latest incomplete run summary plus recent conversation history when you re-enter them

## Project Status

MergeMate is currently in an MVP draft stage.

Implemented now:

- approval-gated planning before execution
- background execution with Telegram progress updates
- role-based planner, architect, coder, tester, and reviewer stages
- endpoint-based provider configuration for OpenAI-compatible APIs
- SQLite persistence for runs, chat history, and learning excerpts
- local CLI integration for repository and platform context
- phase-1 runtime tool context injection for enabled read-only agent tools

Current limitations:

- webhook deployment hardening is still in progress beyond the initial self-hosted webhook and readiness setup
- honest ingress and worker splitting is still in progress; the current codebase now has durable planning and execution jobs, but Redis-backed transport and a dedicated worker process are not implemented yet
- the provider adapter currently assumes an OpenAI-compatible chat-completions request shape
- progress estimates are now prompt-aware and structure-aware heuristic-based rather than telemetry-driven
- sandboxed code execution is not part of the MVP
- runtime tool execution is still limited to safe context collection; autonomous mutating tool use is not implemented

## Commands

The list below mirrors `mergemate --help` and should stay in sync with the CLI.
Use `validate-config` before starting the bot, `probe-readiness` when running webhook mode,
and the search and context commands when you need to inspect persisted state locally.

- `mergemate run-bot` — start the Telegram bot runtime.
- `mergemate validate-config` — verify the resolved config, provider aliases, secrets, and database path before startup.
- `mergemate print-config-path` — show the default project-local config path.
- `mergemate probe-readiness` — check the local webhook readiness endpoint; use `--wait` to poll until ready.
- `mergemate install-package <package-name>` — install an extra Python package when package installs are allowed by config.
- `mergemate repo-context [--platform github|gitlab]` — inspect repository context through local `git` plus an authenticated platform CLI.
- `mergemate platform-auth github|gitlab` — verify the selected GitHub or GitLab CLI is authenticated.
- `mergemate search-runs <query> [--limit N] [--session NAME]` — search stored run prompts, results, and metadata, optionally scoped to a session.
- `mergemate search-conversations <query> [--limit N] [--session NAME]` — search saved chat message history, optionally scoped to a session.
- `mergemate search <query> [--limit N] [--session NAME]` — search runs and chat messages together in a single result stream, optionally scoped to a session.
- `mergemate run <prompt>` — submit a one-shot prompt and wait for completion (supports `--agent`, `--workflow`, `--session`, `--quiet`, `--timeout`, `--poll-interval`).
- `mergemate chat` — interactive REPL session (supports `--session`, `--agent`, `--workflow`, `--timeout`, `--poll-interval`).

The search commands are useful when you want to recover prior requirements or compare a current run with similar past work without opening the database directly. Use `search` when you want a unified stream of both run and message matches; use the source-specific commands when you want only one kind of result.

## GitHub Automation

The repository includes two GitHub Actions workflows:

- pull request validation in `.github/workflows/pr-checks.yml` for PR creation and later commits pushed to the PR branch
- tag-based publishing in `.github/workflows/publish-pypi.yml` for tags matching `v*`

The publish workflow builds the wheel and source distribution, checks them with `twine check`, verifies that the Git tag matches the version in `pyproject.toml`, and then publishes to PyPI.

The PyPI workflow is configured for GitHub trusted publishing through the `id-token: write` permission. Configure the project on PyPI to trust this repository before using release tags.

For repository hygiene and branch cleanup, see `docs/operations/repository-maintenance.md`. The `Makefile` also exposes `branches-list`, `branches-merged`, `branches-clean`, and `branches-prune` helpers for day-to-day maintenance. The listing targets stay successful even when there are no branches to report, and `branches-prune` skips the currently checked-out branch so it can be run safely from a feature branch.

## Development Workflow

The `Makefile` mirrors the common contributor workflow and is the fastest way to run the local quality checks:

- `make install-dev` — install MergeMate in editable mode with the dev tooling set
- `make format` — apply Ruff formatting
- `make format-check` — verify formatting without changing files
- `make lint` — run Ruff linting
- `make typecheck` — run mypy against `src`
- `make test` — run the unit test suite used by PR validation
- `make test-all` — run the full test suite, including integration and e2e tests
- `make ci` — run lint, format check, typecheck, and unit tests in one pass
- `make clean` — remove local caches and generated coverage artifacts

If you are contributing changes, `make ci` is the closest local approximation of the PR checks workflow, and `make test-all` is the best option before larger merges.

## Local State

By default, runtime state is stored in a SQLite database at `.state/mergemate.db` under the configured workspace root. The default workspace root is `./workspace` relative to the active config file, and MergeMate creates that directory automatically if needed.

## Quick Start

1. Install the package in editable mode.
2. Set `TELEGRAM_BOT_TOKEN`.
3. Optionally set `OPENAI_API_KEY`.
4. Review or edit `config/config.yaml`.
5. Start the bot with `mergemate run-bot` or pass an explicit config path.

Use `mergemate validate-config` to verify which config file and database path will be used before startup.

For webhook mode, also set `telegram.mode: webhook`, provide `telegram.webhook_public_base_url`, and expose `TELEGRAM_WEBHOOK_SECRET`. MergeMate now rejects insecure webhook config at startup: non-loopback public URLs must use `https`, the webhook path cannot include query or fragment components, and webhook mode requires a secret-token environment variable. Webhook mode also supports a local readiness endpoint by default; use `mergemate probe-readiness --wait` during rollout and tune the polling loop with `--interval-seconds`, `--max-wait-seconds`, and `--timeout-seconds`. For an initial self-hosted deployment, see `docs/operations/webhook-deployment.md`.

For step-by-step setup and operation, see `docs/user-guide.md`. For production-oriented persistence layout and deployment boundaries, see `docs/operations/production-deployment.md`.

The current split-runtime implementation work starts with durable planning and execution job records in the shared persistence layer. That means dispatch is no longer modeled only as an in-memory worker handoff. The intended production direction is single-host deployment with SQLite as the system of record and Redis as the queue transport once ingress and worker become separate local processes.

## Learning And Package Installation

MergeMate now persists short excerpts from successful runs and feeds recent learned examples back into later prompts for the same chat.

If you set the optional top-level `repo_name` in config, MergeMate also loads repository-specific knowledge snippets for that repository and includes them in the prompt context. Each submitted run stores the repository scope that was active at submission time, so later lookups keep using the run's own repo context even if the config changes. When `repo_name` is unset, the bot falls back to chat-scoped learning only.

MergeMate can also fan out one request to multiple configured model aliases in parallel. The default `coder` agent is now configured to call two provider aliases concurrently and return a sectioned combined result.

The current `generate_code` execution sequence is:

1. capture requirements
2. ask clarification questions and draft a plan
3. wait for user confirmation
4. retrieve context
5. produce design, save it internally, and write an architecture document under the workspace docs folder
6. use configured coding model to generate implementation output
7. use configured testing model to generate tests, then write a test plan document under the workspace docs folder
8. use configured review model to review design and implementation, then write a review report under the workspace docs folder
9. if review reports high concerns, send those concerns back to the planning model and repeat up to the configured iteration limit

For direct workflows such as `debug_code` and `explain_code`, MergeMate still drafts and confirms a plan first, but the background execution path runs a direct single-agent call instead of the full design, testing, and review chain.

The current MVP keeps both planning and long-running execution work off the Telegram intake path. MergeMate now acknowledges the request immediately, completes planning in the background, and then sends the drafted plan or auto-start notice as a follow-up message.

Package installation is supported, but intentionally gated by configuration:

- set `tools.allow_package_install: true`
- optionally restrict allowed installs with `tools.allowed_packages`

This keeps the capability available without making arbitrary package installation the default behavior.

## Parallel Models

Agents can declare multiple `provider_names` and set `parallel_mode: parallel` in config. In that mode, MergeMate calls those models simultaneously and combines the results.

The current MVP combine strategies are:

- `sectioned`: return each model output in labeled sections
- `first_success`: return the first successful model result

## Provider Endpoints

Providers are configured by URL, not by a provider type flag. This is intended to support OpenAI-compatible endpoints, including custom gateway URLs or Azure AI Foundry-style endpoints, as long as they accept the same chat-completions request shape used by the current adapter.

You can also mix multiple providers at the same time by assigning different provider aliases to different roles.

Example:

```yaml
providers:
	kimi_planner:
		api_key_env: KIMI_API_KEY
		model: kimi-k2
		timeout_seconds: 90
		provider_url: https://api.moonshot.ai/v1/chat/completions
		retry:
			max_retries: 4
			base_delay_seconds: 1.5

	deepseek_architect:
		api_key_env: DEEPSEEK_API_KEY
		model: deepseek-reasoner
		timeout_seconds: 120
		provider_url: https://api.deepseek.com/chat/completions

	openai_coder:
		api_key_env: OPENAI_API_KEY
		model: gpt-5.4
		timeout_seconds: 120
		provider_url: https://api.openai.com/v1/chat/completions

	azure_reviewer:
		api_key_env: AZURE_OPENAI_API_KEY
		model: gpt-4.1
		timeout_seconds: 120
		provider_url: https://your-endpoint.openai.azure.com/openai/deployments/reviewer/chat/completions?api-version=2024-10-21
		api_key_header: api-key
		api_key_prefix: ""

workflow_control:
	planner_agent_name: planner
	architect_agent_name: architect
	coder_agent_name: coder
	tester_agent_name: tester
	reviewer_agent_name: reviewer

agents:
	planner:
		workflow: planning
		provider_names: [kimi_planner]

	architect:
		workflow: design
		provider_names: [deepseek_architect]

	coder:
		workflow: generate_code
		provider_names: [openai_coder]

	tester:
		workflow: testing
		provider_names: [openai_coder]

	reviewer:
		workflow: review
		provider_names: [azure_reviewer]
```

This lets you run Kimi, DeepSeek, OpenAI, Azure-hosted models, and other compatible endpoints in the same MergeMate workflow.

You can also override retry behavior per provider. Set `runtime.llm_retry` for the global default, then add `providers.<name>.retry` when a specific endpoint needs a different retry budget or backoff profile. Provider-level retry settings take precedence for that provider and are especially useful when one upstream is stricter than the rest.

## GitHub And GitLab

MergeMate can work with source-control platforms through the local command-line utilities you are already logged into.

Current support assumes the user has authenticated locally with the relevant tools:

- `git`
- `gh` for GitHub
- `glab` for GitLab

The MVP uses those CLIs instead of embedding platform-specific OAuth flows. That keeps setup simple and fits local developer workflows.

Configured support includes:

- repository status from `git`
- GitHub repository and auth inspection through `gh`
- GitLab repository and auth inspection through `glab`

## Repository Layout

See the architecture documentation in `docs/architecture/` for the planned runtime, job lifecycle, config model, and packaging strategy.

The architecture decisions themselves are indexed in `docs/architecture/adr/index.md`.
