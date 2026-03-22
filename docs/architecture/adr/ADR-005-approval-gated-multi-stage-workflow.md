# ADR-005: Approval-Gated Multi-Stage Workflow

## Status

Accepted

## Decision

MergeMate will use an approval-gated workflow. A user request is first turned into a plan that includes design and test approach. Execution continues only after user approval when confirmation is enabled.

For `generate_code`, approval leads into the full multi-stage delivery path. For other supported workflows such as `debug_code` and `explain_code`, approval leads into direct execution after context assembly.

## Rationale

- reduces the chance of implementing the wrong thing
- makes requirements clarification a first-class step
- fits longer-running coding tasks better than immediate one-shot execution
- gives the user a clear control point before costlier work begins

## In Plain Terms

The bot should not jump straight from a prompt to execution by default. It should first confirm what the user wants, show the plan, and then continue into the delivery path required by that workflow.

## Consequences

- runs need an `awaiting_confirmation` state
- the Telegram interface must support plan revision and explicit approval
- planning becomes part of the core runtime, not just prompt formatting
- operators can still disable confirmation in config for faster flows
- not every approved workflow needs the full architect/test/review chain