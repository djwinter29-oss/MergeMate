# ADR-010: Durable Run Jobs For Runtime Split

- Status: Superseded in part by ADR-011
- Date: 2026-04-06

This ADR still records the decision to introduce durable run jobs as the first split-runtime seam. Its earlier assumption that the runtime would later move toward Postgres-backed persistence is superseded by ADR-011, which narrows the intended deployment target to single-host SQLite plus Redis.

## Context

MergeMate now has a responsive Telegram intake path and an asynchronous planning and execution model, but the actual dispatch mechanism is still process-local. The runtime now persists jobs and pushes job IDs through a local queue backend, while the worker still runs in the same process.

That model is acceptable for the current single-process runtime, but it does not support an honest ingress and worker split. A real split requires a shared system of record for queued work, clear job ownership semantics, and a path toward external queue transport and database-backed coordination.

## Decision

MergeMate will introduce durable run jobs as the first implementation slice for split-runtime support.

The first slice includes these decisions:

- persist planning and execution dispatch in a dedicated `run_jobs` table instead of treating dispatch as only an in-memory worker handoff
- keep `agent_runs` as the user-facing lifecycle record, while `run_jobs` becomes the worker-facing dispatch record
- enforce at most one active job per run and job type through the persistence layer
- update the in-process worker to consume job IDs, claim leases, emit heartbeats, and transition job state through queued, running, and terminal statuses
- keep the runtime single-process for now, while shaping the contracts so later Postgres and Redis adapters can replace the current SQLite and local scheduling behavior

## Consequences

Positive:

- dispatch is now durable across process restarts at the storage layer
- duplicate active planning or execution can be prevented by shared persistence rather than only by in-memory sets
- later worker claim, lease, retry, and broker-driven delivery semantics have a concrete place to attach

Trade-offs:

- the first slice adds schema and repository complexity before the external queue and database adapters exist
- planning completion and outbound Telegram follow-up delivery now use the same background worker path, but still remain inside one application process
- SQLite remains unsuitable for true multi-writer shared-runtime deployment even with durable jobs

## Follow-On Work

- add migration and schema-versioning support suitable for Postgres rollout
- introduce Postgres-backed repositories for runs and jobs
- introduce Redis-backed queue transport for durable worker wake-up and fan-out
- add worker claim, lease, heartbeat, and retry semantics
- replace the local queue backend with a shared broker and move worker coordination onto external infrastructure

## Alternatives Considered

### Keep Direct In-Process Dispatch Until Postgres And Redis Are Ready

Rejected because it would delay the core domain and persistence seam that the later split needs. Durable jobs are the minimal structural step that makes later work incremental instead of a single large rewrite.

### Introduce Redis First Without A Durable Job Record

Rejected because a transport broker without a persistent job record would leave dispatch truth split across transient queue state and run status, which makes duplicate prevention, reconciliation, and operator recovery harder.