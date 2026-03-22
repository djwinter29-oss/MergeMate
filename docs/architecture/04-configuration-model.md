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

## Planned Schema Areas

- default agent and provider
- provider definitions and model selection
- Telegram runtime mode
- concurrency and timeout limits
- agent-to-workflow mapping
- enabled tools per agent