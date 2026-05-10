# Dynamic Progress Estimation

> Status: Design proposal  
> Near-Term Roadmap Item #1: "Improve progress estimates beyond the current static workflow estimate"  
> Authored: 2026-05-10

## 1. Problem Statement

The current `estimate_duration()` function at `src/mergemate/application/jobs/estimator.py` returns a hardcoded number per workflow name:

```python
estimates = {
    "generate_code": 30,
    "debug_code": 45,
    "explain_code": 20,
}
return estimates.get(workflow, 60)
```

This ignores:
- **Prompt complexity**: A trivial "fix typo" gets the same estimate as "implement OAuth2 with refresh tokens"
- **Task breakdown depth**: A 2-subtask plan gets the same estimate as a 15-subtask plan
- **Workflow specifics**: Direct-execution workflows (debug_code, explain_code) always take less than multi-stage (generate_code), but even within a workflow type, estimates don't vary
- **User-visible impact**: The Telegram progress notifier shows `Estimated remaining time: 30s` which is either laughably wrong or suspiciously stale, eroding trust

## 2. Current State Diagram

```
User prompt
    │
    ▼
SubmitPromptUseCase.execute()
    │
    ├─ estimate_seconds = estimate_duration(workflow)   ← static, 9-line function
    │
    └─ run = Run(..., estimate_seconds=estimate_seconds)
           │
           ▼
    Telegram notifier polls run.estimate_seconds
        → _remaining_seconds(run) computes elapsed
        → shows "Estimated remaining time: Xs"
```

## 3. Design Goals

1. **Estimates vary by prompt complexity** — not just workflow name
2. **Transparent fallback** — when no estimate can be computed, fall back to a static default (the current behaviour)
3. **Estimates evolve** — after planning completes, estimate should be refined from the task breakdown (number of tasks × roles)
4. **UI integration without refactoring** — the `run.estimate_seconds` field remains the single source of truth; the notifier and presenter already consume it
5. **Minimal blast radius** — no change to the existing notifier loop, presenter, or Run model

## 4. Approaches

### Approach A: Rule-Based Heuristic (Recommended)

A heuristic function that analyzes the prompt text for complexity signals after the plan is drafted, plus a pre-planning simple estimator.

#### Phase 1 — Pre-planning (before plan is drafted)

Replace `estimate_duration()` with a lightweight heuristic that uses prompt surface features:

```python
def estimate_pre_planning(prompt: str, workflow: str) -> int:
    """Estimate before plan exists — uses prompt surface features."""
    base = _base_by_workflow(workflow)  # generate_code=30, debug_code=45, etc.
    complexity = _prompt_complexity_score(prompt)
    return int(base * complexity)
```

**Complexity signals** (additive):
- Word count bands: `<50` → 0.8×, `50–200` → 1.0×, `>200` → 1.3×
- Reference keywords: "database", "API", "auth", "migration", "model", "schema", "config" → +0.1 each (cap at +0.6)
- Multi-file indicators: "class", "interface", "module", "component" → +0.15 each (cap at +0.4)
- Structural markers: numbered lists, code blocks, file paths → +0.1 each
- Lower bound: 0.5×, Upper bound: 2.5×

#### Phase 2 — Post-planning (after plan is approved)

Once `PlanningService.draft_plan()` returns a structured task breakdown, re-estimate using task count and role composition:

```python
def estimate_post_planning(tasks: list[dict]) -> int:
    """Estimate after plan gives us a task breakdown."""
    if not tasks:
        return None  # fall back to pre-planning estimate

    # Per-role base times (seconds)
    BASE_TIME_PER_ROLE = {
        "architect": 15,
        "coder": 25,
        "tester": 20,
        "reviewer": 10,
        "chronicler": 5,
        "planner": 5,
    }
    # Overhead per iteration (review loop adds time)
    REVIEW_OVERHEAD = 15

    total = 0
    unique_roles = set()
    for task in tasks:
        owner = task.get("owner", "coder")
        unique_roles.add(owner)
        total += BASE_TIME_PER_ROLE.get(owner, 20)

    # Sequential role overhead — each unique role adds a context switch
    total += len(unique_roles) * 5

    # Estimate 2 review iterations as default
    if "reviewer" in unique_roles:
        total += REVIEW_OVERHEAD

    return total
```

#### Integration point

The estimate gets updated **once** at the plan-approval boundary, in the orchestrator:

