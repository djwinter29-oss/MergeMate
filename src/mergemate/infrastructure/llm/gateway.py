"""Gateway for single-model and parallel multi-model execution.

Retry/backoff lives here per architecture decision: the gateway layer
wraps ``_generate_from_provider`` with exponential full-jitter retry,
a sliding-window retry budget (soft circuit breaker), and rate-limit
awareness (429/Retry-After header values, including HTTP-date formats,
don't consume the budget).
"""

import asyncio
import random
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from mergemate.config.models import RetryConfig
from mergemate.domain.shared.exceptions import (
    AllProvidersFailedError,
    ProviderResponseError,
)
from mergemate.infrastructure.llm.base import LLMClient


# ── Retryable / non-retryable exception classification ────────────────


def _is_retryable(exc: BaseException) -> bool:
    """Return ``True`` for transient errors that merit a retry.

    Retryable:
    - HTTP 5xx, connection errors, timeouts (``httpx.HTTPStatusError``
      with status >= 500, ``httpx.ConnectError``, ``httpx.TimeoutException``)
    - Rate-limit 429 responses (``httpx.HTTPStatusError`` with status 429)
    - Any other ``IOError`` or ``OSError`` subclass.

    Non-retryable:
    - ``asyncio.CancelledError`` (task was intentionally cancelled)
    - ``ProviderResponseError`` (parse / schema errors -- the response
      was received but malformed; retrying won't change that)
    - ``AllProvidersFailedError`` (already exhausted all options)
    """
    from httpx import (
        ConnectError,
        HTTPStatusError,
        RemoteProtocolError,
        TimeoutException,
        TransportError,
    )

    if isinstance(exc, asyncio.CancelledError):
        return False
    if isinstance(exc, ProviderResponseError):
        return False
    if isinstance(exc, AllProvidersFailedError):
        return False
    if isinstance(exc, HTTPStatusError):
        # 429 is retryable (rate limit) but handled specially by the
        # caller so we mark it retryable here.
        return exc.response.status_code in (429,) or exc.response.status_code >= 500
    if isinstance(exc, (ConnectError, TimeoutException, RemoteProtocolError, TransportError)):
        return True
    if isinstance(exc, (IOError, OSError)):
        return True
    # Anything else -- treat as non-retryable to be safe.
    return False


# ── Sliding-window retry budget (soft circuit breaker) ────────────────


class _RetryBudget:
    """Sliding-window counter of retries across all providers.

    If the number of retries in the last ``window_seconds`` exceeds
    ``max_retries`` the budget is *exhausted* and further retry attempts
    are skipped.  429 (rate-limit) retries do **not** consume budget.

    Thread-safe for asyncio usage (single event loop -- no locks needed).
    """

    __slots__ = ("_window_seconds", "_max_retries", "_timestamps")

    def __init__(self, window_seconds: int, max_retries: int) -> None:
        self._window_seconds = window_seconds
        self._max_retries = max_retries
        self._timestamps: list[float] = []

    def _sweep(self, now: float) -> None:
        cutoff = now - self._window_seconds
        # Pop old entries from the front -- list is maintained in FIFO order.
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.pop(0)

    def can_retry(self) -> bool:
        now = time.monotonic()
        self._sweep(now)
        return len(self._timestamps) < self._max_retries

    def record(self) -> None:
        self._timestamps.append(time.monotonic())

    @property
    def retry_count(self) -> int:
        self._sweep(time.monotonic())
        return len(self._timestamps)


# ── Singleton budget (global -- not per-provider) ─────────────────────


_budget: _RetryBudget | None = None


def _reset_budget_for_testing() -> None:
    """Reset the global budget singleton (test hook only)."""
    global _budget
    _budget = None


def _get_budget(cfg: RetryConfig) -> _RetryBudget:
    global _budget
    if _budget is None:
        _budget = _RetryBudget(
            window_seconds=cfg.budget_window_seconds,
            max_retries=cfg.budget_max_retries,
        )
    return _budget


# ── Full-jitter delay calculation ─────────────────────────────────────


def _full_jitter_delay(
    attempt: int,
    *,
    base_delay_seconds: float,
    max_delay_seconds: float,
) -> float:
    """Compute the sleep duration for the *attempt*-th retry (0-based).

    ``sleep = random.uniform(0, min(max_delay, base_delay * 2 ** attempt))``

    The full-jitter strategy prevents thundering herds when multiple
    clients retry simultaneously.
    """
    cap = min(max_delay_seconds, base_delay_seconds * (2**attempt))
    return random.uniform(0, cap)


# ── Retry wrapper ─────────────────────────────────────────────────────


async def with_retry(
    fn: Callable[[], Any],
    cfg: RetryConfig,
    *,
    _budget_override: _RetryBudget | None = None,
) -> str:
    """Execute ``fn`` with exponential full-jitter retry and budget.

    ``fn`` must be a zero-argument async callable returning ``str``.

    Raises the *last* exception if all retries are exhausted.
    ``asyncio.CancelledError`` and ``ProviderResponseError`` are re-raised
    immediately without retrying.
    """
    budget = _budget_override if _budget_override is not None else _get_budget(cfg)
    last_exc: BaseException | None = None

    for attempt in range(cfg.max_retries + 1):
        try:
            return await fn()
        except BaseException as exc:
            last_exc = exc

            if not _is_retryable(last_exc):
                raise

            if attempt >= cfg.max_retries:
                raise AllProvidersFailedError("All retry attempts exhausted.") from last_exc

            # --- Rate-limit (429) handling ---
            if _is_rate_limit(last_exc):
                retry_after = _extract_retry_after(last_exc)
                if retry_after is not None:
                    await asyncio.sleep(retry_after)
                    # 429 does NOT consume budget
                    continue

            # --- Budget check (soft circuit breaker) ---
            if not budget.can_retry():
                # Budget exhausted -- fail fast instead of wasting time.
                raise AllProvidersFailedError("Retry budget exhausted \u2014 circuit breaker open")

            budget.record()

            delay = _full_jitter_delay(
                attempt,
                base_delay_seconds=cfg.base_delay_seconds,
                max_delay_seconds=cfg.max_delay_seconds,
            )
            await asyncio.sleep(delay)

    raise AllProvidersFailedError("All retry attempts exhausted.")


