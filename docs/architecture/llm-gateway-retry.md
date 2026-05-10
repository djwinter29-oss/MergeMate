# LLM Gateway Retry / Backoff Design

> **Status:** Design proposal  
> **Finding:** P0.1 — `_generate_from_provider()` has no retry/backoff logic  
> **Authored:** 2026-05-10

## 1. Problem Statement

The current `_generate_from_provider()` in `ParallelLLMGateway` (at `src/mergemate/infrastructure/llm/gateway.py`, line 110) delegates directly to `self._clients[name].generate()` with zero retry or backoff:

```python
async def _generate_from_provider(
    self,
    provider_name: str,
    system_prompt: str,
    user_prompt: str,
) -> str:
    result = await self._clients[provider_name].generate(system_prompt, user_prompt)
    if not isinstance(result, str):
        raise ProviderResponseError("Provider returned a non-text result.")
    return result
```

The HTTP call itself (inside `OpenAIAdapter.generate()`) uses `httpx.AsyncClient` with `response.raise_for_status()` — a single 429 Rate Limit, 503 Service Unavailable, or transient 5xx instantly propagates to the caller. In parallel mode (`combine_strategy = "sectioned"` or `"first_success"`), one transient failure means that provider's result is lost for the entire request, or in `first_success` mode, a slower provider may never get a chance to retry.

This creates three concrete failure modes:

| Scenario | Impact |
|---|---|
| Rate-limited (429) by upstream provider | Entire request fails or a parallel branch is silently dropped |
| Transient 5xx (502 Bad Gateway, 503 Service Unavailable) | Same — no point retrying at application level when a brief backoff would likely succeed |
| Network blip during `httpx` POST | `httpx.ConnectTimeout` or `httpx.ReadTimeout` kills the call, though retrying after a brief pause would succeed |

## 2. Design Goals

1. **Resilience** — transient HTTP failures and rate limits are automatically retried with backoff
2. **Configurable** — retry parameters (max retries, backoff base, jitter) are user-configurable via the config file, not hardcoded
3. **Rate limit aware** — 429 responses with `Retry-After` headers are respected
4. **Minimal blast radius** — retry logic lives at the gateway layer, not inside individual adapters. Adapters stay focused on request serialisation and response parsing
5. **No silent infinite loops** — retries have a hard cap, and non-retryable errors (auth failures, bad requests, parse errors) propagate immediately

## 3. Retry Policy Specification

### 3.1 Algorithm — Exponential Backoff with Jitter

Standard exponential backoff with full-jitter:

```
attempt = 0
while attempt < max_retries:
    response = await provider.generate(...)
    if succeeded:
        return response
    if not retryable(exception_or_status):
        raise
    attempt += 1
    if attempt >= max_retries:
        raise MaxRetriesExceededError(...)
    delay = random_uniform(0, base_delay * (2 ** attempt))
    await asyncio.sleep(delay)
```

**Parameters:**

| Parameter | Default | Description |
|---|---|---|
| `max_retries` | 3 | Maximum number of retry attempts (not including the initial call) |
| `base_delay_seconds` | 1.0 | Base backoff in seconds (doubles each attempt) |
| `max_delay_seconds` | 30.0 | Cap on the computed delay before jitter |
| `jitter` | `"full"` | One of `"full"` (0..N), `"equal"` (N/2..N), or `"none"` (N) |

**Why full-jitter:** Full jitter (`random(0, delay)`) avoids thundering-herd when multiple parallel calls to the same provider are retried simultaneously — the equal spacing is destroyed and contention drops sharply. This is well-documented in AWS and Google SRE literature.

### 3.2 Rate-Limit Handling (429)

When the provider returns HTTP 429 with a `Retry-After` header:

1. Parse `Retry-After` (supports both integer seconds and HTTP-date formats per RFC 7231)
2. If the `Retry-After` value exceeds `max_delay_seconds`, cap it
3. Add a small random jitter (`±20%`) to avoid synchronized re-queuing
4. Use this computed delay instead of the exponential backoff for this attempt
5. This delay **does not** consume a retry attempt — 429 with Retry-After is treated as a signal to wait, not a retry budget debit

### 3.3 Retry Budget & Circuit Breaker Awareness

A retry budget prevents cascading retry storms at the application level:

