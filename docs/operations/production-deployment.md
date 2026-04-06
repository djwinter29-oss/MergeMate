# Production Deployment Guidance

## Purpose

This document explains the most production-like deployment MergeMate supports today, plus the target topology for a later ingress/worker split.

## Current Runtime Boundary

MergeMate still runs as a modular monolith with in-process background execution. The Telegram ingress path is responsive, and the current split-runtime slice now persists durable planning and execution jobs, but actual worker pickup still happens through an in-process queue consumer inside the same runtime process.

That means the following are true today:

- one MergeMate process owns both Telegram ingress and background execution
- queued work is durably recorded, but not yet handed to a separate worker service through an external queue
- multiple runtime instances must not share the same SQLite database for active writes

## Supported Production-Like Topology Today

The supported deployment shape today is:

1. reverse proxy with TLS termination
2. one MergeMate application instance in webhook mode
3. one dedicated persistent workspace volume outside the repository checkout

This keeps ingress stable while ensuring SQLite, generated workflow documents, and runtime state survive process restarts.

## External Persistence Guidance Today

MergeMate does not yet support Postgres or another external database backend. The practical production step available now is to externalize the workspace and database paths onto durable storage.

Recommended guidance:

- set `storage.workspace_root` to an absolute path on a persistent volume
- keep `storage.database_path` relative to that workspace root unless you need a separate absolute database path
- use one writer only for a given SQLite database
- back up the workspace root and SQLite database together so run state and generated documents stay consistent

Example config:

```yaml
storage:
  workspace_root: /srv/mergemate/workspace
  database_path: .state/mergemate.db
```

Operational notes:

- do not keep the primary runtime database under the repository checkout for long-lived deployments
- do not place the SQLite database on a shared multi-writer network filesystem unless you fully understand the locking behavior
- if you need higher write concurrency, multiple workers, or shared-writer deployment, that is the point where the roadmap items for Redis and Postgres become necessary

## Example Single-Instance Service Layout

```ini
[Unit]
Description=MergeMate production webhook service
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=%h/src/MergeMate
EnvironmentFile=%h/.config/mergemate/runtime.env
ExecStart=%h/src/MergeMate/.venv/bin/mergemate run-bot --config %h/.config/mergemate/config.yaml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Pair that service with:

- a reverse proxy for TLS
- a persistent host path such as `/srv/mergemate/workspace`
- the readiness probe command `mergemate probe-readiness --wait --config ...` during rollout

## Target Split Topology

The desired later production topology is:

1. Telegram webhook ingress service
2. separate background worker service
3. shared external queue
4. shared external database

That topology is not supported today because:

- worker pickup still happens through in-process asyncio tasks rather than a shared queue consumer
- planning and execution both still run inside the same application process even though they now use the shared job and queue seams
- the current durable job implementation does not yet provide cross-process retries or external broker wake-up
- the current persistence backend is still SQLite rather than a shared external database such as Postgres
- the current queue transport is still local rather than a shared broker such as Redis

## Future Split Example

The following is a target-state example for later roadmap phases, not a runnable deployment with the current codebase:

```text
internet
  -> reverse proxy
  -> mergemate-ingress service
     -> shared Postgres
     -> shared Redis queue
  -> mergemate-worker service
     -> shared Postgres
     -> shared Redis queue
```

Use this as planning guidance only until the worker split, external queue, and external database roadmap items land.