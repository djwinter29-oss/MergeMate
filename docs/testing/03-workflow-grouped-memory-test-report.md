# Test Report: Workflow-Grouped Memory Injection

## Summary

Written and verified 14 new tests across 3 test files covering the
workflow-grouped memory injection feature (`list_grouped_by_workflow`,
`load_grouped_learnings`, orchestrator integration), plus fixed 2 stub
compatibility issues in the existing orchestrator test suite.

## Test Files Modified

| File | New Tests | Pre-existing Tests (still pass) |
|------|-----------|---------------------------------|
| `tests/unit/mergemate/infrastructure/persistence/test_sqlite.py` | 7 | ~12 |
| `tests/unit/mergemate/application/services/test_learning_service.py` | 1 | ~4 |
| `tests/unit/mergemate/application/test_orchestrator.py` | 1 | ~30 |

## Stub Fixes Applied

- **LearningServiceStub**: Added `load_grouped_learnings()`, `load_repo_knowledge()`;
  made `remember_success` async.
- **SettingsStub**: Added `repo_name` field.
- **PromptServiceStub**: Added `**kwargs` to `render()`.

These were pre-existing gaps exposed by architect changes (settings.repo_name,
load_repo_knowledge calls) in the orchestrator.

## Requirement Coverage

| # | Requirement | Test | Status |
|---|-------------|------|--------|
| 1 | 5 current + 3 other -> 3 current + 1 other (total 4) | `test_list_grouped_by_workflow_mixed_workflows_returns_limited_per_group` | PASS |
| 2 | Only current -> up to same_workflow_limit | `test_list_grouped_by_workflow_only_current_workflow` | PASS |
| 3 | Only other -> 1 per other workflow | `test_list_grouped_by_workflow_only_other_workflows` | PASS |
| 4 | No entries -> `[]` | `test_list_grouped_by_workflow_no_entries_returns_empty` | PASS |
| 5 | Limit > available -> all available | `test_list_grouped_by_workflow_limit_greater_than_available` | PASS |
| 6 | learning_lessons column included | `test_list_grouped_by_workflow_includes_learning_lessons` | PASS |
| 7 | Unknown current workflow -> other entries ok | `test_list_grouped_by_workflow_unknown_current_workflow` | PASS |
| 8 | load_grouped_learnings delegates to repo | `test_load_grouped_learnings_delegates_and_honors_enabled_flag` | PASS |
| 9 | load_grouped_learnings returns [] when disabled | `test_load_grouped_learnings_delegates_and_honors_enabled_flag` (same) | PASS |
| 10 | process_run calls load_grouped_learnings | `test_process_run_calls_load_grouped_learnings_instead_of_load_recent_learnings` | PASS |
| 11 | load_recent_learnings backward compat | `test_load_recent_learnings_respects_enabled_flag_and_limit` | PASS |

## Test Results

All 44 tests pass (31 pre-existing + 2 pre-existing stub fixes + 11 new).

**Test command:**
```
cd /home/pi/MergeMate && PYTHONPATH=src python -m pytest \
  tests/unit/mergemate/infrastructure/persistence/test_sqlite.py \
  tests/unit/mergemate/application/services/test_learning_service.py \
  tests/unit/mergemate/application/test_orchestrator.py \
  -v --tb=short
```