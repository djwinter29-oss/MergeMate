# Async Job Lifecycle

## Objective

Telegram chat must remain responsive even when agent execution takes longer than a normal request-response cycle.

## State Model

- `queued`: request accepted and waiting for worker pickup.
- `running`: worker is actively executing the workflow.
- `waiting_tool`: a tool or external step is in progress.
- `completed`: result is ready and delivered.
- `failed`: workflow terminated with an error.
- `cancelled`: run was cancelled by user or policy.

## User Experience Contract

When a prompt is submitted:

1. User receives a quick acknowledgement.
2. The acknowledgement includes run ID, selected agent, current status, and rough estimate.
3. Status can later be retrieved with a command.
4. Important transitions may trigger proactive updates.

## Estimation Strategy

The MVP uses static workflow-based estimates instead of dynamic prediction:

- `generate_code`: short-medium execution estimate.
- `debug_code`: medium execution estimate.
- `explain_code`: short execution estimate.

This is intentionally simple and should be replaced later by telemetry-informed estimates.

## Cancellation

Cancellation is best-effort in the MVP:

1. Queued runs can be cancelled before execution.
2. Running jobs can be marked cancelled and checked between steps.
3. Provider calls already in flight may complete before cancellation is observed.

## Failure Handling

- Record terminal status.
- Preserve enough failure detail for debugging.
- Send a concise failure message to the user.
- Avoid leaving the user without a visible terminal state.