1. `SubmitPromptUseCase` calls `estimate_pre_planning(prompt, workflow)` → stores in `run.estimate_seconds`
2. User sees initial estimate in acknowledgement message
3. After plan approval, `AgentOrchestrator` (or a new `EstimateRefinementStep`) calls `estimate_post_planning(tasks)` → updates `run.estimate_seconds` via `run_repository`
4. Notifier picks up the updated estimate naturally on its next poll cycle

No changes needed in `progress_notifier.py` or `presenter.py`.

**Edge case — direct-execution workflows**: `debug_code`, `explain_code` never produce a task breakdown. The post-planning estimate returns `None`, so `run.estimate_seconds` keeps the pre-planning value throughout. Correct by design.

---

### Approach B: LLM-Based Estimation

Replace the heuristic with an LLM call that judges complexity and returns a JSON estimate.

```
async def estimate_complexity(prompt: str, workflow: str) -> int:
    response = await llm_gateway.generate(
        agent_name="planner",
        system_prompt="You are a complexity estimator...",
        user_prompt=f"Workflow: {workflow}\nPrompt: {prompt}\n\n"
                    "Return a JSON object: {\"estimate_seconds\": <int>, \"confidence\": \"high|medium|low\"}",
    )
    # Parse JSON, validate bounds, return
```

#### Trade-offs vs heuristic approach

| Dimension | Heuristic (Approach A) | LLM-Based (Approach B) |
|---|---|---|
| **Latency** | ~0ms (pure Python) | ~2–5s per LLM call |
| **Cost** | Zero | One LLM call per run |
| **Accuracy ceiling** | Medium — keyword heuristics plateau | High — can reason about actual complexity |
| **Predictability** | Deterministic, testable | Non-deterministic, hard to test |
| **Dependency** | None | Requires LLM gateway, planner role |
| **Fallback** | Trivial — always returns a number | Must still have fallback for parse failures |

**Conclusion**: The LLM approach is over-engineered for this use case. The heuristic is cheap, fast, and already a meaningful improvement over the current static estimate. An LLM call for estimation would add latency and cost to a flow that users expect to feel instant. LLM-based estimation could be explored as a future enhancement (Mid-Term) once the heuristic baseline exists and we have real-world runtime data to validate against.

#### Mitigating LLM risks (if pursued later)
- **Timeout guard**: wrap LLM call with `asyncio.wait_for(..., timeout=5.0)`
- **Parse failure**: fall back to `estimate_pre_planning(prompt, workflow)` on JSON parse error or timeout
- **Bounds clamping**: hard lower bound (5s) and upper bound (600s = 10 min) after LLM response

---

### Approach C: Data-Driven Calibration (Future)

Once enough runs have completed, use recorded `duration_seconds` (actual wall clock time from run creation to completion) to calibrate estimates dynamically.

```
─ Run table ────────────────────────
  workflow  | prompt_length | task_count | duration_seconds
  generate  | 245           | 8          | 127
  generate  | 89            | 3          | 52
  debug     | 412           | 0          | 34
  ...
```

A simple regression: `duration ≈ α·num_tasks + β·prompt_len + γ` — one coefficient per workflow.

**Not recommended for Near-Term** because:
- No historical data exists yet
- Requires a `duration_seconds` column or computed field in the Run model
- Adding a statistical dependency (scipy/sklearn) is disproportionate for the improvement
- The heuristic (Approach A) covers Near-Term needs; data-driven calibration is a natural Mid-Term follow-on once we have 50+ runs recorded

---

## 5. Recommendation

**Approach A (Rule-Based Heuristic)** with two-phase estimation.

### Why not Approach B (LLM)?
- Latency penalty on the critical path (user waits for the ack message)
- Non-deterministic estimates degrade UX consistency
- The information gain doesn't justify the cost at this stage
- Can be added as a future refinement layer if heuristic accuracy proves insufficient

### Implementation plan

#### Files to create
- `src/mergemate/domain/estimation/heuristic.py` — `estimate_pre_planning()` and `estimate_post_planning()`

#### Files to modify
- `src/mergemate/application/jobs/estimator.py` — replace `estimate_duration()` with a call to `estimate_pre_planning()`, keep backward compat
- `src/mergemate/application/use_cases/approve_run.py` or equivalent plan-approval handler — insert a call to `estimate_post_planning()` after plan is available