```
per_provider_retry_count_30s + per_call_attempts < max_retries
```

If a provider has already consumed its retry budget within a sliding 30-second window, subsequent calls fail-fast with a `ProviderRetryBudgetExhaustedError` instead of attempting retries. This is a **soft circuit breaker** — it resets after the window expires.

**Why soft and not a full circuit breaker:** A full circuit breaker (open/closed/half-open) is a larger design decision that would require state persistence, health-check endpoints, and interaction with the `first_success` / `sectioned` combine strategies. A sliding-window retry budget is much simpler, prevents the most common failure pattern (infinite retry loops under load), and can be replaced with a full circuit breaker later.

### 3.4 Exception Classification (Retryable vs Non-Retryable)

Classification happens at the `_generate_from_provider()` level based on the exception type raised by the underlying client.

#### Retryable exceptions

| Exception / Condition | Source | Notes |
|---|---|---|
| `httpx.ConnectTimeout` | httpx client | Network reachability issue |
| `httpx.ReadTimeout` | httpx client | Upstream slow to respond |
| `httpx.WriteTimeout` | httpx client | Request body not sent in time |
| `httpx.PoolTimeout` | httpx client | Connection pool exhausted |
| `httpx.ConnectError` | httpx client | DNS / TCP handshake failure |
| `httpx.RemoteProtocolError` | httpx client | Connection reset or hung up |
| `httpx.HTTPStatusError` with status 429 | `response.raise_for_status()` | Rate limit |
| `httpx.HTTPStatusError` with status 5xx | `response.raise_for_status()` | Transient server error |
| `asyncio.TimeoutError` | `asyncio.wait_for` wrapper (if used) | Overall call timeout |

#### Non-retryable exceptions

| Exception / Condition | Source | Reason |
|---|---|---|
| `httpx.HTTPStatusError` with status 4xx (except 429) | httpx client | Auth (401, 403), bad request (400), not found (404), method not allowed (405) — retrying will produce the same result |
| `ConfigurationError` | Adapter | Misconfiguration like missing API key or invalid URL format — retrying won't fix it |
| `ProviderResponseError` | Adapter / Gateway | Provider returned garbage (non-JSON, missing fields, non-string content) — the payload was accepted but the response is malformed; retry would produce the same output |
| `asyncio.CancelledError` | asyncio | Task was cancelled by `first_success` race winner — should not retry into a cancelled flow |

## 4. Config Schema for Retry Parameters

A new `RetryConfig` model added to `src/mergemate/config/models.py`:

```python
class RetryConfig(BaseModel):
    """Configuration for LLM gateway retry / backoff behaviour."""

    max_retries: int = Field(default=3, ge=0, description="Max retry attempts per call (0 = no retry)")
    base_delay_seconds: float = Field(default=1.0, ge=0.1, description="Base backoff delay in seconds")
    max_delay_seconds: float = Field(default=30.0, ge=1.0, description="Cap on computed delay before jitter")
    jitter_mode: Literal["full", "equal", "none"] = Field(default="full", description="Jitter strategy")
    retry_budget_window_seconds: float = Field(default=30.0, ge=1.0, description="Sliding window for retry budget tracking")
    retry_budget_max_spend: int = Field(default=6, ge=1, description="Max retry attempts across all calls within the sliding window")
```

Integrated into `RuntimeConfig` (the most logical home since it governs runtime behaviour):

```python
class RuntimeConfig(BaseModel):
    max_concurrent_runs: int = Field(default=2, ge=1)
    status_update_interval_seconds: int = Field(default=5, ge=1)
    default_request_timeout_seconds: int = Field(default=300, ge=1)
    job_lease_seconds: int = Field(default=30, ge=1)
    job_heartbeat_interval_seconds: int = Field(default=10, ge=1)
    retry: RetryConfig = Field(default_factory=RetryConfig)  # NEW
```

Per-provider override is **not** included in this design. The rationale is that provider-level retry tolerance is a runtime concern (the gateway decides based on the failure type), not a config-declared concern. Per-provider overrides can be added later by extending `ProviderConfig` with an optional `retry_overrides: RetryConfig | None = None` field if real-world usage shows the need.

### YAML Example

