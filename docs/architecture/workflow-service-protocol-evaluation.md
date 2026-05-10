# Architecture Evaluation: WorkflowService Protocol

## Source

Review finding C in `.hermes/reviews/comprehensive-review-2026-05-10.md`

> `WorkflowService` depends on `LLMGateway` + `AppConfig` — no explicit interface.
> Extract an `IWorkflowService` Protocol **if** the service grows more public methods.

## 1. Assessment: Is a Protocol Warranted Now?

**Verdict: Yes — but not in isolation.**

### Why now, not later

| Factor | Assessment |
|--------|-----------|
| Public methods on `WorkflowService` | **8** — `build_execution_plan`, `create_design`, `generate_code`, `execute_direct`, `generate_tests`, `review`, `record_lesson`, `has_high_concerns` |
| Callers across layers | `orchestrator.py` (1 call), `execution_plan.py` (2 calls via `runtime.deps`), `handlers.py` (7 calls via `runtime.deps`) |
| Already typed as `Any` in `OrchestratorDependencies` | Yes — line 79 of `execution_plan.py`: `workflow_service: Any` |
| Existing test stub pattern | Tests define ad-hoc stubs (`SettingsStub`, `GatewayStub`) per test file — a Protocol would codify the contract and make stubs type-safe |
| Downstream consumers | `MultiStageExecutionPlan.execute()`, `_handle_design`, `_handle_implementation`, `_handle_testing`, `_handle_review`, `_handle_chronicle`, `_handle_direct`, `AgentOrchestrator.process_run()` — all access `workflow_service` through the `Any`-typed `deps` container |

The service is mature and stable — the original review condition ("if it grows more public methods") has been met. There are 8 public methods and 7 unique call sites.

### The key nuance: don't do this in isolation

A **separate design doc** (`docs/architecture/service-protocols.md`) already exists that defines an `IWorkflowService` Protocol as part of a *systematic* effort to replace all `Any` types in `OrchestratorDependencies` with domain Protocols. That doc covers:

- `ContextServiceProtocol`
- `DocumentationServiceProtocol`
- `LearningServiceProtocol`
- `PlanningServiceProtocol`
- `PromptServiceProtocol`
- `ToolServiceProtocol`
- `WorkflowServiceProtocol`
- `LLMGatewayProtocol`

Implementing *only* the `WorkflowServiceProtocol` as a one-off would leave 7 other services still typed as `Any`, and the `OrchestratorDependencies` container would remain partially typed — losing most of the value (type-checked wiring). It would also create inconsistency: some deps typed to Protocols, others still `Any`.

## 2. Recommendation

Add `WorkflowServiceProtocol` as part of the **broader service-protocols effort** already designed in `docs/architecture/service-protocols.md`. Do not implement it standalone.

### Protocol interface

Below is the `WorkflowServiceProtocol` as already specified in the service-protocols design doc — reproduced here for reference and so the implementor has it in one place:

```python
# Place in: src/mergemate/application/protocols.py

class WorkflowServiceProtocol(Protocol):
    """Protocol for WorkflowService — satisfied by the concrete class via structural subtyping."""

    def build_execution_plan(
        self,
        workflow: str,
        *,
        agent_name: str,
    ) -> DirectExecutionPlan | MultiStageExecutionPlan:
        ...

    async def create_design(self, plan_text: str, context_text: str) -> str:
        ...

    async def generate_code(
        self,
        plan_text: str,
        design_text: str,
        context_text: str,
        *,
        agent_name: str | None = None,
    ) -> str:
        ...

    async def execute_direct(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        ...

    async def generate_tests(self, plan_text: str, design_text: str, implementation_text: str) -> str:
        ...

    async def review(self, plan_text: str, design_text: str, implementation_text: str, test_text: str) -> str:
        ...

    async def record_lesson(
        self,
        *,
        plan_text: str = "",
        design_text: str = "",
        implementation_text: str = "",
        test_text: str = "",
        review_text: str = "",
        result_text: str = "",
        error_text: str = "",
        agent_name: str = "",
    ) -> str:
        ...

    @staticmethod
    def has_high_concerns(review_text: str) -> bool:
        ...
```

## 3. Files to Change

| File | Change |
|------|--------|
| `src/mergemate/application/protocols.py` | **CREATE** — include `WorkflowServiceProtocol` alongside other service protocols |
| `src/mergemate/application/execution_plan.py` | Change `workflow_service: Any` → `WorkflowServiceProtocol` in `OrchestratorDependencies` |
| `src/mergemate/domain/workflows/handlers.py` | Import `WorkflowServiceProtocol` if needed for type annotations on `runtime.deps.workflow_service` |
| No changes to `workflow_service.py` | Structural subtyping — the concrete class already satisfies the Protocol |
| No changes to `bootstrap.py` | Wiring is unchanged: `WorkflowService(llm_gateway, settings)` is still correct |

## 4. Impact on Tests

### Positive impact (gains, not cost)

- **`GatewayStub` stays as-is** — it satisfies `LLMClient` Protocol already used elsewhere in the codebase (via `src/mergemate/infrastructure/llm/base.py`)
- **`SettingsStub` stays as-is** — `settings` is typed as `Any` (by design, as per the service-protocols doc)
- No test file needs modification — the Protocol is structurally satisfied by the existing `WorkflowService`, so no concrete class change is needed
- **New tests** would benefit from being able to type-check stubs against `WorkflowServiceProtocol` — a linter violation when a stub misses a method is caught at review time, not at runtime

### What doesn't change

- `test_workflow_service.py` — all 19 tests continue to pass unchanged, including parallel execution tests, `has_high_concerns` tests, and execution plan tests
- Integration tests — no behavioural change

## 5. Implementation Sequence

This task (finding C) should be grouped with the other `OrchestratorDependencies` `Any`→Protocol replacements (findings from the same review or a follow-up). The recommended implementation order within that batch:

1. Define all Protocols in `src/mergemate/application/protocols.py`
2. Update `OrchestratorDependencies` field types all at once
3. Run `mypy src/mergemate/application/ --strict` to verify structural subtyping
4. Run `pytest tests/` to confirm no behavioural change

This avoids intermediate states where some fields are typed and others are `Any`.

## 6. Files That Won't Change (explicitly listed)

- `src/mergemate/application/services/workflow_service.py` — no behavioural change
- `src/mergemate/bootstrap.py` — wiring unchanged
- `tests/unit/mergemate/application/services/test_workflow_service.py` — all 402 lines unchanged
- `src/mergemate/domain/workflows/handlers.py` — handler function signatures reference `OrchestratorDependencies` transitively; no direct import needed

---

*Architecture design by Architect role. Implemented as part of the broader service-protocols task group.*