#### Files unaffected
- `src/mergemate/interfaces/telegram/progress_notifier.py` — no changes needed
- `src/mergemate/interfaces/telegram/presenter.py` — no changes, already reads `run.estimate_seconds`
- `src/mergemate/domain/shared/run.py` (the Run model) — no schema changes
- `src/mergemate/domain/policies/` — `uses_multi_stage_delivery` etc. unchanged

### Interface: EstimationService

```python
# Domain service — not tied to any framework
class EstimationService:
    @staticmethod
    def estimate_pre_planning(prompt: str, workflow: str) -> int:
        """
        Quick heuristic estimate before a plan exists.
        Uses prompt surface features and workflow base time.
        Always returns a positive integer (fallback = 60).
        """
        ...

    @staticmethod
    def estimate_post_planning(tasks: list[dict]) -> int | None:
        """
        Refined estimate from structured task breakdown.
        Returns None if no tasks available (caller keeps pre-planning estimate).
        """
        ...
```

### Data flow (after implementation)

```
User prompt
    │
    ▼
SubmitPromptUseCase.execute()
    │
    ├─ estimate_seconds = EstimationService.estimate_pre_planning(prompt, workflow)
    │     → prompt complexity multiplier × workflow base
    │     → e.g. "fix typo" → 18s, "build OAuth2" → 78s
    │
    └─ run = Run(..., estimate_seconds=estimate_seconds)
           │
           ▼
    Plan drafted → user approves
           │
           ▼
    ApproveRunUseCase / AgentOrchestrator
           │
           ├─ tasks = PlanningService.extract_tasks(plan_text)
           ├─ refined = EstimationService.estimate_post_planning(tasks)
           └─ if refined: run_repository.update_estimate(run_id, refined)
                  │
                  ▼
           Notifier polls run.estimate_seconds
                → now shows refined estimate (e.g. "Estimated remaining time: 75s")
```

## 6. Edge Cases

| Case | Behaviour |
|---|---|
| **Empty prompt** | `estimate_pre_planning("", workflow)` → returns workflow base × 0.5 (minimum multiplier) |
| **Unrecognised workflow** | Falls through to `estimates.get(workflow, 60)` in base, multiplied as usual |
| **Plan with no task breakdown** | `estimate_post_planning([])` → returns `None`; pre-planning estimate sticks |
| **Direct-execution workflow** (e.g. `debug_code`) | Task breakdown does not exist; pre-planning estimate never overwritten |
| **Plan approval without re-estimation** (e.g. auto-execution) | Same as above — refinement only happens if `estimate_post_planning` is explicitly called |
| **Review loop extends execution** | Post-planning estimate already includes a review overhead; actual iterations >1 are not tracked live (Mid-Term improvement) |
| **Run cancelled mid-execution** | Estimate irrelevant — terminal delivery fires with cancellation notice |
| **User revises plan** | On re-approval, `estimate_post_planning` runs again with the new plan's task breakdown |

## 7. Test Strategy

- `test_estimate_pre_planning_single_line_prompt` — short prompts produce lower multiplier
- `test_estimate_pre_planning_long_prompt` — long, structured prompts produce higher multiplier
- `test_estimate_pre_planning_complexity_keywords` — keywords like "database", "auth", "migration" increase estimate
- `test_estimate_pre_planning_minimum_multiplier` — verify lower bound (0.5×)
- `test_estimate_pre_planning_maximum_multiplier` — verify upper bound (2.5×)
- `test_estimate_post_planning_with_tasks` — verifies computation from task count + roles
- `test_estimate_post_planning_no_tasks` — returns None for empty list
- `test_estimate_post_planning_single_role` — only architect tasks
- `test_estimate_post_planning_unknown_role` — falls back to default 20s per task
- `test_estimate_pre_planning_unknown_workflow` — uses default 60s base

All tests are pure-function unit tests — no mocking, no async, no database.

## 8. Future Work (Mid-Term)

1. **LLM-based estimation layer** — wrap the heuristic with an optional LLM refinement call, similar to how `planning_service` drafts plans; the LLM can judge complexity more accurately than keywords for unusual prompts
2. **Live progress recalibration** — update `run.estimate_seconds` as stages complete using actual elapsed time + remaining average
3. **Historical calibration** — once 50+ run durations exist, fit a simple regression to replace the heuristic coefficients with data-driven ones
4. **Expose estimate in `/status`** — the `format_detailed_status` already shows it; optionally add a progress bar