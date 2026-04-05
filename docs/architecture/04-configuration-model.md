# Configuration Model

## Decision

Use YAML as the primary user-facing configuration format.

## Why YAML

- Easier for humans to edit than JSON.
- Supports comments for operational guidance.
- Better suited for nested provider, runtime, and agent settings.
- Common in local developer tooling and self-hosted services.

## Resolution Order

The effective config is built in this order:

1. Package defaults from `src/mergemate/config/defaults.yaml`
2. Local workspace config from `./config/config.yaml`
3. Explicit config path passed at startup
4. Environment variables for secrets and deployment overrides

The current scaffold implements package defaults plus the resolved YAML file. Environment variable expansion for secret values is a later implementation task, but the schema already stores the variable names to reference.

The current runtime resolves API keys and Telegram tokens by reading the configured environment-variable names at startup or request time.

## Local-First Default

The default config lives in the repository-local `config/` directory. This is useful for:

- local development
- project-specific behavior
- versioned team defaults

## User-Space Service Support

When running as a user-space service, operators should pass an explicit config path, for example:

```bash
mergemate run-bot --config ~/.config/mergemate/config.yaml
```

This allows a per-user service definition without forcing the repo-local config layout.

## Current Schema Areas

- `default_agent` and `default_provider`
- `providers`: endpoint URL, model, timeout, auth header, auth prefix, and extra headers
- `telegram`: bot token environment variable and runtime mode
- `storage`: workspace root and SQLite database path
- `learning`: recent successful-run memory behavior
- `tools`: package-install permissions and pip executable
- `source_control`: git, GitHub CLI, and GitLab CLI integration settings
- `runtime`: concurrency, request timeout, and progress-update interval
- `workflow_control`: approval requirement, review iteration cap, and role-to-agent mapping
- `agents`: workflow, tool allow-list, provider aliases, parallel mode, and combine strategy
- `logging`: application log level

## Provider Configuration Pattern

Providers are configured by URL so the same schema can target multiple OpenAI-compatible endpoints. Roles such as planner, architect, coder, tester, and reviewer are then mapped to one or more provider aliases through the `agents` section.

This lets one deployment use different models for planning, design, implementation, testing, and review without changing the runtime code.

## Workspace Root

Relative runtime paths are resolved from `storage.workspace_root`. It defaults to `./workspace` relative to the active config file and is created automatically when resolved. This is the base folder for process state such as the SQLite database, final workflow documents under `docs/`, and relative repository working directories unless a path is configured as absolute.

## Runtime Constraints

- `runtime.max_concurrent_runs` must remain a positive integer so accepted work can always make progress.
- `runtime.default_request_timeout_seconds` must remain a positive integer and is the shared upper bound for operator-facing local CLI work such as repository and package-management commands unless a more specific timeout is introduced.
- Provider-level `timeout_seconds` and runtime polling intervals should also remain positive integers so the runtime does not degrade into immediate failures or invalid scheduler behavior.
- Learning controls such as `learning.max_context_items` and `learning.max_result_chars` must remain positive integers so context recall stays bounded and excerpt truncation remains predictable.
- `workflow_control.max_review_iterations` must remain a positive integer so multi-stage runs cannot terminate as a false success without executing any review loop iterations.
- `default_provider` and agent-level `provider_names` must resolve to configured provider aliases. Validation should reject unknown references before startup rather than deferring them to runtime execution.