# User Guide

## What MergeMate Does

MergeMate is a Telegram-driven coding assistant that keeps planning, design, coding, testing, and review work in the background. The chat intake path returns an immediate acknowledgement, and the drafted plan arrives as a follow-up message.

If you want the architectural reasoning behind these behaviors, start with `docs/architecture/adr/index.md`.

## Project Status

MergeMate is currently in an MVP draft stage.

Implemented now:

- approval-gated planning before execution
- background execution with Telegram progress updates
- role-based planner, architect, coder, tester, and reviewer stages, with one configured agent per workflow role
- endpoint-based provider configuration for OpenAI-compatible APIs
- SQLite persistence for runs, chat history, and learning excerpts
- local CLI integration for repository and platform context
- phase-1 runtime tool context injection for enabled read-only agent tools

Current limitations:

- webhook deployment hardening is still in progress beyond the initial self-hosted runbook
- the provider adapter currently assumes an OpenAI-compatible chat-completions request shape
- progress estimates are still static and workflow-based rather than telemetry-driven
- sandboxed code execution is not part of the MVP
- runtime tool execution is still limited to safe context collection; autonomous mutating tool use is not implemented

The current MVP supports:

- requirement capture and explicit plan confirmation
- background execution with stage updates
- separate planner, architect, coder, tester, and reviewer roles
- role-specific provider aliases and endpoint URLs
- local SQLite state for runs, chat history, and learning excerpts
- optional package installation guarded by configuration
- repository context through local `git`, `gh`, and `glab` CLIs

## Prerequisites

- Python 3.12 or newer
- a Telegram bot token exposed through an environment variable
- at least one provider API key exposed through an environment variable
- `git`, and optionally `gh` or `glab`, if you want repository context features

## Install For Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Required Environment Variables

At minimum set:

```bash
export TELEGRAM_BOT_TOKEN=...
export OPENAI_API_KEY=...
```

If you use different provider aliases, set the API key variable named in each provider entry.

## Configuration Resolution

MergeMate builds its effective configuration in this order:

1. package defaults from `src/mergemate/config/defaults.yaml`
2. local project config from `config/config.yaml`
3. an explicit file passed with `--config`

Secrets are not stored directly in the YAML by default. Instead, each provider points to an environment variable name such as `OPENAI_API_KEY`.

Relative runtime paths are resolved from `storage.workspace_root`. It defaults to `./workspace` relative to the active config file, and MergeMate creates that directory automatically if it does not exist. This lets you keep process data, context memory, final workflow documents, and relative repository paths under one configurable workspace folder.

The Telegram config section now supports both polling and webhook runtime modes. Webhook mode requires an externally reachable `webhook_public_base_url` and a `webhook_secret_token_env`. Public webhook URLs must use `https` unless you are intentionally targeting local loopback development such as `http://127.0.0.1:8081`. Webhook mode can also expose a separate local readiness endpoint through `webhook_healthcheck_enabled`, `webhook_healthcheck_listen_host`, `webhook_healthcheck_listen_port`, and `webhook_healthcheck_path`.

## Basic Commands

Validate configuration:

```bash
mergemate validate-config
```

`validate-config` now also rejects unknown provider aliases referenced by `default_provider` or agent `provider_names` before the bot starts.

Print the default project-local config path:

```bash
mergemate print-config-path
```

Run the Telegram bot:

```bash
mergemate run-bot
```

For webhook mode, configure `telegram.mode: webhook`, set `telegram.webhook_public_base_url` to the externally reachable base URL for the bot, and expose the secret named by `telegram.webhook_secret_token_env`.

Run with an explicit user-space config file:

```bash
mergemate run-bot --config ~/.config/mergemate/config.yaml
```

Webhook mode currently supports runtime configuration, startup validation, Telegram secret-token enforcement, Telegram application wiring, a built-in local readiness endpoint, and an initial self-hosted deployment runbook. See `docs/operations/webhook-deployment.md` for reverse-proxy, TLS termination, readiness probing, and user-service examples.

Install a Python package when allowed by config:

```bash
mergemate install-package requests
```

Inspect repository context:

```bash
mergemate repo-context
mergemate repo-context --platform gitlab
```

Check source-control CLI authentication:

```bash
mergemate platform-auth github
mergemate platform-auth gitlab
```

## Telegram Workflow

The default workflow is:

1. send a normal message describing the task
2. MergeMate stores the request and sends an immediate acknowledgement with the run ID and estimated execution time
3. MergeMate drafts the plan in the background and sends it as a follow-up message
4. if confirmation is enabled, MergeMate waits for approval after that follow-up plan arrives
5. you can reply with more requirements to revise the plan after planning completes
6. approve the run with `/approve <run_id>` or `/approve` to approve the latest one
7. For `generate_code`, MergeMate retrieves context, writes an architecture document under `docs/architecture/`, generates implementation output, writes a test plan under `docs/testing/`, and writes a review report under `docs/reviews/`
8. MergeMate sends stage updates while the run is active and a final completion or failure message at the end

