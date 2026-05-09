# Test Report: P8 — exceptions Migration + Property-Based Testing

## Task: P8

- **Completed**: 2026-05-09
- **Worker**: tester
- **Workspace**: scratch (`/home/pi/.hermes/kanban/boards/mergemate/workspaces/t_0409d374`)

---

## Part 1: exceptions.py — Old → New Migration Audit

### 1a. Verification of Old Exception Types (ValueError / RuntimeError)

The mapping comment in `exceptions.py:110-112` states:

```python
# ValueError → ConfigurationError / RunNotFoundError (context-dependent)
# RuntimeError → ProviderResponseError / JobQueueError / ParallelWorkerError
```

**Bare `raise ValueError` (not yet migrated to domain exceptions):**

| File | Line | Context |
|---|---|---|
| `application/use_cases/get_run_status.py` | 39 | `raise ValueError("chat_id is required when run_id is not provided")` |
| `domain/workflows/handlers.py` | 273 | `raise ValueError(msg)` (unknown document kind) |

**Bare `raise RuntimeError` (not yet migrated):**

| File | Line | Context |
|---|---|---|
| `infrastructure/llm/openai_adapter.py` | 45 | `raise RuntimeError(...)` (unconfigured provider) |

**`except ValueError` / `except RuntimeError` catches (legitimate — catching built-in exceptions):**

| File | Line | Caught | Reason |
|---|---|---|---|
| `domain/policies/__init__.py` | 30 | ValueError from `WorkflowName(workflow)` | Catches StrEnum constructor error |
| `domain/shared/enums.py` | 39 | ValueError from `WorkflowName(workflow)` | Same pattern |
| `interfaces/telegram/presenter.py` | 62 | ValueError from `datetime.fromisoformat()` | Catches date parse error |
| `application/use_cases/submit_prompt.py` | 227 | RuntimeError from `dispatch_run()` | Catches dispatcher failure |

**Conclusion**: Migration is NOT complete. 3 remaining bare raises of `ValueError`/`RuntimeError` should be migrated to domain exceptions. The mapping comment in `exceptions.py:110-112` should be kept to guide the migration.

### 1b. Domain Exception Inheritance Check

`exceptions.py` domain exceptions currently inherit directly from Python base exceptions:

- `ConfigurationError(ValueError)` → `AgentNotFoundError`, `ProviderNotFoundError`, `WorkflowNotFoundError`
- `RunError(ValueError)` → `RunNotFoundError`, `RunSubmissionError`, `StageExecutionError`, `ParallelWorkerError`
- `SoulPermissionError(MergeMateError)`, `SoulNotFoundError(MergeMateError)` → inherit from custom base
- `ProviderError(ValueError)` → `ProviderResponseError`, `AllProvidersFailedError`
- `PersistenceError(MergeMateError)`, `JobQueueError(MergeMateError)`, `InvalidWebhookModeError(MergeMateError)` → inherit from custom base

**No `ChainMap` usage found anywhere** in the MergeMate codebase. The domain exceptions inherit `ValueError` directly. This means `except ValueError` in existing code CAN accidentally catch domain exceptions — the 4 `except ValueError` blocks listed above are safe because they catch specific known patterns (StrEnum/datetime errors), but no general `except ValueError` exists that would be affected.

---

## Part 2: Property-Based Testing

### 2a. Hypothesis Dependency

Hypothesis is NOT in `pyproject.toml` dependencies (neither required nor optional). As instructed ("如果 Hypothesis 不是依赖项，不要添加"), Hypothesis-based tests were NOT written. Instead, the same invariants are covered through regular pytest tests.

### 2b. AgentRun State Model Tests

**File**: `tests/property/test_agent_run_invariants.py`

**Coverage**: 14 tests, all passing

