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

## Estimation Strategy

The MVP uses static workflow-based estimates instead of dynamic prediction:

- `generate_code`: short-medium execution estimate.
- `debug_code`: medium execution estimate.
- `explain_code`: short execution estimate.

This is intentionally simple and should be replaced later by telemetry-informed estimates.

## Cancellation

Cancellation is best-effort in the MVP:

1. Queued runs can be cancelled before execution.
2. Running multi-stage jobs can be marked cancelled and checked between design, implementation, testing, review, and replanning steps.
3. Direct-execution workflows still depend on provider completion boundaries, so cancellation is only observed before or after the direct model call.
4. Provider calls already in flight may complete before cancellation is observed.

## Failure Handling

- Record terminal status.
- Preserve enough failure detail for debugging.
- Send a concise failure message to the user.
- Avoid leaving the user without a visible terminal state.