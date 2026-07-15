# Architecture Design: Feature Gaps — Session Resume and Search Evolution

- Status: Historical design note (partially implemented)
- Date: 2026-05-10
- Review: Architecture Review P2.1 — 3 Feature Gaps from deep review

> Update 2026-06-02: the CLI command surface and search stack have now shipped.
> `mergemate run`, `mergemate chat`, `mergemate search-runs`, `mergemate search-conversations`,
> and unified `mergemate search` are available today, and search is backed by SQLite FTS5 with
> phrase-aware ranking plus a LIKE fallback when FTS is unavailable. `mergemate resume` is also
> available for direct reattachment, and it now scans the full session history instead of relying on
> a fixed lookup window. This document now serves as a historical design note for the remaining
> session-recovery UX work.

---

## 1. Problem Statement

The deep review originally identified 3 feature gaps that were documented in tickets but never implemented:

1. **Missing CLI commands** — `mergemate run` and `mergemate chat` were designed (see `docs/implementation/cli-interactive-mode.md`) and are now implemented in `src/mergemate/cli.py`.
2. **Session resume capability** — The `--session <name>` CLI option exists, but no resume-from-last-unsaved-session logic exists when the user re-enters a session whose last run was interrupted or incomplete.
3. **Conversation search** — The original keyword-search gap has now been closed by FTS5-backed search with phrase-aware ranking and a LIKE fallback.

The original review grouped these gaps because they touched the same CLI surface (`cli.py`) and conversation/session data model. The shipped command and search surface is now complete; the remaining work is about richer session recovery.

---

## 2. Current State Analysis

### 2.1 CLI Framework

- **Framework**: `typer` with subcommands
- **Current commands**: `run-bot`, `validate-config`, `print-config-path`, `probe-readiness`, `install-package`, `repo-context`, `platform-auth`, `search-runs`, `search-conversations`, `search`, `run`, `chat`
- **Historical gap**: `mergemate run` (one-shot prompt execution) and `mergemate chat` (interactive REPL) were once missing, but are now implemented — see `docs/implementation/cli-interactive-mode.md`
- **Telegram bot handlers** (for reference): `/start`, `/status`, `/tools`, `/approve`, `/cancel` plus free-text prompt handling

### 2.2 Session & Conversation Data Model

- `conversation_messages` table: `(id, chat_id, role, content, created_at)` — indexed on `(chat_id, created_at DESC)`
- `agent_runs` table: `(run_id, chat_id, user_id, agent_name, workflow, status, current_stage, prompt, ..., result_text, error_text, created_at, updated_at)` — indexed on `(chat_id, created_at DESC)`
- `ContextService`: thin wrapper around `SQLiteConversationRepository` — `append_message()` and `load_recent_messages()`
- `GetRunStatusUseCase`: looks up runs by `run_id` or latest run for a `chat_id`
- `CancelRunUseCase`: cancels runs in `awaiting_confirmation` status
- Session identity: `chat_id` is derived from a stable digest of `cli:{session_name}` so the same name maps to the same session across processes

**Current data model notes:**
- The runtime now maintains SQLite FTS5 indexes for `conversation_messages.content` and run search text so search can rank and phrase-match results instead of relying only on plain keyword scans.
- `agent_runs.prompt` and `agent_runs.result_text` remain part of the search surface through the consolidated FTS search text and LIKE fallback.
- There is still no `conversation_messages.run_id` foreign key — messages are linked only by `chat_id`.
- There is still no "last active run" tracking for session resume; the CLI finds resumable runs by scanning the session's run history at entry time.

### 2.3 Session Resume Gap

Currently:
- `mergemate chat --session <name>` creates a deterministic `chat_id` and uses the existing conversation history
- The CLI now prints the latest incomplete run summary when `run` or `chat` re-enters a named session, which improves continuity. Direct reattachment is handled by `mergemate resume`.
- But if a user leaves a session mid-run, the remaining gap is still the passive UX path inside `run`/`chat`:
  - Detecting the "last incomplete run" is implemented through the resume lookup
  - `resume` can reattach and optionally approve a pending run
  - automatic watcher reattachment from a plain session re-entry is still a manual action

### 2.4 Search State

Currently:
- `mergemate search-runs` searches stored run prompts, results, and metadata through the consolidated FTS search path, with a LIKE fallback if FTS is unavailable.
- `mergemate search-conversations` searches saved chat messages through the consolidated FTS search path, with a LIKE fallback if FTS is unavailable.
- `mergemate search` combines matching runs and messages into one recency-ordered result set.
- The remaining search-adjacent gap is not ranking support; it is richer session recovery UX, especially automatic reattachment when re-entering an in-flight session.

