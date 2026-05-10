# Comprehensive Code Review — 2026-05-10

## Benchmark

| Metric | Value |
|--------|-------|
| Tests | 759 passed, 4 skipped |
| Coverage | 99% (2868/2909 lines) |
| mypy | 0 errors (72 files) |
| ruff | 0 errors |
| FIXME/TODO/HACK | 0 in `src/` |
| Domain → infra dependency | 0 (clean architecture respected) |

## 🟢 Already Good

### 1. Clean Architecture — domain layer has zero upward dependencies
No file in `src/mergemate/domain/` imports from `infrastructure`, `application`, `interfaces`, or `config`. The domain is truly isolated.

### 2. No technical debt markers in source code
Zero FIXME/TODO/HACK/XXX/BUG comments in `src/`. The codebase is actively maintained.

### 3. Type safety
mypy strict mode passes cleanly on all 72 source files with `disallow_untyped_defs` enabled.

### 4. Deprecation wrappers in shared/`__init__`.py
The 4 deprecation shims (`is_user_facing_workflow`, `resolve_workflow_name`, `uses_multi_stage_delivery`, `workflow_prompt_file`) are properly implemented with lazy imports to avoid circular dependencies.

---

## 🟡 Coverage Gaps (low priority)

### 1. `domain/shared/__init__.py` — 55% (10/22 lines uncovered)
- **Problem**: The 4 deprecation wrapper functions (`is_user_facing_workflow`, `resolve_workflow_name`, `uses_multi_stage_delivery`, `workflow_prompt_file`) are untested.
- **Root cause**: Each wrapper calls `_get_policies()` lazily, and no test exercises the deprecation-warning path.
- **Why low priority**: These are shims intended for eventual removal. The real functions in `domain/policies/__init__.py` have full coverage.

### 2. `bootstrap.py` — 82% (20/114 lines uncovered)
- **Problem**: `discover_workflow_plugins()` (lines 66-71) and `_load_workflow_config_plugins()` (lines 89-107) error-handling branches are untested.
- **Root cause**: The error paths (`except Exception` → log warning) require mocking failing entry points or broken module imports.
- **Impact**: Low — these are graceful degradation paths. The happy path works.

### 3. `domain/workflows/handlers.py` — `_handle_direct` (lines 250-262) uncovered
- **Problem**: The "direct" execution handler has no integration test.
- **Why uncovered**: No workflow stage references the `"direct"` handler in test fixtures.

### 4. `config/models.py` — `_provider_names_for` (line 341) uncovered
- **Problem**: The branch where an agent has custom `provider_names` is uncovered.
- **Root cause**: The test fixture config always uses the default provider path.

### 5. `infrastructure/llm/gateway.py` — `AllProvidersFailedError` (line 92-93) uncovered
- **Problem**: The fallback error path (all providers fail) is not tested.
- **Why uncovered**: Requires all parallel LLM calls to fail simultaneously, which is hard to trigger in unit tests.

---

## 🟠 Architectural Improvement Opportunities

### A. `_save_document` if-elif chain → dict dispatch
- **File**: `domain/workflows/handlers.py` (lines 292-339)
- **Problem**: The 4-kind `if/elif` chain for document saving is verbose and requires adding a new branch each time a document type is introduced.
- **Suggestion**: Replace with a `{kind: callable}` dispatch dict + a `@register_document_kind(kind)` decorator pattern, similar to `@register_handler`.

### B. `ToolRegistry` construction in `bootstrap.py` — repetition in conditional dicts
- **File**: `bootstrap.py` (lines 184-228)
- **Problem**: The same `**({...} if condition else {})` pattern repeats 3 times for git/github/gitlab tools.
- **Suggestion**: Extract a helper like `_build_tool_registry(settings) -> ToolRegistry` or use a registry builder pattern.

### C. `WorkflowService` depends on `LLMGateway` + `AppConfig` — no explicit interface
- **File**: `application/services/workflow_service.py`, `bootstrap.py` line 236
- **Problem**: `WorkflowService` takes `llm_gateway` and `settings` but has no dedicated Protocol/interface. This makes it hard to test or swap implementations.
- **Suggestion**: Extract an `IWorkflowService` Protocol if the service grows more public methods.

