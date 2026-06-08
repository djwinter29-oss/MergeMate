# Changelog

## Unreleased

### Changed

- **Documentation refresh** — clarified that repository-scoped knowledge is keyed by `repo_name`, that submitted runs persist the repository scope in effect at submission time, and that later lookups prefer the run's own repository context.

- **Run repo scope consistency** — `AgentRun` now stores the `repo_name`
  that was in effect when the run was submitted. The SQLite run repository
  persists it, and orchestration prefers the run's own repository scope when
  loading repo knowledge. This keeps repo-scoped memory aligned with the
  submitted run even if the config changes later. Existing runs without a
  `repo_name` fall back to the current config value (backward compatible).

### Added

- **FTS5-backed search** — both `search-runs` and `search-conversations` (and
  the unified `search` command) now use SQLite FTS5 virtual tables with phrase-aware
  MATCH queries. Quoted multi-word phrases (e.g. `"CI/CD pipeline"`) work as shell-style
  tokens.  Triggers keep the FTS indexes in sync with the data tables automatically.
  Falls back to LIKE-based search if FTS5 is unavailable or returns an error.

### Changed

- **Bootstrap repo knowledge import fix** — `bootstrap()` now imports
  `SQLiteRepoKnowledgeRepository` at runtime instead of leaving the symbol as
  `None` outside type-checking context. This restores the real bootstrap path
  for repo-scoped learning and removes a hidden production failure mode.

- **Run repo scope consistency** — `AgentRun` now stores the `repo_name`
  that was in effect when the run was submitted. The SQLite run repository
  persists it, and orchestration prefers the run's own repository scope when
  loading repo knowledge. This keeps repo-scoped memory aligned with the
  submitted run even if the config changes later. Existing runs without a
  `repo_name` fall back to the current config value (backward compatible).

### Added

- **`mergemate run`** — one-shot prompt execution command. Submits a prompt
  via `SubmitPromptUseCase`, polls for completion via `GetRunStatusUseCase`,
  and prints the result. Supports `--agent`, `--workflow`, `--session`,
  `--quiet`, `--timeout`, and `--poll-interval` options. Exit codes: 0 =
  success, 1 = timeout, 2 = runtime error.

- **`mergemate chat`** — interactive REPL session. Creates or resumes a named
  session via SQLite conversation storage. Shows history on resume, loops for
  multi-turn prompts. Supports `--session`, `--agent`, `--workflow`, and
  `--poll-interval` options.

- **Session persistence** — named sessions (`--session NAME`) derive a
  deterministic `chat_id` from the session name, enabling persistent
  conversation history across CLI restarts via the existing
  `SQLiteConversationRepository`.

- `docs/implementation/cli-interactive-mode.md` - implementation notes.

- **Makefile enhancement** — added `typecheck`, `install-dev`, `test-all`,
  `coverage`, and `clean` targets. Renamed `install` to use production-only
  dependencies. Separated `install-dev` for dev extras.

- `.gitignore` added `.ruff_cache/` entry.

- **Housekeeping** — removed 26 stale local branches that were fully merged
  into main. Pruned 9 stale remote tracking branches. Deleted 3 merged remote
  branches from origin. Removed 2 orphaned worktree directories, freeing ~20 MB
  of disk space.

- **`@register_document_kind` decorator** — refactored `_save_document()` from
  if/elif chain to decorator-based dispatch via `_DOCUMENT_KINDS` registry in
  `src/mergemate/domain/workflows/handlers.py`. Added 4 extracted saver
  functions, `_save_to_artifacts()` helper, and duplicate-registration warning.
  No behavioral change — 21 existing integration tests pass.

### Changed

- **Docs refresh** — updated the `docs/architecture/feature-gaps-cli-resume-search.md`
  architecture note to reflect the shipped `search-runs` and `search-conversations`
  CLI commands and to narrow the remaining search gap to unified/FTS-backed search.

- **MergeMateRuntime field grouping** — refactored from flat 18-field
  `@dataclass(slots=True)` to 6 fields with `PersistenceContext` (6 repository
  fields) and `ServiceContext` (8 service/use-case fields) sub-contexts. Added
  14 backward-compatible property shims. Updated all callers across `cli.py`,
  `interfaces/telegram/handlers.py`, and `interfaces/telegram/progress_notifier.py`
  to use `runtime.services.*`. Updated test stubs in 4 test files. 784 tests pass.