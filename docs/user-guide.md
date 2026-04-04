# User Guide

## What MergeMate Does

MergeMate is a Telegram-driven coding assistant that keeps chat responsive while longer planning, design, coding, testing, and review work runs in the background.

If you want the architectural reasoning behind these behaviors, start with `docs/architecture/adr/index.md`.

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

- Telegram webhook mode is not implemented yet
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

## Basic Commands

Validate configuration:

```bash
mergemate validate-config
```

Print the default project-local config path:

```bash
mergemate print-config-path
```

Run the Telegram bot:

```bash
mergemate run-bot
```

Run with an explicit user-space config file:

```bash
mergemate run-bot --config ~/.config/mergemate/config.yaml
```

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
2. MergeMate stores the request and drafts a plan
3. if confirmation is enabled, MergeMate returns the plan and waits for approval
4. you can reply with more requirements to revise the plan
5. approve the run with `/approve <run_id>` or `/approve` to approve the latest one
6. For `generate_code`, MergeMate retrieves context, writes an architecture document under `docs/architecture/`, generates implementation output, writes a test plan under `docs/testing/`, and writes a review report under `docs/reviews/`
7. MergeMate sends stage updates while the run is active and a final completion or failure message at the end

If a status, tool-history, progress, or terminal message is too large for Telegram, MergeMate splits it into multiple messages automatically.

If Telegram temporarily fails to accept a progress update, MergeMate logs the failure and continues watching the run instead of permanently stopping progress notifications.

Workflow documents are written under the active docs root, typically `docs/architecture/`, `docs/testing/`, and `docs/reviews/` under the configured workspace root.

For direct workflows such as debugging and explanation, MergeMate still drafts and confirms a plan, but the execution step runs a direct single-agent call and does not emit the architecture, test-plan, or review documents.

Useful Telegram commands:

- `/start`: show the welcome message
- `/status`: show the latest run status for the current chat
- `/status <run_id>`: inspect a specific run
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
  planner_agent_name: planner
  architect_agent_name: architect
  coder_agent_name: coder
  tester_agent_name: tester
  reviewer_agent_name: reviewer

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
- role-name fields choose which configured agent performs each workflow stage

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