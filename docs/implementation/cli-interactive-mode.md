# CLI Interactive Mode — Implementation Notes

## Overview

Added two new subcommands to the `mergemate` CLI: `mergemate run` (one-shot prompt
execution) and `mergemate chat` (interactive REPL session).

## Changes

### File: `src/mergemate/cli.py`

**`mergemate run` subcommand** — submits a prompt and waits for completion.

```
mergemate run "<prompt>" [--agent <name>] [--workflow <name>] [--quiet]
                        [--timeout <seconds>] [--session <name>]
```

- Bootstraps the full runtime (config, DB, LLM clients) via `bootstrap()`
- Calls `SubmitPromptUseCase.execute()` inside `asyncio.run()` to submit the prompt
- Polls `GetRunStatusUseCase` until the run reaches a terminal status
- `--quiet`: suppresses banner/estimate output, prints only the final result
- `--timeout N`: raises `TimeoutError` (exit code 1) if the run exceeds N seconds
- `--session <name>`: uses a deterministic `chat_id` derived from the session name
  so subsequent runs with the same name share conversation history
- Exit codes: 0 = success, 1 = timeout, 2 = runtime error

**`mergemate chat` subcommand** — interactive REPL for multi-turn conversation.

```
mergemate chat [--session <name>] [--agent <name>]
```

- Creates or resumes a named session (persisted via SQLite)
- Shows conversation history on resume
- Runs a `while True` loop: `input("> ")` → submit → poll → print result
- Type `exit`, `quit`, or `Ctrl+C` to leave

### Session naming

Session names are hashed into deterministic positive integers used as `chat_id`:

```python
from hashlib import blake2s

digest = blake2s(f"cli:{session_name}".encode("utf-8"), digest_size=8).digest()
session_id = 1 + (int.from_bytes(digest, "big") % (2**31 - 2))
```

This ensures:
- Same name → same DB conversation history
- Different names → isolated sessions
- No argument → unique anonymous session (one-shot)

## Design decisions

- Used `asyncio.run()` to bridge the async `SubmitPromptUseCase.execute()` into
  the synchronous typer CLI. This is the same pattern used elsewhere in the
  codebase for async-from-sync calls.
- `require_confirmation` is auto-disabled for CLI sessions — the user is already
  sitting at their terminal and explicitly asked for execution.
- Polling interval is 2 seconds by default with a configurable `--poll-interval`.
- The conversation is wired through `context_service.append_message()` so both
  `run` and `chat` persist their dialogue, making session resumption work.