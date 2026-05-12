# Integration Tests for Async Execution Pipeline

## Status: Implemented in progress notifier

## Motivation

Current test coverage (374 unit tests) covers individual components in isolation but leaves three gaps in the async pipeline:

1. **Progress notifier `watch_run_progress`** -- now has a configurable `max_poll_iterations` guard so a stuck run cannot keep the watcher alive indefinitely.

2. **CI e2e marker** -- integration tests (test_orchestrator_integration.py, test_submit_prompt_flow.py) exist but run as regular `pytest -q`, indistinguishable from unit tests. A dedicated CI step with `--run-e2e` or an `integration` marker would catch regressions in the async pipeline separately.

3. **No parameterized polling/webhook mode test** -- the e2e test at `tests/e2e/mergemate/interfaces/telegram/test_prompt_flow.py` tests Telegram handlers with stubs but doesn't exercise the full stack (real SQLite -> orchestrator -> execution plan -> LLM gateway).

## Design

### 1. Progress Notifier Integration Test

Add `tests/integration/mergemate/interfaces/telegram/test_progress_notifier_integration.py`

#### Test Scenarios

| Scenario | Description |
|----------|-------------|
| Default happy path | Start watcher on QUEUED run; feed stage transitions; verify watcher exits with COMPLETED status |
| Async timeout guard | Watcher should stop after N polls with no terminal status (configurable max_polls) |
| Duplicate snapshot dedup | Same status+stage twice -> no duplicate message sent |
| Terminal delivery retry | notify_terminal_update fails -> retry on next poll |
| Missing run (deleted mid-watch) | run becomes None -> watcher exits cleanly |
| Max iterations guard | watcher respects max_polls config value |
| Cancellation mid-watch | run transitions to CANCELLED -> watcher sends cancellation message and exits |

#### Test Infrastructure

```python
class FakeBot:
    def __init__(self):
        self.sent = []  # list of (chat_id, text)

    async def send_message(self, *, chat_id, text):
        self.sent.append((chat_id, text))

class StageSequenceRunRepo:
    """Returns a pre-defined sequence of run states to simulate progress."""

    def __init__(self, stages: list[AgentRun]):
        self.stages = list(stages)
        self.call_count = 0

    def execute(self, run_id):
        if self.call_count >= len(self.stages):
            return self.stages[-1]
        result = self.stages[self.call_count]
        self.call_count += 1
        return result
```

The watcher runs with `interval_seconds=0.01` (fast polling) and `max_polls=50` (safe upper bound so tests don't hang).

Async timeout configuration: add a `max_polls` parameter to `watch_run_progress` with default `None` (unlimited) -- or a `runtime.settings.runtime.max_poll_iterations` setting. The integration test overrides this to `50` so the test cannot loop forever.

#### Existing Bug Coverage

The PR #16 "infinite loop bug" in `watch_run_progress` occurs when:
- The run is stuck in an intermediate state (no terminal status)
- `last_snapshot` matches every poll -> `continue` without progress
- No max-polls guard -> `while True` runs indefinitely

The fix (likely a max-iterations count) should be verified by the "max iterations guard" test above.

### 2. CI Job for Integration / E2E Tests

Add a new step to `.github/workflows/pr-checks.yml`:

```yaml
- name: Run integration + e2e tests
  run: pytest -q --run-e2e -m 'integration or e2e'
```

Also register pytest markers in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests that verify component interactions with real dependencies",
    "e2e: marks tests that simulate the full Telegram prompt flow",
]
```

Add the `integration` marker to existing integration test classes:

- `tests/integration/mergemate/application/test_execution_plan_integration.py` -- add `@pytest.mark.integration` to all test classes
- `tests/integration/mergemate/application/test_orchestrator_integration.py` -- same
- `tests/integration/mergemate/application/test_submit_prompt_flow.py` -- same
- `tests/e2e/mergemate/interfaces/telegram/test_prompt_flow.py` -- add `@pytest.mark.e2e`

The root conftest's `pytest_collection_modifyitems` already skips e2e tests unless `--run-e2e` is passed, so the existing skip logic stays.

### 3. E2E Test Parameterization

Add a `mode` fixture parameterized to `["polling", "webhook"]` that controls whether the progress notifier is enabled (polling mode) or disabled (webhook mode). In webhook mode, the run still completes but no polling is started.

This requires the e2e test handler to inject a different runtime settings object. Rather than modifying the existing Telegram handler tests (which test handler internals), add new parameterized test functions:

```python
@pytest.mark.parametrize("mode", ["polling", "webhook"])
async def test_full_prompt_flow_with_mode(sqlite_runtime, mode):
    # Build runtime with mode-dependent config
    # Submit -> approve -> run -> verify completion
    ...
```

## Module Boundaries

```
tests/integration/mergemate/interfaces/telegram/
    test_progress_notifier_integration.py    # NEW
tests/integration/mergemate/application/
    test_execution_plan_integration.py       # MARKER ADDITION
    test_orchestrator_integration.py         # MARKER ADDITION
    test_submit_prompt_flow.py               # MARKER ADDITION + PARAMETERIZATION
tests/e2e/mergemate/interfaces/telegram/
    test_prompt_flow.py                      # MARKER ADDITION
.github/workflows/
    pr-checks.yml                            # CI STEP ADDITION
pyproject.toml                               # MARKER REGISTRATION
```

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Progress notifier timeout | Configurable `max_polls` param (default unlimited) | Backward compatible; integration test sets low value |
| CI approach | `pytest -q --run-e2e -m 'integration or e2e'` | Reuses existing `--run-e2e` flag; markers provide flexible filtering |
| Mode parameterization | `@pytest.mark.parametrize` on test functions | No framework changes, idiomatic pytest |
| Marker registration | `pyproject.toml` markers section | Pytest best practice; avoids warnings about unknown markers |
| Existing tests | Add markers only, no code changes | Risk-minimizing: existing coverage stays untouched |

## Open Questions

1. Should `max_polls` be a parameter of `watch_run_progress` or a setting in `runtime.settings.runtime`? Prefer parameter (simpler API), but if `start_progress_watcher` also needs to pass it, a setting may be cleaner.
2. Should the e2e test mode parameterization be added to the existing test file or a new file? Prefer existing file -- adding `@pytest.mark.parametrize("mode", [...])` at the test function level with minimal diff.