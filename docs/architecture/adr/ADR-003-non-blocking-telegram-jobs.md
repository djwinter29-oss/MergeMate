# ADR-003: Non-Blocking Telegram Jobs

## Status

Accepted

## Decision

The Telegram bot must acknowledge requests quickly and hand off longer work to a background execution path.

## Rationale

- improves perceived responsiveness
- supports status reporting and cancellation
- prevents provider latency from dominating chat interaction quality

## In Plain Terms

Telegram should answer quickly even if planning or model calls take a while. MergeMate therefore splits request intake from long-running execution and reports progress while the work continues.

## Consequences

- users get a fast acknowledgement instead of waiting on model latency
- long-running work needs a worker path and run persistence
- status, approval, and cancellation become first-class workflow features