# Architecture Design: Replace `Any` Types with Service Protocols

## Problem

`OrchestratorDependencies` and `ExecutionRuntime` in
`src/mergemate/application/execution_plan.py` annotate all service fields with
`Any`, defeating static type checking and obscuring the contractual dependency
of the orchestration layer on each service.

## Solution

Define a `Protocol` class for each service interface in a new file
`src/mergemate/application/protocols.py`.  Wire the Protocols into the
dataclass field annotations and into `DirectExecutionPlan.execute()` and
`MultiStageExecutionPlan.execute()` method signatures.

No concrete service class (`ContextService`, `DocumentationService`, etc.)
needs to change — Python's structural subtyping means they already satisfy
their respective Protocols as long as their method signatures match.

## Location

| Artifact | Path |
|---|---|
| **Protocol definitions (NEW)** | `src/mergemate/application/protocols.py` |
| **Updated dependency containers** | `src/mergemate/application/execution_plan.py` |
| **Updated handler signatures** | `src/mergemate/domain/workflows/handlers.py` |

## Protocols Defined

### `ContextServiceProtocol`
- `append_message(chat_id: int, role: str, content: str) -> None`
- `load_recent_messages(chat_id: int, limit: int = 8) -> list[dict[str, str]]`

### `DocumentationServiceProtocol`
- `write_architecture_design(*, run_id, iteration, plan_text, design_text, role_name=None) -> Path`
- `write_test_plan(*, run_id, iteration, plan_text, design_text, test_text, role_name=None) -> Path`
- `write_review_report(*, run_id, iteration, plan_text, design_text, implementation_text, test_text, review_text, role_name=None) -> Path`
- `write_lesson(*, run_id, iteration, plan_text, lesson_text, role_name=None) -> Path`

### `LearningServiceProtocol`
- `remember_success(*, chat_id, workflow, prompt, result_text) -> None`
- `load_recent_learnings(chat_id) -> list[dict[str, str]]`

### `PlanningServiceProtocol`
- `draft_plan(prompt, prior_feedback=None) -> str` (async)
- `revise_plan(existing_prompt, feedback) -> tuple[str, str]` (async)

### `PromptServiceProtocol`
- `render(workflow, recent_messages, learned_items, user_prompt) -> tuple[str, str]`

### `ToolServiceProtocol`
- `list_enabled_tools(agent_name) -> list[str]`
- `execute_enabled_tool(agent_name, tool_name, payload, *, run_id=None, resume_stage=...) -> dict[str, str]`
- `install_package(package_name) -> dict[str, str]`
- `build_runtime_tool_context_async(run_id, agent_name, *, resume_stage=...) -> str` (async)
- `get_repository_context(platform=None) -> dict[str, dict[str, str]]`
- `get_platform_auth_status(platform) -> dict[str, str]`

### `WorkflowServiceProtocol`
- `build_execution_plan(workflow, *, agent_name) -> DirectExecutionPlan | MultiStageExecutionPlan`
- `create_design(plan_text, context_text) -> str` (async)
- `generate_code(plan_text, design_text, context_text, *, agent_name=None) -> str` (async)
- `execute_direct(agent_name, system_prompt, user_prompt) -> str` (async)
- `generate_tests(plan_text, design_text, implementation_text) -> str` (async)
- `review(plan_text, design_text, implementation_text, test_text) -> str` (async)
- `record_lesson(*, plan_text="", design_text="", implementation_text="", test_text="", review_text="", result_text="", error_text="", agent_name="") -> str` (async)
- `has_high_concerns(review_text) -> bool` (static method)

### `LLMGatewayProtocol`
- `generate(agent_name, system_prompt, user_prompt) -> str` (async)

### Adopted from domain layer
- `AgentRunRepository` — already a Protocol in `mergemate/domain/runs/repository.py`
- `RunJobRepository` — already a Protocol in `mergemate/domain/runs/repository.py`

## Changes to `OrchestratorDependencies`

```
@dataclass(slots=True, frozen=True)
class OrchestratorDependencies:
    run_repository: AgentRunRepository
    context_service: ContextServiceProtocol
    documentation_service: DocumentationServiceProtocol
    learning_service: LearningServiceProtocol
    planning_service: PlanningServiceProtocol
    prompt_service: PromptServiceProtocol
    tool_service: ToolServiceProtocol
    workflow_service: WorkflowServiceProtocol
    llm_gateway: LLMGatewayProtocol
    settings: Any                          # kept — config model, not a service
```

## Changes to `ExecutionRuntime`

```
@dataclass(slots=True)
class ExecutionRuntime:
    run_repository: AgentRunRepository
    context_service: ContextServiceProtocol
    documentation_service: DocumentationServiceProtocol
    learning_service: LearningServiceProtocol
    planning_service: PlanningServiceProtocol
    workflow_service: WorkflowServiceProtocol
    settings: Any                          # kept — config model
    is_cancelled: Callable[[str], bool]
```

## Changes to `_check_cancelled` and `_check_after_cancelled`

These helper functions in `execution_plan.py` use `run_repository: Any`
parameters.  Change the type annotation to `AgentRunRepository`.

## Changes to `stage.py` / `ExecutionContext`

The `run: Any` in `ExecutionContext` should use `AgentRun` from
`domain/runs/entities.py`.

## Not Changed

- `settings: Any` — left as-is because `AppConfig` is a concrete data class
  with many fields, not a service suitable for Protocol abstraction.
- `StageDescriptor`, `DirectExecutionPlan`, `MultiStageExecutionPlan` — these
  are data/implementation classes, not injected dependencies.

## Verification

1.  Run `mypy src/mergemate/application/ --strict` — all Protocol assignments
    should resolve (structural subtyping: concrete services implicitly satisfy
    the Protocols).
2.  Run `pytest tests/` — no behavioural change is expected.
3.  Confirm no concrete service class was modified.