---

## 3. Historical Design: CLI Commands (`mergemate run` + `mergemate chat`)

The interface and sketches below are preserved from the original proposal. The commands now ship in `src/mergemate/cli.py`.

### 3.1 `mergemate run`

**Purpose**: One-shot prompt submission from CLI that waits for completion.

**Interface**:
```
mergemate run "<prompt>" [--agent <name>] [--workflow <name>] [--quiet]
                        [--timeout <seconds>] [--session <name>]
                        [--poll-interval <seconds>]
```

**Implementation sketch**:

```python
@app.command("run")
def run_cli(
    prompt: str,
    agent: str | None = typer.Option(None, help="Agent name"),
    workflow: str | None = typer.Option(None, help="Workflow name (generate_code, debug_code, explain_code)"),
    quiet: bool = typer.Option(False, help="Suppress banner/estimate; print only the final result"),
    timeout: float | None = typer.Option(None, min=1, help="Max seconds to wait for completion"),
    session: str | None = typer.Option(None, help="Session name for persistent conversation history"),
    poll_interval: float = typer.Option(2.0, min=0.5, help="Polling interval in seconds"),
) -> None:
    runtime = bootstrap(config)
    chat_id = _resolve_session_chat_id(session)
    agent_name = agent or runtime.settings.default_agent
    resolved_workflow = _resolve_workflow(agent_name, workflow, runtime)

    # Override confirmation for CLI sessions
    with _temporary_auto_approve(runtime):
        result = asyncio.run(runtime.services.submit_prompt.execute(
            chat_id=chat_id,
            user_id=_CLI_USER_ID,
            agent_name=agent_name,
            workflow=resolved_workflow,
            prompt=prompt,
        ))

    # Poll until terminal
    deadline = time.monotonic() + (timeout or float("inf"))
    while time.monotonic() < deadline:
        run = runtime.services.get_run_status.execute(result.run_id)
        if run is None:
            raise typer.Exit(code=2)
        if run.status in RunStatus.terminal_statuses():
            _print_result(run, quiet=quiet)
            return
        time.sleep(poll_interval)

    raise typer.Exit(code=1)  # timeout
```

**Key design decisions**:
- Uses `asyncio.run()` to bridge async use cases into sync typer commands — same pattern used elsewhere
- Auto-disables `require_confirmation` for CLI sessions (user explicitly asked for execution)
- Deterministic `chat_id` via session name hash ensures conversation persistence
- Exit codes: 0 = success, 1 = timeout, 2 = runtime error

### 3.2 `mergemate chat`

**Purpose**: Interactive REPL for multi-turn conversation with session persistence.

**Interface**:
```
mergemate chat [--session <name>] [--agent <name>]
               [--timeout <seconds>] [--poll-interval <seconds>]
```

**Implementation sketch**:

```python
@app.command("chat")
def chat_cli(
    session: str | None = typer.Option(None, help="Session name"),
    agent: str | None = typer.Option(None),
    timeout: float | None = typer.Option(None, min=1),
    poll_interval: float = typer.Option(2.0, min=0.5),
) -> None:
    runtime = bootstrap(config)
    chat_id = _resolve_session_chat_id(session)
    agent_name = agent or runtime.settings.default_agent
    resolved_workflow = _resolve_workflow(agent_name, None, runtime)

    # Print existing conversation history on resume
    _print_conversation_history(runtime, chat_id)

    with _temporary_auto_approve(runtime):
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if user_input.lower() in ("exit", "quit"):
                break
            if not user_input:
                continue

            # Submit and poll as in `mergemate run`
            ...
```

**Key design decisions**:
- Reuses the same `submit_prompt`, `complete_planning`, and polling loop as `mergemate run`
- Shows conversation history on resume via `ContextService.load_recent_messages()`
- `exit`, `quit`, or `Ctrl+C` to leave
- All conversation history persists across sessions via the same `chat_id` hashing

---

## 4. Design: Session Resume Capability

### 4.1 What "Resume" Means

Session resume has two meanings, both addressed here:

1. **Conversation resume** (passive) — When a user re-enters a named session, they see their previous conversation history. Already works via the deterministic `chat_id` hash and `context_service.load_recent_messages()`. Low risk, well understood.

2. **Run resume** (active) — When a user re-enters a session that had a run in a non-terminal state (e.g., `awaiting_confirmation`, `queued`, `running`, `failed`), the CLI should detect this, offer options, and let the user continue from where they left off.

### 4.2 Run Resume Design

