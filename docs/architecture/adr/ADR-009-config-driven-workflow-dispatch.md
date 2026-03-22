# ADR-009: Config-Driven Workflow Dispatch

## Status

Accepted

## Decision

MergeMate will treat workflow selection as a configuration concern owned by agent definitions, and it will keep workflow execution policy in the application runtime rather than in a separate router package.

The current runtime uses two execution shapes:

- `generate_code` uses the approval-gated multi-stage pipeline with design, implementation, testing, review, and bounded replanning
- `debug_code` and `explain_code` use approval plus direct single-agent execution after context assembly

## Rationale

- the actual workflow name already comes from the configured agent definition
- the orchestrator must own execution-shape decisions because it controls status transitions, artifacts, and cancellation points
- a separate workflow router package created a second, unused abstraction that drifted away from real behavior

## In Plain Terms

There is one source of truth for which workflow a request uses: the configured agent. Once the run starts, the application runtime decides whether that workflow needs the full coding pipeline or just one direct model call.

## Consequences

- dead workflow router and policy placeholders should not remain in the codebase
- adding a new workflow now requires two explicit decisions:
  - which agent config selects it
  - whether it uses direct execution or the multi-stage delivery pipeline
- architecture docs must describe both workflow shapes instead of implying that every workflow always runs design, testing, and review