def _is_rate_limit(exc: BaseException) -> bool:
    from httpx import HTTPStatusError

    return isinstance(exc, HTTPStatusError) and exc.response.status_code == 429


def _extract_retry_after(
    exc: BaseException,
    *,
    now: datetime | None = None,
) -> float | None:
    from httpx import HTTPStatusError

    if not isinstance(exc, HTTPStatusError):
        return None
    header = exc.response.headers.get("Retry-After")
    if header is None:
        return None
    try:
        return max(0.0, float(header))
    except (ValueError, TypeError):
        pass

    try:
        retry_after_at = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if retry_after_at is None:
        return None
    if retry_after_at.tzinfo is None:
        retry_after_at = retry_after_at.replace(tzinfo=timezone.utc)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_after_at - current_time).total_seconds())


# ── Gateway class ─────────────────────────────────────────────────────


class ParallelLLMGateway:
    _settings: Any
    _clients: Mapping[str, LLMClient]

    def __init__(self, settings: Any, clients: Mapping[str, LLMClient]) -> None:
        self._settings = settings
        self._clients = clients

    def _resolve_provider_names(self, agent_name: str) -> tuple[list[str], list[str]]:
        provider_names = list(dict.fromkeys(self._settings.resolve_agent_provider_names(agent_name)))
        available_names = [name for name in provider_names if name in self._clients]
        missing_names = [name for name in provider_names if name not in self._clients]
        return available_names, missing_names

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        available_names, missing_names = self._resolve_provider_names(agent_name)
        if not available_names:
            configured_names = ", ".join(self._settings.resolve_agent_provider_names(agent_name))
            missing_text = ", ".join(missing_names) if missing_names else "none"
            raise AllProvidersFailedError(
                f"No configured providers are available for agent {agent_name}. "
                f"Configured providers: {configured_names}. Missing clients: {missing_text}."
            )

        agent = self._settings.agents.get(agent_name)
        parallel_mode = agent.parallel_mode if agent is not None else "single"
        combine_strategy = agent.combine_strategy if agent is not None else "sectioned"

        if parallel_mode != "parallel" or len(available_names) == 1:
            return await self._generate_from_provider(available_names[0], system_prompt, user_prompt)

        if combine_strategy == "first_success":
            return await self._generate_first_success(available_names, system_prompt, user_prompt)

        tasks = [
            self._generate_from_provider(name, system_prompt, user_prompt)
            for name in available_names
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_results: list[tuple[str, str]] = []
        failures: list[tuple[str, str]] = []
        for provider_name, result in zip(available_names, raw_results, strict=True):
            if isinstance(result, BaseException):
                failures.append((provider_name, str(result)))
                continue
            successful_results.append((provider_name, result))

        if not successful_results:
            failure_detail = "; ".join(f"{name}: {detail}" for name, detail in failures)
            raise AllProvidersFailedError(f"All parallel model calls failed. {failure_detail}")

        return self._format_sectioned_results(successful_results, failures)

    async def _generate_first_success(
        self,
        provider_names: list[str],
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        tasks = [
            asyncio.create_task(
                self._generate_first_success_result(name, system_prompt, user_prompt)
            )
            for name in provider_names
        ]
        failures: list[tuple[str, str]] = []

        for completed_task in asyncio.as_completed(tasks):
            provider_name, result, error_detail = await completed_task
            if error_detail is not None:
                failures.append((provider_name, error_detail))
                continue

            assert result is not None

            # Cancel remaining tasks since we got a successful result
            for pending_task in tasks:
                if pending_task is not completed_task and not pending_task.done():
                    pending_task.cancel()
            # Wait for cancelled tasks to settle
            await asyncio.gather(*tasks, return_exceptions=True)
            return result

        failure_detail = "; ".join(f"{name}: {detail}" for name, detail in failures)
        raise AllProvidersFailedError(f"All parallel model calls failed. {failure_detail}")

    async def _generate_first_success_result(
        self,
        provider_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> tuple[str, str | None, str | None]:
        try:
            return (
                provider_name,
                await self._generate_from_provider(provider_name, system_prompt, user_prompt),
                None,
            )
        except Exception as exc:
            return provider_name, None, str(exc)

    async def _generate_from_provider(
        self,
        provider_name: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        retry_cfg: RetryConfig = getattr(getattr(self._settings, 'runtime', None), 'llm_retry', RetryConfig())

        async def _call() -> str:
            result = await self._clients[provider_name].generate(system_prompt, user_prompt)
            if not isinstance(result, str):
                raise ProviderResponseError("Provider returned a non-text result.")
            return result

        return await with_retry(_call, retry_cfg)

    @staticmethod
    def _format_sectioned_results(
        successful_results: list[tuple[str, str]],
        failures: list[tuple[str, str]],
    ) -> str:
        sections = []
        for provider_name, result_text in successful_results:
            sections.append(f"## {provider_name}\n{result_text.strip()}")
        if failures:
            failure_lines = [f"- {provider_name}: {detail}" for provider_name, detail in failures]
            sections.append("## failed_models\n" + "\n".join(failure_lines))
        return "\n\n".join(sections)