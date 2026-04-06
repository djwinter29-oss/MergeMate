# Evolution Roadmap

## Near-Term

1. Improve progress estimates beyond the current static workflow estimate.
2. Add end-to-end integration tests for startup, config resolution, and Telegram workflow boundaries.
3. Expand provider compatibility beyond the current OpenAI-compatible adapter shape.
4. Strengthen operational logging around stage transitions and failures.
5. Decide whether agent tools become first-class runtime capabilities or remain operator-facing CLI utilities.

## Mid-Term

1. Harden webhook deployment guidance, ingress security, and release validation beyond the initial runtime foundation.
2. Add entry-point based tool plugins once runtime tool invocation is part of the execution loop.
3. Add richer source-control workflows beyond repository inspection.
4. Split bot and worker processes on the same host once the Redis queue transport and worker entrypoint are ready.

## Longer-Term

1. Add Redis-backed queue.
2. Add a dedicated worker process entrypoint.
3. Harden SQLite for split-process operation with WAL, busy-timeout, and startup reconciliation.
4. Add sandboxed code execution.
5. Publish to PyPI.