**Data model change**: Add a `last_active_run_id` column to a new lightweight lookup, or reuse the existing `list_for_chat(chat_id, limit=1)` pattern in `GetRunStatusUseCase`.

No schema change needed — `list_for_chat` already returns the latest run for a chat sorted by `created_at DESC`.

**Detection on session entry**:

```python
def _detect_resumable_run(runtime, chat_id: int) -> AgentRun | None:
    """Return the latest non-terminal run for the chat, if one exists."""
    runs = runtime.persistence.run_repository.list_for_chat(chat_id, limit=1)
    if not runs:
        return None
    run = runs[0]
    if run.status in RunStatus.terminal_statuses():
        return None
    return run
```

**User interaction on resume**:

```
$ mergemate chat --session my-feature
Resuming session "my-feature"...

[!] Found an incomplete run from 5 minutes ago:
    Run ID: a1b2c3d4
    Prompt: "Add rate limiting to the API"
    Status: awaiting_confirmation
    Stage: planning (plan drafted)

Options:
  1. Show the draft plan
  2. Approve and continue
  3. Revise the prompt
  4. Cancel and start fresh
  5. Ignore (start new run)

Choose [1-5]:
```

**Implementation approach**:
- New module: `src/mergemate/application/services/session_service.py`
- `SessionService` wraps `RunRepository` and `ContextService` to provide resume-aware session operations:
  - `detect_resumable_run(chat_id) -> AgentRun | None`
  - `build_resume_prompt(run) -> str` (formatted resume options)
  - `handle_resume_choice(chat_id, run, choice) -> ActionTaken`
- The CLI's `chat` and `run` commands call `SessionService.detect_resumable_run()` at startup

**New service Protocol** (in `protocols.py`):

```python
class SessionServiceProtocol(Protocol):
    def detect_resumable_run(self, chat_id: int) -> AgentRun | None: ...
    def get_resume_summary(self, run: AgentRun) -> dict: ...
```

### 4.3 Auto-Resume for `mergemate run`

When `--session` is specified and a resumable run exists, the `run` command can auto-resume if the prompt matches the previous prompt, or prompt the user. For simplicity, the MVP approach is:

- `mergemate run --session <name> "new prompt"` — if a resumable run exists, cancel it and start fresh
- `mergemate run --session <name> --resume` — attempt to resume the last non-terminal run (re-submit for execution)

### 4.4 Edge Cases

| Scenario | Behavior |
|---|---|
| Session has no previous runs | Fresh start, no resume prompt |
| Session has a completed run | Show history, let user start a new run |
| Session has a failed run | Offer to retry with same or modified prompt |
| Session has a cancelled run | Treat as terminal — no resume prompt |
| Session has a queued/running run | Warn user, offer to wait or cancel |
| Session has an `awaiting_confirmation` run | Offer to show plan, approve, revise, or cancel |

---

## 5. Historical Design: Conversation Search

The existing CLI now supports keyword search. The sketches below describe the remaining FTS-backed search evolution.

### 5.1 Requirements

- Keyword search across `conversation_messages.content`
- Keyword search across `agent_runs.prompt` and `agent_runs.result_text`
- Filter by `chat_id` (session-scoped search)
- Filter by date range
- Sort by relevance or recency
- Output structured results for both CLI and Telegram

### 5.2 Approach: SQLite FTS5

**Rationale**: MergeMate already uses SQLite as its single data store. Adding an FTS5 virtual table avoids introducing Elasticsearch, Meilisearch, or any external dependency. SQLite FTS5 supports:
- `MATCH` queries (Boolean, prefix, phrase)
- `rank` for relevance ordering
- Triggers for automatic index maintenance
- `content=` option for external content tables (avoids data duplication)

### 5.3 Schema Changes

```sql
-- FTS5 virtual table over conversation_messages
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts
USING fts5(
    content,
    content=conversation_messages,
    content_rowid=id,
    tokenize='porter unicode61'
);

-- FTS5 virtual table over agent_runs prompt + result_text
CREATE VIRTUAL TABLE IF NOT EXISTS agent_runs_fts
USING fts5(
    prompt,
    result_text,
    content=agent_runs,
    content_rowid=run_id,
    tokenize='porter unicode61'
);
```

**Triggers for automatic index maintenance**:

