# Implementation: Service Protocols

## Files Created

- `src/mergemate/application/protocols.py` — 8 Protocol classes for structural subtyping

## Files Modified

- `src/mergemate/application/execution_plan.py` — `OrchestratorDependencies` fields typed from `Any` → Protocols, `_check_cancelled`/`_check_after_cancelled` return type `Any | None` → `AgentRun | None`, `ExecutionContext.run` `Any` → `AgentRun`
- `tests/integration/mergemate/application/test_execution_plan_integration.py` — `LearningServiceSpy.remember_success` changed from `async def` to `def` (matching the real `LearningService` and the Protocol)
- `tests/integration/mergemate/application/test_orchestrator_integration.py` — `LearningServiceSpy.remember_success` same fix
- `tests/unit/mergemate/application/test_orchestrator.py` — `LearningServiceStub.remember_success` same fix

## 8 Protocols Defined

| Protocol | Satisfied by | Key methods |
|---|---|---|
| `ContextServiceProtocol` | `ContextService` | `append_message`, `load_recent_messages` |
| `DocumentationServiceProtocol` | `DocumentationService` | `write_architecture_design`, `write_test_plan`, `write_review_report`, `write_lesson` |
| `LearningServiceProtocol` | `LearningService` | `remember_success`, `load_recent_learnings` |
| `PlanningServiceProtocol` | `PlanningService` | `draft_plan`, `revise_plan` |
| `PromptServiceProtocol` | `PromptService` | `render` |
| `ToolServiceProtocol` | `ToolService` | `list_enabled_tools`, `execute_enabled_tool`, `install_package`, `build_runtime_tool_context_async`, `get_repository_context`, `get_platform_auth_status` |
| `WorkflowServiceProtocol` | `WorkflowService` | `build_execution_plan`, `create_design`, `generate_code`, `execute_direct`, `generate_tests`, `review`, `record_lesson`, `has_high_concerns` |
| `LLMGatewayProtocol` | `ParallelLLMGateway` | `generate` |

## Design Decisions

- **`WorkflowServiceProtocol.build_execution_plan`** returns `DirectExecutionPlan | MultiStageExecutionPlan` — these types are defined in `execution_plan.py`. Used `TYPE_CHECKING` guard with `from __future__ import annotations` to avoid circular import at runtime.
- **`settings: Any` kept** — the config model `AppConfig` is a concrete data class, not a service. Per architecture design doc.
- **Structural subtyping** — no concrete service class was modified. Protocols are structurally satisfied.
- **`LearningServiceProtocol.remember_success` is sync** — matches the concrete `LearningService`. Test spies were fixed from `async def` to `def` accordingly.

## Verification

```bash
cd /home/pi/MergeMate && PYTHONPATH=src mypy src/mergemate/application/ --strict
cd /home/pi/MergeMate && PYTHONPATH=src python -m pytest tests/integration/mergemate/application/test_execution_plan_integration.py -v
```

Both pass clean.