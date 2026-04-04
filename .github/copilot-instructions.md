# MergeMate Copilot Instructions

Use the existing project documents as the source of truth and avoid rewriting their content in code comments or chat responses.

## Start Here

- Read `README.md` first for the current MVP scope and repository status.
- Use `docs/architecture/01-system-overview.md` for system goals and runtime shape.
- Use `docs/architecture/02-runtime-architecture.md` for module boundaries and interactive vs background execution paths.
- Use `docs/architecture/04-configuration-model.md` for config resolution, schema areas, and workspace-root behavior.
- Use `docs/architecture/05-plugin-tool-architecture.md` for tool capability boundaries and config-gated behavior.
- Use `docs/architecture/08-security-and-sandboxing.md` for security posture and MVP safety limits.
- Use `docs/architecture/09-operations-and-observability.md` for operator workflows and expected runtime signals.
- Use `docs/architecture/adr/index.md` and the linked ADRs when a change affects architecture, workflow control, provider strategy, deployment mode, or tool boundaries.

## Architecture Rules

- Preserve the Python modular monolith structure under `src/mergemate`.
- Keep concerns in the intended layer:
  - `interfaces`: delivery adapters such as Telegram ingress and outbound messaging.
  - `application`: orchestration, jobs, execution planning, and use cases.
  - `domain`: entities, policies, and contracts.
  - `infrastructure`: persistence, queue, telemetry, LLM, and tool adapters.
  - `config`: settings models, defaults, loading, and logging configuration.
- Keep the Telegram-facing path responsive. Long-running work belongs in the background execution path, not the chat intake path.
- Preserve the current workflow split unless the docs are intentionally updated:
  - `generate_code` uses the multi-stage architecture/design/code/test/review path.
  - `debug_code` and `explain_code` use the direct single-agent path after context assembly.
- Keep provider integrations endpoint-based and config-driven. Do not hard-code vendor-specific behavior into application workflows unless that decision is documented.
- Treat tool usage as capability-based and policy-driven. Mutating behavior and package installation must remain explicitly gated by configuration.

## Configuration Rules

- Keep YAML as the user-facing configuration model.
- Preserve config resolution order:
  1. `src/mergemate/config/defaults.yaml`
  2. repository-local `config/config.yaml`
  3. explicit `--config` path
  4. environment-provided secrets and deployment overrides
- Keep secrets referenced by environment-variable names, not checked-in values.
- Relative runtime paths should remain scoped to `storage.workspace_root`.

## Testing And Quality

- Target Python 3.12 and the existing `src/` package layout.
- Keep tests under `tests/` and mirror the package structure where practical.
- Add or update the smallest relevant test for behavior changes.
- Prefer targeted validation first, then broader validation when touching shared workflow, config, or bootstrap code.
- Use the existing project commands when validating changes:
  - `pytest`
  - `ruff check src tests`

## Change Hygiene

- Make focused changes that match the existing naming, typing, and module organization.
- Update documentation when changing runtime behavior, workflow stages, configuration schema, tool permissions, or operational commands.
- Create or update an ADR when a decision materially changes architecture, deployment, provider abstraction, review/replanning flow, or security boundaries.
- Prefer referencing the architecture documents in explanations instead of duplicating rationale across multiple files.