# Test Plan: Additional Branch Coverage for MergeMate

## Overview

This document describes the additional test coverage added for uncovered branch paths across the MergeMate codebase.

## Coverage Target

**File:** `tests/unit/mergemate/test_additional_branch_coverage.py`
**Tests:** 19 tests covering previously uncovered branch paths in 9 modules.

## Test Breakdown

### 1. `application/jobs/dispatcher.py` — Job Queue Error
- **`test_dispatcher_raises_when_queue_repository_returns_no_job`**: Covers the path where `ensure_queued_job` returns a decision with `job=None`, triggering a `JobQueueError` (line 31).

### 2. `application/orchestrator.py` — Early Returns
- **`test_orchestrator_returns_early_for_non_queued_run`**: Covers the path where a run is already `RUNNING` (line 40 — status is in skip-process statuses).
- **`test_orchestrator_returns_run_when_transition_does_not_happen`**: Covers the path where `try_update_status` returns `transitioned=False` (line 51 — run stays as-is).

### 3. `application/services/tool_service.py` — Edge Cases
- **`test_tool_service_skips_resume_transition_when_current_run_is_not_waiting_tool`**: Covers the exit path when `entering=False` and current run status is not `WAITING_TOOL` (line 70).
- **`test_tool_service_skips_repository_context_metadata_for_other_platforms`**: Covers the platform filter in `_iter_repository_context_metadata` (line 95 — platform mismatch).

### 4. `application/services/workflow_service.py` — Record Lesson
- **`test_workflow_service_record_lesson_includes_error_section`**: Covers the `error_text` branch in `record_lesson` (line 180).

### 5. `application/use_cases/cancel_run.py` — Null Repository Update
- **`test_cancel_run_returns_none_when_repository_update_clears_run`**: Covers the path where `try_update_status` returns `run=None` (line 45).

### 6. `application/use_cases/submit_prompt.py` — Edge Cases
- **`test_submit_prompt_complete_planning_returns_none_when_run_missing`**: Covers the missing run path in `complete_planning` (line 107).
- **`test_submit_prompt_complete_planning_raises_when_approval_missing_before_dispatch`**: Covers the path where `approve` returns `run=None` before dispatch (line 131).
- **`test_submit_prompt_approve_returns_non_transitioned_result_when_approval_does_not_transition`**: Covers the path where approval does not transition the run (line 207).

### 7. `cli.py` — Readiness Probe Error Handling
- **`test_cli_probe_readiness_handles_invalid_json_http_error`**: Covers the JSON decode error path in `_probe_readiness_once` (line 45).

### 8. `config/loader.py` — Config Discovery Fallback
- **`test_loader_falls_back_to_cwd_when_no_pyproject_is_found`**: Covers the fallback path in `_discover_default_local_config_path` when no `pyproject.toml` is found (line 19).

### 9. `config/models.py` — Role-Based Resolution
- **`test_config_model_resolves_roles_and_agent_fallbacks`**: Covers `resolve_agent_provider_names` with role config (line 335), and `resolve_agent_name_for_workflow` with `preferred_agent_name` matching and mismatching (lines 353-355).

### 10. `interfaces/telegram/bot.py` — Runtime Lifecycle
- **`test_bot_stop_runtime_tasks_marks_readiness_state_and_stops_worker`**: Covers `stop_runtime_tasks` with readiness state and worker (lines 29-37).
- **`test_bot_build_application_stores_readiness_state`**: Covers `build_application` with a provided readiness state (line 59).

### 11. `interfaces/telegram/health.py` — Server Lifecycle
- **`test_health_server_start_is_idempotent_and_stop_is_safe_when_not_started`**: Covers double-start guard (line 54) and stop-without-start (lines 67-73).

### 12. `interfaces/telegram/progress_notifier.py` — Terminal Updates
- **`test_progress_notifier_formats_cancelled_and_failed_terminal_updates`**: Covers `_format_terminal_update` with `CANCELLED` and `FAILED` statuses (lines 15-19).

### 13. `interfaces/telegram/handlers.py` — Confirmation Delivery
- **`test_handlers_send_confirmation_when_plan_text_is_present`**: Covers the path where `plan_text` is present and the confirmation is sent (line 254).

### 14. `infrastructure/persistence/sqlite.py` — Integrity Error
- **`test_sqlite_ensure_queued_job_raises_when_integrity_error_has_no_active_job`**: Covers the re-raise path when `IntegrityError` is caught but `get_active_for_run` returns `None` (line 475).

## Running the Tests

```bash
cd /home/pi/MergeMate
PYTHONPATH=src python -m pytest tests/unit/mergemate/test_additional_branch_coverage.py -v
```

All 19 tests should pass. The file is standalone and does not interfere with existing tests.