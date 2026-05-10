# StageDescriptor Culling Plan

> Status: Design proposal
> Author: Architect
> Date: 2026-05-10
> Related: Deep Review Finding P2.4

## 1. Problem Statement

`StageDescriptor` is a frozen dataclass in `src/mergemate/application/execution_plan.py` (line 66) that was the original mechanism for describing workflow stages. It was superseded by `WorkflowStage` (in `src/mergemate/domain/workflows/stage.py`) when the workflow plugin system was introduced, and now exists solely as a backward-compatibility shim.

The class has an explicit docstring stating its legacy status:

> Legacy stage descriptor used by DirectExecutionPlan. MultiStageExecutionPlan now derives its stage data from WorkflowStage objects. This type is kept for backward compatibility only.

This docstring was written anticipating removal. This design documents the full audit and specifies the exact culling approach.

## 2. Usage Audit

### 2.1 Definition

```python
@dataclass(slots=True, frozen=True)
class StageDescriptor:
    name: str
    current_stage: str | RunStage
    uses_tool_context: bool = False
    checks_cancellation_before: bool = False
    checks_cancellation_after: bool = False
```

Fields: `name`, `current_stage`, `uses_tool_context`, `checks_cancellation_before`, `checks_cancellation_after`.

### 2.2 All References

| # | File | Line(s) | Role | Status |
|---|------|---------|------|--------|
| 1 | `src/.../execution_plan.py` | 66-78 | Class definition | DEAD — remove |
| 2 | `src/.../execution_plan.py` | 116-118 | `BaseExecutionPlan.stages` return type annotation | DEAD — remove |
| 3 | `src/.../execution_plan.py` | 129-136 | `DirectExecutionPlan.stages` constructs `StageDescriptor` | DEAD — inline `requires_tool_context` |
| 4 | `src/.../execution_plan.py` | 159 | `DirectExecutionPlan.execute` reads `self.stages[0].current_stage` | ACTIVE — but can use a constant |
| 5 | `src/.../execution_plan.py` | 207-219 | `MultiStageExecutionPlan.stages` converts `WorkflowStage` → `StageDescriptor` | DEAD — remove |
| 6 | `src/.../execution_plan.py` | 122 | `BaseExecutionPlan.requires_tool_context` iterates `self.stages` | ACTIVE — inline |
| 7 | `test_execution_plan_uncovered.py` | 35 | Import | DEAD — remove |
| 8 | `test_execution_plan_uncovered.py` | 192-201 | `test_stages_returns_descriptors_when_workflow_def_provided` | DEAD — remove test |

### 2.3 Downstream Consumers of `.stages` and `.requires_tool_context`

| Caller | File | What it uses | Impact of removal |
|--------|------|-------------|-------------------|
| `AgentOrchestrator.process_run` | `orchestrator.py:69` | `execution_plan.requires_tool_context` (bool property) | None — property stays, just its implementation changes |
| `DirectExecutionPlan.execute` | `execution_plan.py:159` | `self.stages[0].current_stage` | Needs replacement with a constant |
| `WorkflowService.build_execution_plan` | `workflow_service.py:19-27` | Returns `DirectExecutionPlan` or `MultiStageExecutionPlan` | No signature change — consumers get the same plan types |
| `BaseExecutionPlan` subclasses | any | Call `.stages` to build `StageDescriptor` tuples | `.stages` property removed; callers use plan-specific API |

## 3. Dependency Tree

```
BaseExecutionPlan.stages (return type)
  ├── DirectExecutionPlan.stages     → constructs StageDescriptor
  │     └── DirectExecutionPlan.execute → reads self.stages[0].current_stage
  ├── MultiStageExecutionPlan.stages  → converts WorkflowStage → StageDescriptor
  └── BaseExecutionPlan.requires_tool_context → iterates self.stages
        └── AgentOrchestrator.process_run → calls .requires_tool_context
```

## 4. Replacement Analysis

Each consumer of `StageDescriptor` can be replaced with direct, type-safe alternatives:

### 4.1 `BaseExecutionPlan.stages` → Remove

The abstract `stages` property on `BaseExecutionPlan` exists solely to provide `StageDescriptor` tuples. It is consumed by:

1. **`requires_tool_context`** — can be replaced with a concrete property on each subclass.
2. **`DirectExecutionPlan.execute`** — uses `self.stages[0].current_stage` for the `current_stage` parameter when saving artifacts. This can be replaced with a class-level constant.

### 4.2 `requires_tool_context` — Keep the interface, change the implementation

`AgentOrchestrator.process_run` (line 69) calls `execution_plan.requires_tool_context`. This boolean property is the only consumer of `.stages` outside the execution plan hierarchy itself.

Replace the current implementation:
```python
# Current (iterates StageDescriptor tuple)
@property
def requires_tool_context(self) -> bool:
    return any(stage.uses_tool_context for stage in self.stages)
```

