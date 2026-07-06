# LLM Gateway Retry / Backoff Implementation

> **Status:** Implemented
> **PR:** #113 (this PR)

## Summary

This PR implements the design from `docs/architecture/llm-gateway-retry.md` (PR #111). It adds exponential full-jitter retry with a sliding-window retry budget (soft circuit breaker) and rate-limit awareness to `ParallelLLMGateway._generate_from_provider()`.

## Files Changed

### `src/mergemate/config/models.py`

- **New `RetryConfig` class** — Pydantic model with:
  - `max_retries` (default 3)
  - `base_delay_seconds` (default 2.0)
  - `max_delay_seconds` (default 60.0)
  - `budget_window_seconds` (default 60)
  - `budget_max_retries` (default 10)
- **`RuntimeConfig.llm_retry`** — New field, defaults to `RetryConfig()`

### `src/mergemate/infrastructure/llm/gateway.py`

- **`_is_retryable(exc)`** — Classifies exceptions:
  - Retryable: httpx timeout/connect/5xx/429, IOError, OSError
  - Non-retryable: CancelledError, ProviderResponseError, AllProvidersFailedError, unknown types
- **`_RetryBudget`** — Sliding-window counter; 429 does not consume budget
- **`_get_budget()` / `_reset_budget_for_testing()`** — Global singleton management
- **`_resolve_retry_config()`** — Reads `runtime.llm_retry` and falls back to the legacy `runtime.retry` alias
- **`_full_jitter_delay()`** — `random.uniform(0, min(max, base * 2^attempt))`
- **`with_retry()`** — Async retry wrapper: budget check, 429/Retry-After handling, exponential backoff
- **`_is_rate_limit()` / `_extract_retry_after()`** — HTTP 429 helpers
- **`_generate_from_provider()`** — Now wraps call in `with_retry()`; reads config from `settings.runtime.llm_retry` and honors the legacy `settings.runtime.retry` alias
- **Provider-specific retry overrides** — `providers.<name>.retry` is also honored when present and takes precedence over the runtime default for that provider
- **`generate()`** — Single-mode path now delegates to `_generate_from_provider()` (so it gets retry too)

### `tests/unit/mergemate/infrastructure/llm/test_gateway.py`

- `SettingsStub.runtime` field added
- **`TestRetryableClassification`** — 13 tests for exception classification
- **`TestFullJitterDelay`** — 5 tests for delay bounds and randomness
- **`TestRetryBudget`** — 6 tests for sliding-window budget behaviour
- **`TestWithRetry`** — 10 async tests for retry loop, budget exhaustion, 429 handling, cancellation
- **`TestParallelLLMGatewayWithRetry`** — 4 integration-style tests through the gateway

## Key Design Decisions

- Retry lives at the gateway layer, not inside adapters (per architecture decision)
- Full-jitter prevents thundering herd on parallel retries
- 429 with Retry-After delays without consuming retry budget
- Sliding-window budget is a soft circuit breaker (resets after window expires)
- No new dependencies — pure stdlib (asyncio, random, time)
- Per-provider retry overrides are supported now via `providers.<name>.retry`
- No full circuit breaker; the sliding window budget covers the common overload case