```yaml
runtime:
  max_concurrent_runs: 2
  retry:
    max_retries: 3
    base_delay_seconds: 0.5
    max_delay_seconds: 30.0
    jitter_mode: full
    retry_budget_window_seconds: 30.0
    retry_budget_max_spend: 6
```

## 5. Integration Points

### 5.1 New Exception Classes

In `src/mergemate/domain/shared/exceptions.py`, add under the LLM / provider errors section:

```python
class ProviderRetryExhaustedError(ProviderError):
    """Max retry attempts exceeded for a single provider call."""


class ProviderRetryBudgetExhaustedError(ProviderError):
    """Retry budget exhausted for a provider within the sliding window."""
```

### 5.2 New Module: Retry Decorator / Helper

A new module `src/mergemate/infrastructure/llm/retry.py` containing:

```python
@dataclass
class RetryPolicy:
    max_retries: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_mode: JitterMode  # enum: FULL, EQUAL, NONE
    retry_budget_window_seconds: float
    retry_budget_max_spend: int

class RetryBudgetTracker:
    """Tracks retry spend per provider within a sliding window."""
    def __init__(self, window_seconds: float, max_spend: int) -> None: ...
    def can_retry(self, provider_name: str) -> bool: ...
    def record_attempt(self, provider_name: str) -> None: ...
    def reset(self) -> None: ...

def _compute_delay(
    attempt: int,
    base_delay: float,
    max_delay: float,
    jitter_mode: JitterMode,
    retry_after_header: str | None = None,
) -> float: ...

def _is_retryable(exc: BaseException) -> bool: ...

async def with_retry(
    coro_fn: Callable[[], Awaitable[str]],
    provider_name: str,
    policy: RetryPolicy,
    budget_tracker: RetryBudgetTracker,
) -> str: ...
```

The `with_retry` function wraps any `Callable[[], Awaitable[str]]` — it doesn't depend on `ParallelLLMGateway` internals. This makes it unit-testable in isolation.

### 5.3 Changes to `ParallelLLMGateway`

**Constructor** adds `retry_policy: RetryConfig | None` parameter:

```python
class ParallelLLMGateway:
    def __init__(
        self,
        settings: Any,
        clients: Mapping[str, LLMClient],
        retry_policy: RetryConfig | None = None,
    ) -> None:
        ...
        self._retry_policy = retry_policy
        self._retry_budget = RetryBudgetTracker(...) if retry_policy else None
```

**`_generate_from_provider`** becomes:

```python
async def _generate_from_provider(
    self, provider_name: str, system_prompt: str, user_prompt: str,
) -> str:
    async def _do_generate() -> str:
        result = await self._clients[provider_name].generate(system_prompt, user_prompt)
        if not isinstance(result, str):
            raise ProviderResponseError("Provider returned a non-text result.")
        return result

    if self._retry_policy is not None:
        return await with_retry(
            _do_generate,
            provider_name,
            self._retry_policy,
            self._retry_budget,
        )
    return await _do_generate()  # no retry when retry_policy is None
```

**`_generate_first_success_result`** is a caller of `_generate_from_provider`, so it automatically inherits retry behaviour. This is intentional — when racing providers, even though the first success cancels others, each individual call should still have its own retry budget so that a transient 503 from a fast provider doesn't cause it to lose the race to a slower-but-equal provider.

### 5.4 Changes to `bootstrap.py`

When constructing `ParallelLLMGateway`, pass the retry config:

```python
gateway = ParallelLLMGateway(
    settings=config,
    clients=adapter_map,
    retry_policy=config.runtime.retry,
)
```

No changes to the adapter construction — adapters remain HTTP-call-focused and should not know about retries.

### 5.5 Test Strategy

New test file: `tests/unit/mergemate/infrastructure/llm/test_retry.py`

| Test case | Expected behaviour |
|---|---|
| Single transient failure (httpx.ConnectTimeout) on first attempt | Retries once, succeeds on second, returns result |
| 3 consecutive transient failures | Raises `ProviderRetryExhaustedError` after 3 retries |
| 429 with Retry-After header | Waits exactly the Retry-After duration (not exponential backoff), then retries |
| Non-retryable 401 | Propagates immediately, no retry |
| Non-str result on retry attempt | Raises `ProviderResponseError` (non-retryable) without further retry |
| Retry budget exhausted within window | Raises `ProviderRetryBudgetExhaustedError` immediately — no attempt |
| `max_retries=0` (retries disabled) | No retry logic invoked, original exception propagates |
| Two parallel providers both with transient failures | Each gets its own independent retry budget; one succeeding does not affect the other's retries |
| `asyncio.CancelledError` during retry sleep | Cancellation propagates immediately, no retry |