```sql
-- After INSERT on conversation_messages
CREATE TRIGGER IF NOT EXISTS conversation_messages_ai AFTER INSERT ON conversation_messages BEGIN
    INSERT INTO conversation_messages_fts(rowid, content) VALUES (new.id, new.content);
END;

-- After UPDATE on conversation_messages.content
CREATE TRIGGER IF NOT EXISTS conversation_messages_ad AFTER DELETE ON conversation_messages BEGIN
    INSERT INTO conversation_messages_fts(conversation_messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS conversation_messages_au AFTER UPDATE ON conversation_messages BEGIN
    INSERT INTO conversation_messages_fts(conversation_messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO conversation_messages_fts(rowid, content) VALUES (new.id, new.content);
END;
```

For `agent_runs`, FTS rebuild is simpler due to low write volume — can be done on `UPDATE` of `result_text` or periodically. Given that `agent_runs` rows change state during a run's lifecycle, a rebuild trigger is less critical than the `conversation_messages` one.

**Initial data backfill** in `SQLiteDatabase.initialize()`:

```python
# Backfill existing conversation messages into FTS
cursor = connection.execute("SELECT COUNT(*) FROM conversation_messages_fts")
fts_count = cursor.fetchone()[0]
cursor = connection.execute("SELECT COUNT(*) FROM conversation_messages")
msg_count = cursor.fetchone()[0]
if fts_count < msg_count:
    connection.execute("INSERT INTO conversation_messages_fts(rowid, content) "
                       "SELECT id, content FROM conversation_messages "
                       "WHERE id > (SELECT COALESCE(MAX(rowid), 0) FROM conversation_messages_fts)")
```

### 5.4 Repository Changes

**New repository** — `SQLiteConversationSearchRepository`:

```python
@dataclass
class SearchResult:
    type: Literal["message", "run"]
    chat_id: int
    snippet: str
    created_at: datetime
    rank: float
    # For messages
    role: str | None = None
    # For runs
    run_id: str | None = None
    workflow: str | None = None
    status: str | None = None

class SQLiteConversationSearchRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def search_messages(
        self,
        query: str,
        chat_id: int | None = None,
        limit: int = 20,
    ) -> list[SearchResult]: ...

    def search_runs(
        self,
        query: str,
        chat_id: int | None = None,
        limit: int = 10,
    ) -> list[SearchResult]: ...

    def search_all(
        self,
        query: str,
        chat_id: int | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Combined search: messages first (by rank), then runs."""
        ...
```

### 5.5 Service and CLI Integration

**New service** — `SearchService`:

```python
class SearchService:
    def __init__(self, search_repository: SQLiteConversationSearchRepository) -> None:
        self._repository = search_repository

    def search(
        self,
        query: str,
        chat_id: int | None = None,
        limit: int = 20,
    ) -> list[SearchResult]: ...
```

**New CLI command** — `mergemate search`:

```
mergemate search "<query>" [--session <name>] [--limit <N>]
                           [--chat-id <id>] [--json]
```

**New Telegram bot command** — `/search <query>`:

Added to `handlers.py` as a `CommandHandler("search", search_command)` and registered in `bot.py`.

### 5.6 Presenter/Formatting

Both CLI and Telegram need formatted search results:

**CLI output**:
```
$ mergemate search "rate limit" --session my-feature
Found 3 results:

1. Message (user) — 2026-05-09 14:32:
   "Can you add rate... limiting to the API?"
                                    ^^^^^^^^

2. Run a1b2c3d4 — generate_code (completed) — 2026-05-09 14:33:
   Prompt: "Add rate limiting to the API"
   Result: "Added a token bucket rate limiter..."

3. Message (assistant) — 2026-05-09 14:35:
   "The rate limiter uses a token bucket algorithm..."
```

**Telegram output**: Same content, truncated to Telegram message limits via existing `send_text_chunks`.

### 5.7 Performance Considerations

- FTS5 indexes are stored in the same SQLite file — no separate process required
- Initial backfill for an existing database with 10K messages is sub-second
- Trigger overhead on `INSERT` is negligible (<1ms per message)
- `agent_runs_fts` has much lower volume (hundreds, not thousands), so simpler rebuild triggers are acceptable
- `search_messages` with `chat_id` filter: `SELECT ... FROM conversation_messages_fts WHERE content MATCH ? AND rowid IN (SELECT id FROM conversation_messages WHERE chat_id = ?)` — uses the FTS index for the MATCH filter and the existing `idx_conversation_messages_chat_id_created_at` for the chat_id filter

---

## 6. Bootstrap and Wiring Changes

### 6.1 `bootstrap.py` additions

The `PersistenceContext` and `ServiceContext` dataclasses need new fields:

```python
@dataclass(slots=True)
class PersistenceContext:
    # ... existing fields ...
    search_repository: SQLiteConversationSearchRepository  # NEW

@dataclass(slots=True)
class ServiceContext:
    # ... existing fields ...
    session_service: SessionService  # NEW
    search_service: SearchService    # NEW
```

