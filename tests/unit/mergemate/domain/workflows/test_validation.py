"""Tests for workflow validation hooks — registration, query, and execution."""

from __future__ import annotations

import pytest

from mergemate.domain.workflows.validation import (
    _VALIDATION_HOOKS,
    get_validation_hooks,
    register_validation_hook,
    run_validation_hooks,
)


@pytest.fixture(autouse=True)
def _clear_hooks() -> None:
    """Clear the global hook registry before each test to prevent cross-test pollution."""
    _VALIDATION_HOOKS.clear()


# ── register_validation_hook ────────────────────────────────────────────


def test_register_validation_hook_stores_hook() -> None:
    """A registered hook is retrievable via get_validation_hooks."""

    async def my_hook(stage_name: str, artifacts: dict) -> bool:
        return True

    register_validation_hook("implementation", my_hook)
    hooks = get_validation_hooks("implementation")

    assert my_hook in hooks


def test_register_validation_hook_appends_multiple_hooks() -> None:
    """Multiple hooks for the same key are stored in registration order."""

    async def hook_a(stage_name: str, artifacts: dict) -> bool:
        return True

    async def hook_b(stage_name: str, artifacts: dict) -> bool:
        return True

    register_validation_hook("testing", hook_a)
    register_validation_hook("testing", hook_b)

    hooks = get_validation_hooks("testing")
    assert hooks == [hook_a, hook_b]


def test_register_validation_hook_preserves_hooks_across_keys() -> None:
    """Hooks registered under different keys are independent."""

    async def design_hook(stage_name: str, artifacts: dict) -> bool:
        return True

    async def review_hook(stage_name: str, artifacts: dict) -> bool:
        return True

    register_validation_hook("design", design_hook)
    register_validation_hook("review", review_hook)

    design_hooks = get_validation_hooks("design")
    review_hooks = get_validation_hooks("review")

    assert design_hooks == [design_hook]
    assert review_hooks == [review_hook]
    assert design_hooks != review_hooks


# ── get_validation_hooks ────────────────────────────────────────────────


def test_get_validation_hooks_returns_empty_list_for_unknown_key() -> None:
    """An unregistered handler key returns an empty list, not an error."""
    hooks = get_validation_hooks("nonexistent_stage")

    assert hooks == []


def test_get_validation_hooks_returns_copy_not_reference() -> None:
    """Returned list is a copy; mutating it does not affect the registry."""

    async def hook(stage_name: str, artifacts: dict) -> bool:
        return True

    register_validation_hook("design", hook)

    retrieved = get_validation_hooks("design")
    retrieved.clear()

    hooks_after = get_validation_hooks("design")
    assert hook in hooks_after


# ── run_validation_hooks ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_validation_hooks_returns_true_when_no_hooks() -> None:
    """No hooks registered for a key returns True (vacuously)."""
    result = await run_validation_hooks("unregistered_key", "stage1", {})

    assert result is True


@pytest.mark.asyncio
async def test_run_validation_hooks_passes_stage_name_and_artifacts() -> None:
    """Hooks receive the stage_name and artifacts dict."""

    captured: list[tuple[str, dict]] = []

    async def capturing_hook(stage_name: str, artifacts: dict) -> bool:
        captured.append((stage_name, dict(artifacts)))
        return True

    register_validation_hook("design", capturing_hook)

    await run_validation_hooks("design", "analysis", {"key": "val"})

    assert captured == [("analysis", {"key": "val"})]


@pytest.mark.asyncio
async def test_run_validation_hooks_returns_true_when_all_pass() -> None:
    """When all hooks return True, run_validation_hooks returns True."""

    async def always_ok(stage_name: str, artifacts: dict) -> bool:
        return True

    register_validation_hook("deploy", always_ok)

    result = await run_validation_hooks("deploy", "deployment", {})
    assert result is True


@pytest.mark.asyncio
async def test_run_validation_hooks_stops_on_first_failure() -> None:
    """If a hook returns False, subsequent hooks are not called."""

    call_order: list[str] = []

    async def first_fail(stage_name: str, artifacts: dict) -> bool:
        call_order.append("first")
        return False

    async def never_called(stage_name: str, artifacts: dict) -> bool:
        call_order.append("should_not_run")
        return True

    register_validation_hook("review", first_fail)
    register_validation_hook("review", never_called)

    result = await run_validation_hooks("review", "code_review", {})

    assert result is False
    assert call_order == ["first"]


@pytest.mark.asyncio
async def test_run_validation_hooks_all_hooks_run_in_order_when_all_pass() -> None:
    """All hooks run in registration order when all return True."""

    call_order: list[str] = []

    async def hook_a(stage_name: str, artifacts: dict) -> bool:
        call_order.append("a")
        return True

    async def hook_b(stage_name: str, artifacts: dict) -> bool:
        call_order.append("b")
        return True

    async def hook_c(stage_name: str, artifacts: dict) -> bool:
        call_order.append("c")
        return True

    register_validation_hook("full", hook_a)
    register_validation_hook("full", hook_b)
    register_validation_hook("full", hook_c)

    result = await run_validation_hooks("full", "pipeline", {})

    assert result is True
    assert call_order == ["a", "b", "c"]