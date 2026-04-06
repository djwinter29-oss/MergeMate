# Async Job Lifecycle

## Objective

Telegram chat must remain responsive even when agent execution takes longer than a normal request-response cycle.

## State Model

- `awaiting_confirmation`: plan drafted and waiting for the user to approve or revise it.
- `queued`: request accepted and waiting for worker pickup.
- `running`: worker is actively executing the workflow.
- `waiting_tool`: a tool or external step is in progress.
- `completed`: result is ready and delivered.
- `failed`: workflow terminated with an error.
- `cancelled`: run was cancelled by user or policy.

## User Experience Contract

When a prompt is submitted:

1. User receives a quick acknowledgement.
2. The acknowledgement includes the run ID and a rough estimate for later execution.
3. Planning completes asynchronously after acknowledgement.
4. If confirmation is enabled, MergeMate sends the drafted plan as a follow-up message and then waits for approval or revision.
5. If confirmation is disabled, MergeMate auto-dispatches after planning completes and sends a follow-up message that execution has started.
6. Status can later be retrieved with a command.
7. Important transitions trigger proactive progress updates while the run is non-terminal.

Approval and revision are only valid after the plan has been persisted. If the user tries either action while planning is still running, the bot responds with a planning-in-progress message.

## Dispatch Semantics

- A run is intended to execute once per approved dispatch.
- Duplicate enqueue attempts for the same active run are treated as a correctness bug, not as an accepted retry mechanism.
- The worker and orchestrator should therefore refuse to restart runs that are already active or terminal.
- Because run state is persisted in SQLite, duplicate-dispatch protection must hold across local runtime processes that share the same database file, not only inside one in-memory worker.
- The current durable-job implementation therefore persists planning and execution jobs separately from `agent_runs` and enforces one active job per run and job type at the database layer.
- If resumable or at-least-once execution is introduced later, that behavior should be designed explicitly rather than emerging from duplicate background dispatch.

## Durable Job Model

- Dispatch now has its own persisted job record instead of existing only as an in-memory worker handoff.
- A queued planning or execution job references exactly one run.
- Worker startup claims the job with lease metadata and transitions it into `running` before orchestration begins.
- Worker heartbeats refresh lease metadata while the job is active.
- Worker completion or failure transitions the job into a terminal status and keeps the run as the user-facing source of truth.
- The current slice still uses SQLite and an in-process queue backend, so retries, Redis-backed delivery, and crash-recovery reconciliation remain later steps in the single-host split-runtime rollout.

## Estimation Strategy

The MVP uses static workflow-based estimates instead of dynamic prediction:

- `generate_code`: short-medium execution estimate.
- `debug_code`: medium execution estimate.
- `explain_code`: short execution estimate.

This is intentionally simple and should be replaced later by telemetry-informed estimates.

## Cancellation

Cancellation is intentionally limited in the MVP:

1. User-driven cancellation through Telegram is only supported while a run is in `awaiting_confirmation`.
2. Once a run has been approved and moved into `queued`, `running`, or `waiting_tool`, Telegram does not offer a user cancellation path.
3. Shutdown or policy interruptions may still move a run into `failed` or `cancelled`, but that is a runtime safety behavior rather than an interactive user control.
4. Broader queued and running cancellation remains a future enhancement.

## Failure Handling

- Record terminal status.
- Preserve enough failure detail for debugging.
- Send a concise failure message to the user.
- Avoid leaving the user without a visible terminal state.
- Treat delivery-channel failures such as Telegram send errors as transient operational issues when possible: log them, preserve run state, and keep polling-based progress delivery alive for later retries.