If you try to revise or approve a run before planning finishes, MergeMate returns a planning-in-progress message instead of accepting the change.

If a status, tool-history, progress, or terminal message is too large for Telegram, MergeMate splits it into multiple messages automatically.

If Telegram temporarily fails to accept a progress update or final terminal update, MergeMate logs the failure and keeps the watcher alive long enough to retry delivery instead of permanently dropping the notification.

Workflow documents are written under the active docs root, typically `docs/architecture/`, `docs/testing/`, and `docs/reviews/` under the configured workspace root.

For direct workflows such as debugging and explanation, MergeMate still drafts and confirms a plan, but the execution step runs a direct single-agent call and does not emit the architecture, test-plan, or review documents.

Useful Telegram commands:

- `/start`: show the welcome message
- `/status`: show the latest run status for the current chat
- `/status <run_id>`: inspect a specific run
- `/tools [run_id] [limit]`: show recent tool activity, with `limit` capped at 50 entries per request
- `/approve`: approve the latest awaiting run in the current chat
- `/approve <run_id>`: approve a specific run
- `/cancel`: cancel the latest run in the current chat if it is still awaiting confirmation
- `/cancel <run_id>`: cancel a specific run if it is still awaiting confirmation

After a run has been approved, MergeMate does not currently support cancelling queued or running work from Telegram.

## Role-Based Provider Configuration

Providers are configured by endpoint URL, not by provider type. This allows you to mix different OpenAI-compatible endpoints in one workflow.

Example:

```yaml
providers:
  kimi_planner:
    api_key_env: KIMI_API_KEY
    model: kimi-k2
    timeout_seconds: 90
    provider_url: https://api.moonshot.ai/v1/chat/completions

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
  require_confirmation: true
  max_review_iterations: 5

agents:
  planner:
    workflow: planning
    provider_names: [kimi_planner]
    parallel_mode: single
    combine_strategy: first_success

  architect:
    workflow: design
    provider_names: [deepseek_architect]
    parallel_mode: single
    combine_strategy: first_success

  coder:
    workflow: generate_code
    provider_names: [openai_coder]
    parallel_mode: single
    combine_strategy: first_success

  tester:
    workflow: testing
    provider_names: [openai_coder]
    parallel_mode: single
    combine_strategy: first_success

  reviewer:
    workflow: review
    provider_names: [azure_reviewer]
    parallel_mode: single
    combine_strategy: first_success
```

## Parallel Model Fan-Out

One agent can call multiple provider aliases at once. Set `parallel_mode: parallel` and list multiple `provider_names`.

Example:

```yaml
agents:
  coder:
    workflow: generate_code
    provider_names: [openai_coder, deepseek_coder]
    parallel_mode: parallel
    combine_strategy: sectioned
```

Current combine strategies:

- `sectioned`: return each successful model output in separate labeled sections
- `first_success`: return the first successful result

## Approval And Review Controls

The `workflow_control` section governs the approval and review loop.

- `require_confirmation: true` keeps the plan approval gate enabled
- `max_review_iterations: 5` limits planner-reviewer replanning cycles
- workflow stages are selected from the `agents` section by workflow, with one configured agent per workflow role

If you supply an explicit override config file and it contains an `agents` section, MergeMate replaces the inherited `agents` map with that section instead of merging individual agent entries.

## Package Installation Safety

Package installation is disabled by default.

To enable it:

```yaml
tools:
  allow_package_install: true
  allowed_packages:
    - requests
    - pydantic
```

If `allowed_packages` is empty, any package name is accepted once installation is enabled. Restrict the list if you want tighter control.

## Repository Context Features

MergeMate can inspect your local repository and platform context through installed CLIs.

Expected tools:

- `git`
- `gh` for GitHub
- `glab` for GitLab

The current MVP assumes you already authenticated those tools locally.

## Runtime Data Location

By default, MergeMate stores runtime state in:

```text
.state/mergemate.db
```

This path is resolved under `storage.workspace_root` unless you configure an absolute path.

Example:

```yaml
storage:
  workspace_root: ~/.local/share/mergemate/workspace
  database_path: .state/mergemate.db
```

With that setup, architecture documents will go under `~/.local/share/mergemate/workspace/docs/architecture/`, test plans under `~/.local/share/mergemate/workspace/docs/testing/`, and review reports under `~/.local/share/mergemate/workspace/docs/reviews/`. Relative source-control paths will also resolve from the same workspace root.

## Troubleshooting

If the bot does not start:

- run `mergemate validate-config`
- confirm the Telegram token environment variable exists
- confirm at least one configured provider API key environment variable exists

If repository commands fail:

- verify `git`, `gh`, or `glab` is installed
- verify the selected platform CLI is already authenticated

If package installation is blocked:

- confirm `tools.allow_package_install` is `true`
- confirm the package is included in `tools.allowed_packages` when that list is non-empty