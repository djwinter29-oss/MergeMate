# ADR-011: Single-Host SQLite And Redis Runtime Target

- Status: Accepted
- Date: 2026-04-06

## Context

MergeMate now has durable planning and execution jobs, lease-aware worker coordination, and a clear seam for queue-backed dispatch. Earlier planning documents treated Postgres plus Redis as the likely end state for ingress and worker separation.

That is not the real deployment target for this project. MergeMate is expected to remain single-host. The remaining split-runtime work is about separating ingress and worker processes on the same machine, not about scaling across multiple hosts or introducing a service-grade relational database.

## Decision

MergeMate will target a single-host split runtime built on:

- SQLite as the system of record for runs, jobs, messages, learning state, and generated artifacts
- Redis as the queue transport for dispatch, worker wake-up, and local process decoupling
- one persistent local workspace root shared by the ingress and worker processes on the same host
- no Postgres rollout on the current roadmap unless product requirements materially change

This ADR supersedes the deployment-target assumption in ADR-010 that later slices would move toward Postgres-backed persistence.

## Consequences

Positive:

- operations stay simpler because the system avoids a separate database service
- backups and recovery stay centered on the workspace root and SQLite database
- Redis can be used for transport without becoming another source of truth
- ingress and worker can split honestly without pretending the project needs multi-host coordination

Trade-offs:

- the deployment remains intentionally single-host
- SQLite hardening matters more because crash recovery and local process coordination depend on one database file
- future scaling work should assume vertical scaling and local process isolation, not horizontal database-backed growth

## Operational Requirements

- keep the SQLite database on local persistent storage
- enable WAL mode and a busy timeout before relying on separate ingress and worker processes
- do not treat Redis as durable state; SQLite remains the recovery and reconciliation source of truth
- add startup reconciliation for stale queued or leased jobs before calling the split runtime production-ready

## Follow-On Work

- add a Redis-backed queue adapter
- add a dedicated worker process entrypoint
- harden SQLite startup and repository behavior for split-process operation
- document the single-host deployment boundary explicitly in production runbooks

## Alternatives Considered

### Postgres Plus Redis

Rejected because the project does not need multi-host deployment, shared-database horizontal scaling, or the operational overhead of a separate database service.

### SQLite Only With No Redis

Rejected because separate ingress and worker processes still need a practical queue transport and wake-up mechanism. Redis solves that cleanly without changing the system of record.