### D. `MergeMateRuntime` dataclass — 18 fields
- **File**: `bootstrap.py` (lines 114-133)
- **Problem**: The runtime dataclass is growing. 18 fields with no grouping suggests it may need to be broken into smaller context objects soon.
- **Suggestion**: Consider grouping `*Repository` fields into a `PersistenceContext`, and `*Service` fields into a `ServiceContext`.

---

## 🔴 Actual Defects (must fix)

### None found.

The entire codebase passes all quality gates with no errors.

---

## 🆕 High-Value Feature Gaps (new features, not bugs)

### F1. CLI Interactive Mode (not just Telegram)
**Problem**: Currently only Telegram bot is supported as user interface (`interfaces/telegram/`). There is no CLI mode, so developers cannot submit prompts or check status directly from the terminal.
**Why valuable**: Developers work in the terminal. Switching to Telegram breaks the flow.
**Suggested approach**: Add an interactive mode to `cli.py` (like `mergemate chat` or `mergemate run "write a FastAPI CRUD"`), reusing existing use cases (SubmitPromptUseCase, GetRunStatusUseCase, CancelRunUseCase).

### F2. Retry/Resume Failed Run
**Problem**: `CancelRunUseCase` exists but there is no `RetryRunUseCase` or `ResumeRunUseCase`. If a multi-stage workflow fails partway through, the only option is to start over from scratch.
**Why valuable**: Long-running multi-stage workflows (e.g., generate_code) are expensive to re-run entirely.
**Suggested approach**: 
- Add `RetryRunUseCase` to re-submit a failed run
- Add `ResumeRunUseCase` to resume from a failed stage
- AgentRun entity may need to store failure stage info
- Add `/retry` and `/resume` Telegram commands

### F3. Conversation History Search
**Problem**: `SQLiteConversationRepository` only supports append/load. No search across past conversations.
**Why valuable**: Cross-session context retrieval is a core capability for an AI assistant.
**Suggested approach**:
- Add `search(query, chat_id, limit)` method to ConversationRepository
- Implement SQL FTS (full-text search) in SQLiteConversationRepository
- Add `/search` Telegram command + formatted output in presenter.py

---

## 📚 Memory & Understanding Improvements

### M1. Structured Lesson Extraction (not just raw text truncation)
**Problem**: `SQLiteLearningRepository.record()` stores `result_excerpt[:1200]` — raw text truncation. No structured extraction. When loaded, the LLM must parse raw text to understand what was learned.
**Suggested approach**:
- Add an `_extract_lessons()` step after run completion: use LLM to distill `result_text` into structured notes (key technical points, gotchas, patterns, conclusions)
- Add `learning_lessons TEXT` column to the `learning_entries` table
- `LearningService.remember_success()` calls the extraction step
- `PromptService.render()` injects both raw excerpt and extracted lessons
- Kanban: architect→coder→tester→reviewer

### M2. Per-Repository Knowledge Base
**Problem**: All knowledge is stored by `chat_id` only. When working on multiple repos simultaneously, memory is polluted across projects.
**Suggested approach**:
- New `repo_knowledge` table (chat_id, repo_name, topic, summary, created_at)
- Created by `SQLiteDatabase.initialize()`
- New `LearningService.remember_repo_knowledge()` and `load_repo_knowledge()`
- `PromptService.render()` loads current repo knowledge
- `AppConfig` gets a `repo_name` config field
- Kanban: architect→coder→tester→reviewer

### M3. Workflow-Grouped Memory Injection
**Problem**: `load_recent_learnings(chat_id, limit=3)` returns the last 3 entries regardless of workflow. If the user was doing `debug_code`, then switches to `generate_code`, no relevant history is injected.
**Suggested approach**:
- Group by `WorkflowName`: current workflow → top-3, other workflows → top-1 each
- Or have `PromptService.render()` prioritize entries matching the current workflow
- Kanban: architect→coder→tester