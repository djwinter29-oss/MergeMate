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
2. If confirmation is enabled, the acknowledgement includes the drafted plan, run ID, and rough estimate for post-approval execution.
3. If confirmation is disabled, the run is queued immediately and the acknowledgement states that execution already started.
4. Status can later be retrieved with a command.
5. Important transitions trigger proactive progress updates while the run is non-terminal.

## Dispatch Semantics

- A run is intended to execute once per approved dispatch.
- Duplicate enqueue attempts for the same active run are treated as a correctness bug, not as an accepted retry mechanism.
- The worker and orchestrator should therefore refuse to restart runs that are already active or terminal.
- Because run state is persisted in SQLite, duplicate-dispatch protection must hold across runtime instances that share the same database, not only inside one in-memory worker.
- If resumable or at-least-once execution is introduced later, that behavior should be designed explicitly rather than emerging from duplicate background dispatch.

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