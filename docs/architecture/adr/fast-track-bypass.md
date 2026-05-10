# Fast-Track Approval Bypass

> Follow-on to ADR-005 (Approval-Gated Multi-Stage Workflow) and ADR-009 (Config-Driven Workflow Dispatch)

## Status

Proposed

## Decision

MergeMate will add a **fast-track approval bypass** that lets specific workflows, user-triggered flags, or explicit CLI options skip the `awaiting_confirmation` state. When bypassed, a run transitions directly from `planning` to `queued` (or, for known-trivial workflows, directly from `PLANNING` to `EXECUTION` without waiting for user confirmation).

## Rationale

The current `workflow_control.require_confirmation` is a single global boolean. Every workflow — from `explain_code` (trivial, read-only) to `generate_code` (expensive, multi-stage) — follows the same confirmation gate. This forces unnecessary friction on fast, low-risk interactions:

- `explain_code` and `debug_code` are read-only or self-contained workflows with near-zero cost. Asking for confirmation before running them breaks the interactive flow.
- Operators who want to run a headless session without manual confirmation have no way to signal that intent at invocation time.
- Adding new user-facing workflows in the future requires either disabling confirmation globally (risky) or accepting the friction for every workflow equally.

## Design

### 1. Config Schema — Per-Workflow Fast-Track

Extend `WorkflowControlConfig` with an optional `fast_track_workflows` set:

```yaml
workflow_control:
  require_confirmation: true          # default for all workflows
  fast_track_workflows:              # these skip confirmation
    - explain_code
    - debug_code
  max_review_iterations: 5
```

The `WorkflowControlConfig` Pydantic model gets a new field:

```python
class WorkflowControlConfig(BaseModel):
    require_confirmation: bool = True
    fast_track_workflows: set[str] = Field(default_factory=set)
    max_review_iterations: int = Field(default=5, ge=1)
```

Backward compat: when `fast_track_workflows` is absent or empty, all workflows respect `require_confirmation` — existing configs continue working identically.

### 2. CLI Flag — `--no-confirm`

Add a `--no-confirm` / `--yes` flag to the CLI `mergemate run` subcommand. This is available even for workflows NOT in `fast_track_workflows`, giving the operator explicit one-shot override.

Semantics: when `--no-confirm` is passed, the command creates the run with status `QUEUED` (or jumps directly to execution for direct-execution workflows) regardless of `require_confirmation` and `fast_track_workflows` settings.

### 3. Runtime Decision Logic

The approval decision is a single function/predicate. Currently in `submit_prompt.py`:

```python
require_confirmation = self._settings.workflow_control.require_confirmation
initial_status = (
    RunStatus.AWAITING_CONFIRMATION if require_confirmation else RunStatus.QUEUED
)
```

After this change the logic becomes:

```python
def _needs_confirmation(
    workflow_control: WorkflowControlConfig,
    workflow: str,
    no_confirm_override: bool = False,
) -> bool:
    # Hard override from CLI or API flag
    if no_confirm_override:
        return False
    # Check per-workflow fast-track list
    if workflow in workflow_control.fast_track_workflows:
        return False
    # Fall back to global default
    return workflow_control.require_confirmation
```

Key properties:

- **Backward compatible**: existing configs have `fast_track_workflows={}`, so the function falls through to `require_confirmation`.
- **Per-workflow opt-in**: an operator adds `explain_code` to the fast-track list; `generate_code` still gates on confirmation.
- **Explicit override wins**: `--no-confirm` beats everything, even `require_confirmation=True`.

### 4. Wireframe of the Approval Decision Logic

```
User submits prompt (via Telegram or CLI)
              │
              ▼
    Resolve workflow from agent config
              │
              ▼
    ┌───────────────────────────────────────┐
    │  _needs_confirmation(                 │
    │    workflow_control,                  │
    │    workflow,                          │
    │    no_confirm_override,               │
    │  )                                    │
    │                                       │
    │  1. no_confirm_override=True?  ─── YES ──► return False (skip)
    │  2. workflow in fast_track_workflows? ── YES ──► return False (skip)
    │  3. require_confirmation=True?  ─ YES ──► return True (gate)
    │  4. Else                           ────► return False (skip)
    └───────────────────────────────────────┘
              │
         ┌────┴────┐
         ▼         ▼
    AWAITING_    QUEUED
    CONFIRMATION
```

### 5. Where the Change Lives

| Concern | File | Change |
|---|---|---|
| Config model | `src/mergemate/config/models.py` | Add `fast_track_workflows: set[str]` to `WorkflowControlConfig` |
| Decision logic | `src/mergemate/application/use_cases/submit_prompt.py` | Inline or extract `_needs_confirmation()`; pass `no_confirm_override` through call chain |
| Workflow resolution | `src/mergemate/interfaces/telegram/handlers.py` | Telegram handler has no CLI flag — uses config-only decision |
| CLI invocation | `src/mergemate/interfaces/cli/` (new or existing) | Add `--no-confirm` flag to `mergemate run`; pass as parameter through `SubmitPromptUseCase` |
| Defaults | `src/mergemate/config/defaults.yaml` | Optionally add `fast_track_workflows: []` (omitting is identical) |

## Consequences

- **Positive**: `explain_code` becomes a "fire and forget" workflow — no confirmation dialog, faster interaction.
- **Positive**: `debug_code` can skip confirmation for debugging sessions where the user is iterating rapidly.
- **Positive**: CLI scripting works without requiring manual approval for headless automation.
- **Positive**: Global `require_confirmation: true` can stay on for high-cost workflows while low-cost ones bypass it.
- **Negative**: The decision logic now has three sources of truth (global flag, workflow list, CLI flag). The function `_needs_confirmation` centralizes the combinatorics — all callers route through it.
- **Negative**: `--no-confirm` on a `generate_code` run means the user commits to potentially expensive multi-stage execution without seeing a plan first. This is an explicit operator choice.

## Implementation Order

1. Add the `fast_track_workflows` field to `WorkflowControlConfig` in `models.py`.
2. Extract `_needs_confirmation()` in `submit_prompt.py` and wire it into the `execute()` method.
3. Thread a `no_confirm_override: bool` parameter through `SubmitPromptUseCase.execute()`.
4. Add `--no-confirm` to the CLI command handler.
5. Update `defaults.yaml` with `fast_track_workflows: []` for explicitness.
6. Update `docs/architecture/02-runtime-architecture.md` to mention the fast-track bypass.
7. Update `docs/architecture/03-async-job-lifecycle.md` to include `fast_track_workflows` in the intake step.