With:
```python
# New — each subclass declares its own constant
@property
def requires_tool_context(self) -> bool:
    return False  # Base default, overridden as needed

# DirectExecutionPlan → True (hardcoded, it always uses tool context)
# MultiStageExecutionPlan → derived from WorkflowStage instances
```

### 4.3 `DirectExecutionPlan.stages` — Remove, inline the constant

`DirectExecutionPlan.execute` (line 159):
```python
runtime.deps.run_repository.save_artifacts(
    run.run_id,
    current_stage=self.stages[0].current_stage,
    ...
)
```

Replace with:
```python
current_stage=RunStage.EXECUTION,
```

This is already the value the StageDescriptor supplies. No behavioral change.

### 4.4 `MultiStageExecutionPlan.stages` — Remove

`MultiStageExecutionPlan.execute` already uses `WorkflowStage` directly via `_get_workflow_stages()` (line 222-232). The `.stages` property (lines 207-219) is an unused backward-compatibility conversion that no code path calls.

**Verified by usage search:** No code outside `execution_plan.py` calls `.stages` on any plan instance. The only cross-file consumer is `requires_tool_context`.

## 5. Culling Plan

### Phase 1: Remove `StageDescriptor` class and all `.stages` properties

**File: `src/mergemate/application/execution_plan.py`**

1. Delete `StageDescriptor` dataclass (lines 65-78)
2. Delete `BaseExecutionPlan.stages` property (lines 115-118)
3. Delete `DirectExecutionPlan.stages` property (lines 128-136)
4. Delete `MultiStageExecutionPlan.stages` property (lines 206-220)
5. Replace `requires_tool_context` implementation:
   - Move to each subclass as an override
   - `BaseExecutionPlan`: returns `False`
   - `DirectExecutionPlan`: returns `True` (hardcoded)
   - `MultiStageExecutionPlan`: iterate `self._workflow_definition.stages` checking `uses_tool_context` on each `WorkflowStage`
6. In `DirectExecutionPlan.execute`, replace `self.stages[0].current_stage` with `RunStage.EXECUTION`

**File: `tests/unit/mergemate/application/test_execution_plan_uncovered.py`**

1. Remove `StageDescriptor` from import line (line 35)
2. Delete `test_stages_returns_descriptors_when_workflow_def_provided` method (lines 192-201) — this tests the legacy `.stages` conversion
3. Delete `test_stages_returns_empty_when_no_workflow_def` method (lines 187-190) — tests removed `BaseExecutionPlan.stages`

### Phase 2: Verify no imports break

Confirm that:
- `from mergemate.application.execution_plan import StageDescriptor` does not exist anywhere else
- No module checks `isinstance(x, StageDescriptor)`
- No serialization or pickle relies on `StageDescriptor`

These have all been confirmed in the audit above. No further changes needed.

### Phase 3: Run tests

- All existing tests must pass unchanged except the two deleted test methods
- Coverage must not decrease (those tests were for uncovered-line coverage, not behavioral coverage)

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Plugin/third-party code imports StageDescriptor | Low | Low (compile error, not runtime) | Search codebase confirmed no external imports |
| `save_artifacts(current_stage=...)` misalignment | Low | Low | `RunStage.EXECUTION` is identical to the old StageDescriptor value |
| `MultiStageExecutionPlan.requires_tool_context` divergence | Low | Low | `WorkflowStage.uses_tool_context` is the same semantic field — the conversion was 1:1 |
| Coverage regression | Low | Low | The two deleted tests only tested dead code paths; other tests cover the actual behavior |

## 7. Migration Steps for Coder

### Order of changes

1. **Edit `execution_plan.py`** — all source changes together:
   - Delete `StageDescriptor` dataclass
   - Delete `BaseExecutionPlan.stages` property
   - Add `requires_tool_context` as non-abstract property returning `False` on `BaseExecutionPlan`
   - On `DirectExecutionPlan`:
     - Override `requires_tool_context` → `True`
     - In `execute()`, replace `self.stages[0].current_stage` → `RunStage.EXECUTION`
   - On `MultiStageExecutionPlan`:
     - Override `requires_tool_context` → iterate `self._workflow_definition.stages`

2. **Edit `test_execution_plan_uncovered.py`**:
   - Remove `StageDescriptor` from import
   - Delete `TestMultiStageExecutionPlanStages` class (lines 186-206) — both test methods within it test removed properties

3. **Run `pytest tests/unit/mergemate/application/`** — verify all pass
4. **Run `pytest tests/integration/mergemate/application/`** — verify integration tests pass

### Post-removal state

After culling, the execution plan hierarchy will be:

```
BaseExecutionPlan
  ├── DirectExecutionPlan
  │     └── requires_tool_context → True (hardcoded)
  └── MultiStageExecutionPlan
        └── requires_tool_context → derived from WorkflowStage list
```

`StageDescriptor` type, all `.stages` properties, and the backward-compat conversion code will be gone. The `WorkflowStage` type in `domain/workflows/stage.py` (which has the richer field set including `handler`, `prompt_template`, `validation_hook_key`, and `produces`) becomes the single canonical stage descriptor.