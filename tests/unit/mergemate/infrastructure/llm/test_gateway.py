from dataclasses import dataclass, field
from datetime import datetime, timezone
import asyncio
import time as time_module
from types import SimpleNamespace

import httpx
import pytest
from unittest.mock import MagicMock

from mergemate.config.models import RetryConfig
from mergemate.domain.shared.exceptions import AllProvidersFailedError, ProviderResponseError
from mergemate.infrastructure.llm.gateway import (
    ParallelLLMGateway,
    _extract_retry_after,
    _full_jitter_delay,
    _is_retryable,
    _RetryBudget,
    with_retry,
)


class ClientStub:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls = []

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class NonStrClientStub:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls = []

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.result  # type: ignore[return-value]


class DelayedClientStub:
    def __init__(self, result: str, *, delay_seconds: float) -> None:
        self.result = result
        self.delay_seconds = delay_seconds
        self.cancelled = False

    async def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            await asyncio.sleep(self.delay_seconds)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return self.result


@dataclass(slots=True)
class AgentStub:
    parallel_mode: str = "single"
    combine_strategy: str = "sectioned"


@dataclass(slots=True)
class SettingsStub:
    provider_names: list[str]
    agents: dict[str, AgentStub] = field(default_factory=dict)
    providers: object = None
    runtime: object = None

    def resolve_agent_provider_names(self, agent_name: str) -> list[str]:
        return self.provider_names


@pytest.mark.asyncio
async def test_generate_raises_when_no_providers_available() -> None:
    gateway = ParallelLLMGateway(SettingsStub(provider_names=["missing"]), {})

    with pytest.raises(AllProvidersFailedError, match="No configured providers"):
        await gateway.generate("coder", "system", "user")


@pytest.mark.asyncio
async def test_generate_reports_missing_provider_aliases_when_none_are_available() -> None:
    gateway = ParallelLLMGateway(SettingsStub(provider_names=["missing-one", "missing-two"]), {})

    with pytest.raises(
        AllProvidersFailedError,
        match=r"Configured providers: missing-one, missing-two\. Missing clients: missing-one, missing-two\.",
    ):
        await gateway.generate("coder", "system", "user")


@pytest.mark.asyncio
async def test_generate_uses_first_available_provider_for_single_mode() -> None:
    client = ClientStub("ok")
    settings = SettingsStub(
        provider_names=["one"], agents={"coder": AgentStub(parallel_mode="single")}
    )
    gateway = ParallelLLMGateway(settings, {"one": client})

    result = await gateway.generate("coder", "system", "user")

    assert result == "ok"
    assert client.calls == [("system", "user")]


@pytest.mark.asyncio
async def test_generate_returns_first_success_for_parallel_mode() -> None:
    first = ClientStub("first")
    second = ClientStub("second")
    settings = SettingsStub(
        provider_names=["one", "two"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="first_success")},
    )
    gateway = ParallelLLMGateway(settings, {"one": first, "two": second})

    result = await gateway.generate("coder", "system", "user")

    assert result == "first"


@pytest.mark.asyncio
async def test_generate_deduplicates_repeated_provider_aliases() -> None:
    first = ClientStub("first")
    second = ClientStub("second")
    settings = SettingsStub(
        provider_names=["one", "one", "two", "one"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="sectioned")},
    )
    gateway = ParallelLLMGateway(settings, {"one": first, "two": second})

    result = await gateway.generate("coder", "system", "user")

    assert result.count("## one\nfirst") == 1
    assert result.count("## two\nsecond") == 1
    assert first.calls == [("system", "user")]
    assert second.calls == [("system", "user")]


@pytest.mark.asyncio
async def test_generate_first_success_cancels_slower_parallel_calls() -> None:
    fast = DelayedClientStub("fast", delay_seconds=0.01)
    slow = DelayedClientStub("slow", delay_seconds=5)
    settings = SettingsStub(
        provider_names=["fast", "slow"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="first_success")},
    )
    gateway = ParallelLLMGateway(settings, {"fast": fast, "slow": slow})

    result = await gateway.generate("coder", "system", "user")

    assert result == "fast"
    assert slow.cancelled is True


