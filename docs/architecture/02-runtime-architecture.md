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
5. Persist a queued run.
6. Return acknowledgement immediately.

### Background Path

Responsible for doing actual agent work:

1. Pull queued run.
2. Load conversation context.
3. Build prompt and tool plan.
4. Call one provider or fan out to multiple models in parallel, then optionally invoke tools.
5. Persist progress and artifacts.
6. Send status and final result back to Telegram.

## Modules

- `interfaces.telegram`: inbound and outbound chat communication.
- `application.jobs`: queue dispatch, worker lifecycle, progress estimation.
- `application.use_cases`: prompt submission, status lookup, cancellation.
- `domain`: entities and contracts.
- `infrastructure`: config-backed adapters for provider, persistence, queue, and telemetry.

## Multi-Model Execution

The runtime can map one agent to multiple provider aliases. When `parallel_mode` is enabled for that agent, the background path executes those model calls concurrently and combines the outputs according to the configured strategy.

## Deployment Modes

- Local interactive run: `mergemate run-bot --config ./config/config.yaml`
- User-space service: launch the same command under systemd user service or equivalent with an explicit config path.
- Future webhook mode: same internal architecture with a different Telegram ingress adapter.