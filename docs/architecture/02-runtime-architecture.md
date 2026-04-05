# Runtime Architecture

## Architecture Style

The MVP is a modular monolith. It runs as one Python application process or as a small set of cooperating local processes later, but the codebase is structured around explicit boundaries.

## Runtime Paths

### Interactive Path

Responsible for keeping Telegram responsive enough for chat intake while keeping long-running execution out of the update handler:

1. Receive Telegram update.
2. Normalize request.
3. Resolve effective configuration.
4. Determine workflow and initial estimate.
5. Persist a run in `awaiting_confirmation` or `queued` state based on config.
6. Draft a plan with the planner agent. In the current MVP this is still a synchronous LLM call on the intake path, so first-response latency is bounded by planner availability and timeout settings.
7. Return the drafted plan, or auto-dispatch when confirmation is disabled.

### Background Path

Responsible for doing actual agent work:

1. Pull queued run.
2. Load conversation context.
3. Build workflow-specific execution context.
4. Choose the execution shape from the workflow name:
	- `generate_code`: call architect, coder, tester, and reviewer agents with generated workflow documents
	- `debug_code` and `explain_code`: call the selected agent directly after context assembly
5. Persist stage progress and generated artifacts when the workflow uses the multi-stage delivery path.
6. Optionally replan from reviewer concerns up to the configured iteration limit for `generate_code`.
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