@pytest.mark.asyncio
async def test_generate_formats_sectioned_parallel_results_and_failures() -> None:
    first = ClientStub(" first result ")
    second = ClientStub(RuntimeError("broken"))
    settings = SettingsStub(
        provider_names=["one", "two"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="sectioned")},
    )
    gateway = ParallelLLMGateway(settings, {"one": first, "two": second})

    result = await gateway.generate("coder", "system", "user")

    assert "## one\nfirst result" in result
    assert "## failed_models" in result
    assert "- two: broken" in result


@pytest.mark.asyncio
async def test_generate_raises_when_all_parallel_calls_fail() -> None:
    settings = SettingsStub(
        provider_names=["one", "two"],
        agents={"coder": AgentStub(parallel_mode="parallel")},
    )
    gateway = ParallelLLMGateway(
        settings,
        {"one": ClientStub(RuntimeError("boom")), "two": ClientStub(RuntimeError("snap"))},
    )

    with pytest.raises(AllProvidersFailedError, match="All parallel model calls failed"):
        await gateway.generate("coder", "system", "user")


@pytest.mark.asyncio
async def test_generate_first_success_raises_when_all_providers_fail() -> None:
    """Lines 92-93: _generate_first_success all providers fail -> AllProvidersFailedError."""
    settings = SettingsStub(
        provider_names=["one", "two"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="first_success")},
    )
    gateway = ParallelLLMGateway(
        settings,
        {
            "one": ClientStub(RuntimeError("provider one failed")),
            "two": ClientStub(RuntimeError("provider two failed")),
        },
    )

    with pytest.raises(
        AllProvidersFailedError,
        match="All parallel model calls failed",
    ):
        await gateway.generate("coder", "system", "user")


@pytest.mark.asyncio
async def test_generate_first_success_treats_missing_result_as_failure() -> None:
    class NoneReturningClientStub:
        async def generate(self, system_prompt: str, user_prompt: str) -> str:
            return None  # type: ignore[return-value]

    settings = SettingsStub(
        provider_names=["none", "working"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="first_success")},
    )
    gateway = ParallelLLMGateway(
        settings,
        {"none": NoneReturningClientStub(), "working": ClientStub("fallback")},
    )

    result = await gateway.generate("coder", "system", "user")

    assert result == "fallback"


@pytest.mark.asyncio
async def test_generate_from_provider_raises_on_non_str_result() -> None:
    """The gateway should reject non-str return values from provider clients."""
    non_str = NonStrClientStub(42)  # int, not str
    working = ClientStub("ok")
    settings = SettingsStub(
        provider_names=["bad", "good"],
        agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="first_success")},
    )
    gateway = ParallelLLMGateway(settings, {"bad": non_str, "good": working})

    result = await gateway.generate("coder", "system", "user")

    # first_success strategy: "bad" returns int (non-str), should be treated as failure
    # "good" should succeed and be returned
    assert result == "ok"


# ── Retry / backoff tests ─────────────────────────────────────────────


