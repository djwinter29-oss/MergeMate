# ADR-003: Non-Blocking Telegram Jobs

## Status

Accepted

## Decision

The Telegram bot must acknowledge requests quickly and hand off longer work to a background execution path.

## Rationale

- improves perceived responsiveness
- supports status reporting and cancellation
- prevents provider latency from dominating chat interaction quality