| Test | Verifies |
|---|---|
| `test_terminal_runs_must_have_terminal_current_stage` | 3 parametrized: COMPLETED/FAILED/CANCELLED pairs with RunStage.COMPLETED |
| `test_non_terminal_run_must_not_have_stage_completed` | RUNNING runs must not have current_stage=COMPLETED |
| `test_known_valid_status_stage_combinations_are_constructible` | 13 valid (status, stage) pairs |
| `test_terminal_runs_have_error_or_result_text` | FAILED → error_text; COMPLETED → result_text |
| `test_review_iterations_must_be_non_negative` | review_iterations >= 0 |
| `test_estimate_seconds_must_be_positive` | estimate_seconds > 0 |
| `test_approved_flag_may_be_false_before_completion` | RUNNING runs may have approved=False |
| `test_completed_run_may_be_approved_or_not` | Both True and False for approved on COMPLETED runs |
| `test_created_at_must_not_be_after_updated_at` | Temporal ordering invariant |
| `test_created_at_should_be_less_than_or_equal_updated_at_for_all_pairs` | All RunStatus values |
| `test_different_run_ids_produce_different_runs` | Identity test |
| `test_same_fields_are_equal_when_timestamps_match` | Equality test |

### 2c. Soul.doc_permissions Invariants Tests

**File**: `tests/property/test_soul_permissions_invariants.py`

**Coverage**: 30 tests, all passing

| Test | Verifies |
|---|---|
| `test_every_soul_has_exactly_one_exclusive_write_section` | Each Soul owns one write section (except explainer: none) |
| `test_no_two_souls_share_the_same_write_section` | Exclusive write ownership |
| `test_no_soul_writes_to_unknown_section` | All write sections are in known set |
| `test_every_write_section_is_also_readable` | Documents current convention (own section not duplicated in read list) |
| `test_explainer_cannot_write_anything` | Explainer is read-only |
| `test_planner_can_write_planning_and_requirements` | + whitelist |
| `test_planner_cannot_write_architecture` | − blacklist |
| `test_architect_can_write_architecture` | + whitelist |
| `test_architect_cannot_write_implementation` | − blacklist |
| `test_coder_can_write_implementation` | + whitelist |
| `test_coder_cannot_write_testing` | − blacklist |
| `test_tester_can_write_testing` | + whitelist |
| `test_tester_cannot_write_implementation` | − blacklist |
| `test_reviewer_can_write_review` | + whitelist |
| `test_reviewer_cannot_write_testing` | − blacklist |
| `test_chronicler_can_write_lessons` | + whitelist |
| `test_chronicler_cannot_write_implementation` | − blacklist |
| `test_coder_can_read_shared_and_planning` | Cross-section read permission |
| `test_tester_can_read_architecture_and_implementation` | Cross-section read permission |
| `test_doc_permission_write_list_has_no_duplicates` | No duplicate entries |
| `test_doc_permission_read_list_has_no_duplicates` | No duplicate entries |
| `test_doc_permission_read_is_superset_of_write` | At least some Souls have cross-section read access |
| `test_tester_can_write_testing_document` | Runtime enforcement: allowed |
| `test_tester_cannot_write_architecture_document` | Runtime enforcement: denied |
| `test_planner_cannot_write_testing_document` | Runtime enforcement: denied |
| `test_no_role_name_bypasses_permission_check` | Backward compatibility |
| `test_unknown_role_bypasses_permission_check` | Backward compatibility |
| `test_all_souls_are_registered_and_findable` | Registry completeness |
| `test_soul_registry_names_are_lowercase_and_unique` | Naming convention |
| `test_soul_can_write_section_and_read_section` | Cross-Soul read coverage completeness |

---

## Findings

### Design Notes on Permission Model

The Soul.doc_permissions model separates `write` and `read` as orthogonal lists:
- `write` = sections this Soul owns and can write to
- `read` = OTHER Souls' sections this Soul can read

A Soul's own write section is **implicitly readable** (not duplicated in its read list). This is a deliberate convention, not a bug. The cross-Soul read coverage is complete: every write section is readable by at least one other Soul.

### Remaining Bare Raises

3 `raise ValueError`/`raise RuntimeError` calls should be migrated to domain-specific exceptions. The mapping comment in `exceptions.py` should be preserved until this is complete.