class TestRetryableClassification:
    """_is_retryable -- edge cases and contract."""

    def test_cancelled_error_not_retryable(self) -> None:
        assert _is_retryable(asyncio.CancelledError()) is False

    def test_provider_response_error_not_retryable(self) -> None:
        assert _is_retryable(ProviderResponseError("bad schema")) is False

    def test_all_providers_failed_not_retryable(self) -> None:
        assert _is_retryable(AllProvidersFailedError("all dead")) is False

    def test_httpx_429_is_retryable(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        exc = httpx.HTTPStatusError("rate limit", request=MagicMock(), response=response)
        assert _is_retryable(exc) is True

    def test_httpx_500_is_retryable(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        exc = httpx.HTTPStatusError("internal", request=MagicMock(), response=response)
        assert _is_retryable(exc) is True

    def test_httpx_502_is_retryable(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 502
        exc = httpx.HTTPStatusError("bad gateway", request=MagicMock(), response=response)
        assert _is_retryable(exc) is True

    def test_httpx_503_is_retryable(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 503
        exc = httpx.HTTPStatusError("unavailable", request=MagicMock(), response=response)
        assert _is_retryable(exc) is True

    def test_httpx_400_not_retryable(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        exc = httpx.HTTPStatusError("bad request", request=MagicMock(), response=response)
        assert _is_retryable(exc) is False

    def test_httpx_401_not_retryable(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 401
        exc = httpx.HTTPStatusError("unauthorized", request=MagicMock(), response=response)
        assert _is_retryable(exc) is False

    def test_connect_error_is_retryable(self) -> None:
        exc = httpx.ConnectError("DNS failed")
        assert _is_retryable(exc) is True

    def test_timeout_is_retryable(self) -> None:
        exc = httpx.TimeoutException("timed out")
        assert _is_retryable(exc) is True

    def test_ioerror_is_retryable(self) -> None:
        assert _is_retryable(IOError("disk full")) is True

    def test_runtime_error_not_retryable(self) -> None:
        # Bare RuntimeError is not a recognized transient error
        assert _is_retryable(RuntimeError("unexpected")) is False


class TestFullJitterDelay:
    """_full_jitter_delay -- distribution and bounds."""

    def test_zero_delay_for_first_attempt(self) -> None:
        delay = _full_jitter_delay(0, base_delay_seconds=2.0, max_delay_seconds=60.0)
        assert 0 <= delay <= min(60.0, 2.0 * 1)  # base * 2^0 = 2.0

    def test_delay_increases_exponentially_no_cap(self) -> None:
        """Attempt 5 with base=1 and max=1000: cap = min(1000, 32) = 32."""
        delays = [
            _full_jitter_delay(5, base_delay_seconds=1.0, max_delay_seconds=1000)
            for _ in range(100)
        ]
        for d in delays:
            assert 0 <= d <= 32.0

    def test_delay_respects_max_cap(self) -> None:
        """Attempt 10 with base=1 and max=10: cap = min(10, 1024) = 10."""
        delays = [
            _full_jitter_delay(10, base_delay_seconds=1.0, max_delay_seconds=10.0)
            for _ in range(100)
        ]
        for d in delays:
            assert 0 <= d <= 10.0

    def test_near_zero_base_delay(self) -> None:
        delay = _full_jitter_delay(0, base_delay_seconds=0.001, max_delay_seconds=1.0)
        assert 0 <= delay <= 0.1

    def test_randomness(self) -> None:
        """Verify we get varying delays (not all the same)."""
        delays = {
            _full_jitter_delay(3, base_delay_seconds=10.0, max_delay_seconds=60.0)
            for _ in range(50)
        }
        assert len(delays) > 5, f"Expected variety in jitter, got {len(delays)} unique values"


class TestRetryBudget:
    """_RetryBudget -- sliding-window circuit breaker."""

    def test_can_retry_when_under_budget(self) -> None:
        budget = _RetryBudget(window_seconds=60, max_retries=5)
        assert budget.can_retry() is True

    def test_cannot_retry_when_over_budget(self) -> None:
        budget = _RetryBudget(window_seconds=60, max_retries=3)
        for _ in range(3):
            budget.record()
        assert budget.can_retry() is False

    def test_can_retry_after_budget_window_expires(self) -> None:
        budget = _RetryBudget(window_seconds=60, max_retries=2)
        budget.record()
        budget.record()
        assert budget.can_retry() is False

        # Fast-forward timestamps by patching
        now = time_module.monotonic()
        budget._timestamps = [now - 120, now - 90]
        assert budget.can_retry() is True

    def test_retry_count_reflects_active_retries(self) -> None:
        budget = _RetryBudget(window_seconds=60, max_retries=10)
        assert budget.retry_count == 0
        budget.record()
        assert budget.retry_count == 1
        budget.record()
        assert budget.retry_count == 2

    def test_record_does_not_exceed_max_retries(self) -> None:
        budget = _RetryBudget(window_seconds=60, max_retries=2)
        budget.record()
        budget.record()
        budget.record()  # third record pushes past max
        assert budget.can_retry() is False


class TestWithRetry:
    """with_retry -- end-to-end retry behaviour."""

    @pytest.mark.asyncio
    async def test_success_first_attempt(self) -> None:
        cfg = RetryConfig(max_retries=3, base_delay_seconds=0.001)

        async def ok() -> str:
            return "hello"

        result = await with_retry(ok, cfg)
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_retry_then_succeed(self) -> None:
        cfg = RetryConfig(max_retries=3, base_delay_seconds=0.001)
        call_count = 0

        async def fail_then_ok() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("timeout")
            return "success"

        result = await with_retry(fail_then_ok, cfg)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhaust_retries_raises_last_exception(self) -> None:
        cfg = RetryConfig(max_retries=2, base_delay_seconds=0.001)
        budget = _RetryBudget(window_seconds=60, max_retries=10)

        async def always_fail() -> str:
            raise httpx.TimeoutException("always timeout")

        with pytest.raises(AllProvidersFailedError, match="retry attempts exhausted"):
            await with_retry(always_fail, cfg, _budget_override=budget)

    @pytest.mark.asyncio
    async def test_cancelled_error_does_not_retry(self) -> None:
        cfg = RetryConfig(max_retries=3, base_delay_seconds=0.001)

        async def cancelled() -> str:
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await with_retry(cancelled, cfg)

    @pytest.mark.asyncio
    async def test_provider_response_error_does_not_retry(self) -> None:
        cfg = RetryConfig(max_retries=3, base_delay_seconds=0.001)

        async def bad_response() -> str:
            raise ProviderResponseError("bad data")

        with pytest.raises(ProviderResponseError, match="bad data"):
            await with_retry(bad_response, cfg)

    @pytest.mark.asyncio
    async def test_budget_exhausted_fails_fast(self) -> None:
        cfg = RetryConfig(max_retries=5, base_delay_seconds=0.001)
        budget = _RetryBudget(window_seconds=60, max_retries=2)
        budget.record()
        budget.record()  # budget is full

        async def fails() -> str:
            raise httpx.TimeoutException("nope")

        with pytest.raises(AllProvidersFailedError, match="budget exhausted"):
            await with_retry(fails, cfg, _budget_override=budget)

    @pytest.mark.asyncio
    async def test_rate_limit_429_retry_after_respected(self) -> None:
        """429 with Retry-After should delay and retry without consuming budget."""
        cfg = RetryConfig(max_retries=3, base_delay_seconds=0.001)
        budget = _RetryBudget(window_seconds=60, max_retries=10)
        call_count = 0

        response_429 = MagicMock(spec=httpx.Response)
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "0.005"}

        async def rate_limited_then_ok() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.HTTPStatusError(
                    "rate limited", request=MagicMock(), response=response_429
                )
            return "ok"

        start = time_module.monotonic()
        result = await with_retry(rate_limited_then_ok, cfg, _budget_override=budget)
        elapsed = time_module.monotonic() - start

        assert result == "ok"
        assert call_count == 2
        assert elapsed >= 0.005  # at least the Retry-After delay
        assert budget.retry_count == 0  # 429 does NOT consume budget

    def test_extract_retry_after_parses_http_date(self) -> None:
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        retry_after_at = datetime(2026, 1, 1, 12, 0, 10, tzinfo=timezone.utc)
        response.headers = {"Retry-After": retry_after_at.strftime("%a, %d %b %Y %H:%M:%S GMT")}
        exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=response)

        computed_delay = _extract_retry_after(
            exc,
            now=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )

        assert computed_delay == 10.0

    def test_extract_retry_after_non_http_error_returns_none(self) -> None:
        """Line 223: non-HTTPStatusError exc returns None."""
        exc = RuntimeError("not an HTTP error")
        assert _extract_retry_after(exc) is None

    def test_extract_retry_after_no_header_returns_none(self) -> None:
        """Line 226: HTTPStatusError without Retry-After header returns None."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        response.headers = {}
        exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=response)
        assert _extract_retry_after(exc) is None

    def test_extract_retry_after_unparseable_date_returns_none(self) -> None:
        """Lines 234-235: unparseable Retry-After date returns None."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        response.headers = {"Retry-After": "not-a-valid-date-at-all"}
        exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=response)
        assert _extract_retry_after(exc) is None

    def test_extract_retry_after_date_without_tzinfo(self) -> None:
        """Lines 237-242: Retry-After date without tzinfo is handled."""
        from email.utils import formatdate

        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        # Use formatdate (produces no tzinfo marker) to exercise tzinfo guards
        retry_after_ts = time_module.time() + 30
        response.headers = {"Retry-After": formatdate(retry_after_ts, usegmt=True)}
        exc = httpx.HTTPStatusError("rate limited", request=MagicMock(), response=response)

        computed_delay = _extract_retry_after(exc)
        # Should compute a positive delay (approximately 30 seconds)
        assert computed_delay is not None
        assert computed_delay >= 0.0

    @pytest.mark.asyncio
    async def test_retry_count_on_retryable_errors_increments_budget(self) -> None:
        cfg = RetryConfig(max_retries=3, base_delay_seconds=0.001)
        budget = _RetryBudget(window_seconds=60, max_retries=10)

        async def fail_twice_then_ok() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.TimeoutException("timeout")
            return "ok"

        call_count = 0
        result = await with_retry(fail_twice_then_ok, cfg, _budget_override=budget)
        assert result == "ok"
        # Two retries = 2 budget entries
        assert budget.retry_count == 2

    @pytest.mark.asyncio
    async def test_zero_retries_no_retry(self) -> None:
        cfg = RetryConfig(max_retries=0, base_delay_seconds=0.001)

        async def fails() -> str:
            raise httpx.TimeoutException("fail")

        with pytest.raises(AllProvidersFailedError, match="retry attempts exhausted"):
            await with_retry(fails, cfg)

    @pytest.mark.asyncio
    async def test_non_retryable_bare_runtime_error_no_retry(self) -> None:
        cfg = RetryConfig(max_retries=3, base_delay_seconds=0.001)
        call_count = 0

        async def fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("some internal bug")

        with pytest.raises(RuntimeError, match="some internal bug"):
            await with_retry(fails, cfg)
        assert call_count == 1  # no retry


# ── Integration-style: ParallelLLMGateway._generate_from_provider ─────


class TestParallelLLMGatewayWithRetry:
    """End-to-end tests of retry behaviour through the gateway."""

    @pytest.mark.asyncio
    async def test_generate_from_provider_prefers_provider_specific_retry_config(self) -> None:
        call_count = 0

        class FlakyClientStub:
            async def generate(self, system_prompt: str, user_prompt: str) -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise httpx.TimeoutException("transient timeout")
                return "provider-specific"

        settings = SettingsStub(
            provider_names=["p1"],
            agents={"coder": AgentStub(parallel_mode="single")},
            providers={
                "p1": SimpleNamespace(retry=RetryConfig(max_retries=2, base_delay_seconds=0.001))
            },
        )
        settings.runtime = SimpleNamespace(
            llm_retry=RetryConfig(max_retries=0, base_delay_seconds=0.001),
        )

        gateway = ParallelLLMGateway(settings, {"p1": FlakyClientStub()})

        result = await gateway.generate("coder", "system", "user")

        assert result == "provider-specific"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_generate_from_provider_honors_legacy_retry_alias(self) -> None:
        """The gateway should still honor runtime.retry for older configs."""
        call_count = 0

        class FlakyClientStub:
            async def generate(self, system_prompt: str, user_prompt: str) -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise httpx.TimeoutException("transient timeout")
                return "recovered"

        settings = SettingsStub(
            provider_names=["p1"],
            agents={"coder": AgentStub(parallel_mode="single")},
        )
        settings.runtime = SimpleNamespace(
            retry=RetryConfig(max_retries=5, base_delay_seconds=0.001),
        )

        gateway = ParallelLLMGateway(settings, {"p1": FlakyClientStub()})

        result = await gateway.generate("coder", "system", "user")

        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_generate_from_provider_retries_on_retryable_error(self) -> None:
        """_generate_from_provider should retry on transient errors (via parallel sectioned mode)."""
        call_count = 0

        class RetryableClientStub:
            async def generate(self, system_prompt: str, user_prompt: str) -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise httpx.TimeoutException("transient timeout")
                return "recovered"

        settings = SettingsStub(
            provider_names=["p1", "p2"],
            agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="sectioned")},
        )
        from mergemate.config.models import RuntimeConfig

        settings.runtime = RuntimeConfig(
            llm_retry=RetryConfig(max_retries=5, base_delay_seconds=0.001),
        )

        steady = ClientStub("steady")
        gateway = ParallelLLMGateway(settings, {"p1": RetryableClientStub(), "p2": steady})
        result = await gateway.generate("coder", "system", "user")
        assert "## p1\nrecovered" in result
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_generate_from_provider_fails_fast_on_non_retryable(self) -> None:
        """_generate_from_provider should NOT retry on non-retryable errors (via parallel sectioned mode)."""
        call_count = 0

        class NonRetryableClientStub:
            async def generate(self, system_prompt: str, user_prompt: str) -> str:
                nonlocal call_count
                call_count += 1
                raise ProviderResponseError("malformed response")

        settings = SettingsStub(
            provider_names=["p1", "p2"],
            agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="sectioned")},
        )
        from mergemate.config.models import RuntimeConfig

        settings.runtime = RuntimeConfig(
            llm_retry=RetryConfig(max_retries=5, base_delay_seconds=0.001),
        )

        gateway = ParallelLLMGateway(
            settings,
            {"p1": NonRetryableClientStub(), "p2": ClientStub("backup")},
        )
        result = await gateway.generate("coder", "system", "user")
        # "p1" raises ProviderResponseError (non-retryable, only called once)
        # "p2" succeeds normally
        assert "## p2\nbackup" in result
        assert call_count == 1  # no retry

    @pytest.mark.asyncio
    async def test_parallel_retry_continues_across_providers(self) -> None:
        """In parallel sectioned mode, failures with retries don't block other providers."""

        class FlakyClient:
            def __init__(self, fail_count: int) -> None:
                self.calls = 0
                self._fail_count = fail_count

            async def generate(self, system_prompt: str, user_prompt: str) -> str:
                self.calls += 1
                if self.calls <= self._fail_count:
                    raise httpx.TimeoutException("flaky")
                return "ok"

        settings = SettingsStub(
            provider_names=["p1", "p2"],
            agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="sectioned")},
        )
        from mergemate.config.models import RuntimeConfig

        settings.runtime = RuntimeConfig(
            llm_retry=RetryConfig(max_retries=3, base_delay_seconds=0.001),
        )

        flaky = FlakyClient(fail_count=2)
        steady = ClientStub("steady_result")
        gateway = ParallelLLMGateway(settings, {"p1": flaky, "p2": steady})

        result = await gateway.generate("coder", "system", "user")
        assert "## p1\nok" in result
        assert "## p2\nsteady_result" in result

    @pytest.mark.asyncio
    async def test_generate_non_str_result_does_not_retry(self) -> None:
        """A non-str result raises ProviderResponseError which is non-retryable (no retry)."""
        call_count = 0

        class IntClientStub:
            async def generate(self, system_prompt: str, user_prompt: str) -> str:
                nonlocal call_count
                call_count += 1
                return 42  # type: ignore[return-value]

        settings = SettingsStub(
            provider_names=["p1", "p2"],
            agents={"coder": AgentStub(parallel_mode="parallel", combine_strategy="sectioned")},
        )
        from mergemate.config.models import RuntimeConfig

        settings.runtime = RuntimeConfig(
            llm_retry=RetryConfig(max_retries=3, base_delay_seconds=0.001),
        )

        gateway = ParallelLLMGateway(
            settings,
            {"p1": IntClientStub(), "p2": ClientStub("fallback")},
        )
        result = await gateway.generate("coder", "system", "user")
        # IntClientStub returns non-str -> ProviderResponseError (no retry)
        # fallback client succeeds
        assert "## p2\nfallback" in result
        assert call_count == 1
