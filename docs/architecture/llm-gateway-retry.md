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
4. **Minimal blast radius** — retry logic lives at the gateway layer, not inside individual adapters
5. **No silent infinite loops** — retries have a hard cap, and non-retryable errors (auth failures, bad requests, parse errors) propagate immediately

## 3. Retry Policy Specification

### 3.1 Algorithm — Exponential Backoff with Full-Jitter

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

Full jitter avoids thundering-herd when multiple parallel calls retry simultaneously.

### 3.2 Rate-Limit Handling (429)

When the provider returns HTTP 429 with a `Retry-After` header: the `Retry-After` value is parsed, and that delay is used instead of the exponential backoff. This delay **does not** consume the retry budget.

### 3.3 Retry Budget (Soft Circuit Breaker)

A sliding-window retry budget prevents cascading retry storms. If the number of retries in the last `budget_window_seconds` exceeds `budget_max_retries`, further retry attempts fail-fast. 429 rate-limit retries do not consume budget.

### 3.4 Exception Classification

**Retryable:** httpx timeout/connect errors, 5xx, 429, IOError, OSError
**Non-retryable:** CancelledError, ProviderResponseError, AllProvidersFailedError, 4xx (except 429)

### 3.5 Config Schema

```python
class RetryConfig(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    base_delay_seconds: float = Field(default=1.0, ge=0.1)
    max_delay_seconds: float = Field(default=30.0, ge=1.0)
    budget_window_seconds: float = Field(default=30.0, ge=1.0)
    budget_max_retries: int = Field(default=6, ge=1)
```

Integrated into `RuntimeConfig`:

```python
class RuntimeConfig(BaseModel):
    ...
    retry: RetryConfig = Field(default_factory=RetryConfig)
```

## 4. Integration Points

### 4.1 Retry Helper

```python
async def with_retry(
    fn: Callable[[], Any],
    cfg: RetryConfig,
    *,
    _budget_override: _RetryBudget | None = None,
) -> str:
```

### 4.2 `_generate_from_provider` Wrapper

The existing `_generate_from_provider()` reads `settings.runtime.llm_retry`, and still accepts the legacy `settings.runtime.retry` alias for backward compatibility, then wraps the call in `with_retry()`. The `generate()` single-mode path now delegates to `_generate_from_provider()` to share retry logic.

## 5. Non-Goals (Future Work)

| Feature | Why excluded |
|---|---|
| Full circuit breaker (open/closed/half-open) | Needs state persistence, health probes; sliding-window budget covers common overload case |
| Per-provider retry config overrides | Can be added later by extending `ProviderConfig` |
| Retry metrics / observability hooks | Should be added when telemetry infrastructure exists |
| Backpressure | Belongs in the Telegram interface layer, not the LLM gateway |