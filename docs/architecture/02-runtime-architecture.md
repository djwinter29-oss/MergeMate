# Runtime Architecture

## Architecture Style

The MVP is a modular monolith. It runs as one Python application process or as a small set of cooperating local processes later, but the codebase is structured around explicit boundaries.

## Runtime Paths

### Interactive Path

Responsible for keeping Telegram responsive:

1. Receive Telegram update.
2. Normalize request.
3. Resolve effective configuration.
4. Determine workflow and initial estimate.
5. Persist a run in `awaiting_confirmation` or `queued` state based on config.
6. Draft a plan with the planner agent.
7. Return the drafted plan immediately, or auto-dispatch when confirmation is disabled.

### Background Path

Responsible for doing actual agent work:

1. Pull queued run.
2. Load conversation context.
3. Build design and implementation context.
4. Call the architect, coder, tester, and reviewer agents using their configured provider aliases.
5. Persist stage progress and generated artifacts.
6. Optionally replan from reviewer concerns up to the configured iteration limit.
7. Send periodic status updates and the final result back to Telegram.

## Modules

- `interfaces.telegram`: inbound and outbound chat communication.
- `application.jobs`: queue dispatch, worker lifecycle, progress estimation.
- `application.use_cases`: prompt submission, status lookup, cancellation.
- `domain`: entities and contracts.
- `infrastructure`: config-backed adapters for provider, persistence, queue, and telemetry.

## Multi-Model Execution

The runtime can map one agent to multiple provider aliases. When `parallel_mode` is enabled for that agent, the background path executes those model calls concurrently and combines the outputs according to the configured strategy.

Provider definitions are endpoint-based, not type-based. This allows one workflow to mix OpenAI-compatible endpoints from different vendors, such as OpenAI, Azure-hosted deployments, Kimi, or DeepSeek, as long as they accept the current adapter request shape.

## Deployment Modes

- Local interactive run: `mergemate run-bot --config ./config/config.yaml`
- User-space service: launch the same command under systemd user service or equivalent with an explicit config path.
- Future webhook mode: same internal architecture with a different Telegram ingress adapter.

See `docs/diagrams/index.md` for the corresponding container and sequence views.