The `bootstrap()` function:

1. Creates `SQLiteConversationSearchRepository(database)` after `database.initialize()`
2. Creates `SessionService(run_repository=run_repository)`
3. Creates `SearchService(search_repository=search_repository)`
4. Registers both in `ServiceContext`

### 6.2 `SQLiteDatabase.initialize()` changes

Add to the DDL block:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS conversation_messages_fts
USING fts5(content, content=conversation_messages, content_rowid=id, tokenize='porter unicode61');

CREATE VIRTUAL TABLE IF NOT EXISTS agent_runs_fts
USING fts5(prompt, result_text, content=agent_runs, content_rowid=run_id, tokenize='porter unicode61');
```

Plus the rebuild triggers and backfill logic described in §5.3.

---

## 7. Acceptance Criteria Verification

| # | Criterion | Verification |
|---|---|---|
| 1 | `mergemate run "<prompt>"` works as one-shot execution | Run the command — should prompt → plan → execute → print result |
| 2 | `mergemate chat` provides interactive REPL | Enter chat, type prompts, see responses, exit cleanly |
| 3 | `--session <name>` persists conversation history across invocations | Run two prompts with same session name, verify history via search |
| 4 | Session resume detects incomplete runs | Start a run, interrupt, re-enter session — should prompt with resume options |
| 5 | Session resume can approve/revise/cancel a pending run | Test each option in the resume prompt menu |
| 6 | `mergemate search "<query>"` returns results | Search for a known word — should return matching messages and runs |
| 7 | `/search <query>` Telegram command works | Send `/search rate limit` — should return formatted results |
| 8 | FTS indexes are maintained automatically | Insert a message, search — should find it immediately |
| 9 | Existing databases are backfilled on upgrade | Run against an existing `.db` file — FTS tables should populate |
| 10 | All new components have Protocol definitions | Check `protocols.py` for `SessionServiceProtocol`, `SearchServiceProtocol` |

---

## 8. Implementation Order

1. **Phase A — CLI commands** (highest priority, least dependency)
   - Add `mergemate run` command to `cli.py`
   - Add `mergemate chat` command to `cli.py`
   - Add shared helpers: `_resolve_session_chat_id()`, `_temporary_auto_approve()`, `_print_conversation_history()`, `_poll_until_terminal()`

2. **Phase B — FTS search** (no dependency on Phase A)
   - Add FTS5 tables, triggers, and backfill to `SQLiteDatabase.initialize()`
   - Add `SQLiteConversationSearchRepository` with `search_messages()`, `search_runs()`, `search_all()`
   - Add `SearchService` and `SearchServiceProtocol`
   - Add `mergemate search` CLI command
   - Add `/search` Telegram command
   - Wire into bootstrap

3. **Phase C — Session resume** (depends on Phase A CLI commands existing)
   - Add `SessionService` and `SessionServiceProtocol`
   - Add `detect_resumable_run()` and resume prompt UI
   - Integrate resume dialog into `chat` command
   - Add `--resume` flag to `run` command
   - Wire into bootstrap

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| SQLite FTS5 may not be available on older Python/sqlite3 builds | FTS5 is built into Python's `sqlite3` module starting with SQLite 3.8.3 (Python 3.5+). Check via `pragma compile_options` and fall back to `LIKE` search with a warning. |
| Large FTS rebuild on existing databases | Backfill is incremental — only rebuilds missing rows. For millions of messages, add a batch size limit and run in steps. |
| CLI polling loop blocks the terminal | `CTRL+C` stops polling and exits cleanly. The run remains in the DB and can be resumed later. |
| `input()` in `chat` mode conflicts with asyncio event loop | Use `asyncio.to_thread(input)` or run the REPL in a separate thread to avoid blocking the background worker. |
| Session resume prompt is confusing | Keep the prompt minimal (numbered options 1-5). Show a `--help`-style hint on first resume. |

---

## 10. Appendix: `_resolve_session_chat_id` Shared Helper

```python
_CLI_USER_ID = 0  # Sentinel for CLI-originated runs

def _resolve_session_chat_id(session_name: str | None) -> int:
    """Return a deterministic chat_id for a named session, or a unique one for anonymous sessions.

    Same session name → same chat_id → same conversation history.
    """
    if session_name is None:
        return random.randrange(1, 2**31 - 1)  # Anonymous session
    digest = blake2s(f"cli:{session_name}".encode("utf-8"), digest_size=8).digest()
    return 1 + (int.from_bytes(digest, "big") % (2**31 - 2))
```