## 6. Interaction with Existing Modes

### 6.1 Single Mode (`parallel_mode = "single"`)

The single provider call gets full retry/backoff. If all retries are exhausted, the error propagates to the caller (`generate()`) which propagates it upward. This is strictly better than the current behaviour (single transient failure = total failure).

### 6.2 Sectioned Mode (`parallel_mode = "parallel"`, `combine_strategy = "sectioned"`)

Each parallel provider call independently applies retry/backoff. `asyncio.gather(return_exceptions=True)` captures `ProviderRetryExhaustedError` as a normal failure. The sectioned formatter still shows the provider's failure in the `failed_models` section. No behavioural change — just fewer failures in practice.

### 6.3 First-Success Mode (`parallel_mode = "parallel"`, `combine_strategy = "first_success"`)

Each racing call independently retries. When one succeeds and cancels the others, the cancellation propagates through `asyncio.CancelledError` which is non-retryable — so the retry loop exits cleanly. The racing behaviour is preserved, but each racer is more resilient to transient blips.

### 6.4 Sequential Fallback (from provider-compatibility-expansion design)

The sequential fallback proposal (`FallbackProviderGroup`) would compose naturally: each member provider in the fallback chain gets its own retry/backoff. If a provider exhausts retries, the fallback moves to the next provider. If all providers exhaust retries, `AllProvidersFailedError` is raised.

## 7. Non-Goals (Future Work)

| Feature | Why excluded |
|---|---|
| Full circuit breaker (open/closed/half-open) | Needs state persistence, health probes, and coordination that would triple the scope of this change. The sliding-window retry budget covers the most common overload case |
| Per-provider retry config overrides | Can be added later by extending `ProviderConfig` with `retry_overrides`. Not needed for initial implementation |
| Retry metrics / observability hooks | Should be added when telemetry infrastructure exists. The retry module can emit callbacks for logging |
| Backpressure (rejecting inbound Telegram requests when upstream is overloaded) | A separate concern — belongs in the Telegram interface layer, not the LLM gateway |

## 8. Migration Plan

1. **Phase 1 — Add model + exception classes** (this design sprint): `RetryConfig`, `RetryPolicy`, `RetryBudgetTracker`, exception classes, `_is_retryable()` helper — no behavioural change yet
2. **Phase 2 — Add `with_retry` wrapper + tests**: Unit tests covering all retry scenarios, parallel safety, cancellation handling
3. **Phase 3 — Wire into `ParallelLLMGateway`**: Pass `retry_policy` from constructor, update `_generate_from_provider`, update `bootstrap.py`
4. **Phase 4 — Configuration**: Users can set `runtime.retry.*` in config YAML. Default values preserve today's behaviour (3 retries, 1s base, full jitter). No migration burden.

## 9. Rejected Alternatives

### 9.1 Retry inside the adapter (OpenAIAdapter)

Putting retry logic inside `OpenAIAdapter.generate()` would couple retry concerns with HTTP serialisation logic. Since the retry policy is a gateway-level concern (same policy applies to all providers), centralising it at the gateway level is cleaner. Adapters don't need to know about retries — they raise the right exceptions and the gateway handles the rest.

### 9.2 Tenacity / backoff library

Popular retry libraries (`tenacity`, `backoff`) provide decorator-based retry logic. However:

- They don't natively support sliding-window retry budgets across parallel calls
- The exception classification logic would need to be reimplemented as a custom `retry_if_exception` predicate anyway
- Adding a third-party dependency for what is essentially a `while` loop + `asyncio.sleep` adds audit and maintenance overhead

A 50-line custom helper (`with_retry`) is more transparent, testable, and fits the project's existing dependency philosophy.

### 9.3 Full circuit breaker (e.g., `pybreaker`)

A circuit breaker would require state management across calls, health-check endpoints, and half-open probe logic. This is warranted when a provider is persistently down for minutes at a time — but MergeMate's current use case is recovering from transient 429s and 503s within seconds. The sliding-window retry budget is a simpler, strictly better starting point.