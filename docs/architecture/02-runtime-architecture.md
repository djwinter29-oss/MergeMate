# Runtime Architecture

## Architecture Style

The MVP is a modular monolith. It currently runs as one Python application process, but the codebase is now being prepared for a later ingress and worker split through shared durable job records and externalized coordination.

## Runtime Paths

### Interactive Path

Responsible for keeping Telegram responsive enough for chat intake while keeping long-running execution out of the update handler:

1. Receive Telegram update.
2. Normalize request.
3. Resolve effective configuration.
4. Determine workflow and initial estimate.
5. Persist a run in `awaiting_confirmation` or `queued` state based on config.
6. Return an immediate acknowledgement with run ID and estimate.

### Background Planning Path

Responsible for completing planning after intake acknowledgement:

1. Load the persisted run.
2. Draft a plan with the planner agent.
3. Persist the drafted plan.
4. Send the drafted plan back to Telegram as a follow-up message when confirmation is required.
5. Auto-dispatch the run and send an execution-started follow-up message when confirmation is disabled.

Today this path still runs inside the same runtime process as Telegram delivery, but it already uses the same durable job and queue model as execution. The target split keeps that model and moves the worker consumer behind external queue and database adapters so ingress can stay stateless beyond request persistence and outbound acknowledgements.

### Background Path

Responsible for doing actual agent work:

1. Pull queued planning or execution job.
2. Resolve the target run from shared persistence.
2. Load conversation context.
3. Build workflow-specific execution context.
4. Choose the execution shape from the workflow name:
	- `generate_code`: call architect, coder, tester, and reviewer agents with generated workflow documents
	- `debug_code` and `explain_code`: call the selected agent directly after context assembly
5. Persist stage progress and generated artifacts when the workflow uses the multi-stage delivery path.
6. Optionally replan from reviewer concerns up to the configured iteration limit for `generate_code`.
7. Send periodic status updates and the final result back to Telegram.

The current split-runtime slice introduces durable planning and execution jobs even while the worker still lives in-process. Later slices replace the local queue backend with an external transport and move claim, lease, and retry semantics onto shared infrastructure suitable for separate worker processes.

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
- Current webhook mode: same internal architecture with a different Telegram ingress adapter.
- Future split mode: one ingress process plus one or more worker processes sharing durable jobs, external queue transport, and external database state.

See `docs/diagrams/index.md` for the corresponding container and sequence views.