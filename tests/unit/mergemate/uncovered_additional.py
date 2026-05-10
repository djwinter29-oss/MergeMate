"""Additional coverage tests for remaining uncovered lines.

Covers:
1. gateway.py lines 92-93: _generate_first_success when all providers fail
2. handlers.py lines 217-229: direct execution handler path
3. bot.py lines 32, 59: readiness_state handling
4. health.py lines 55, 68: start/stoop early returns
5. progress_notifier.py lines 18-20: CANCELLED format path
"""
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, MagicMock

import pytest

from mergemate.domain.shared import RunStatus
from mergemate.domain.shared.exceptions import AllProvidersFailedError


# ── gateway.py: lines 92-93 ──────────────────────────────────────────

class TestGatewayAllProvidersFailed:
    """Cover _generate_first_success all-failures path (lines 92-93)."""

    @pytest.mark.asyncio
    async def test_generate_raises_when_all_providers_fail_first_success(self) -> None:
        """Lines 92-93: all providers fail -> AllProvidersFailedError."""
        from mergemate.infrastructure.llm.gateway import ParallelLLMGateway

        provider = AsyncMock(spec=["generate"])
        provider.generate.side_effect = RuntimeError("provider error")

        agent = SimpleNamespace(
            parallel_mode="parallel",
            combine_strategy="first_success",
        )
        settings = SimpleNamespace(
            agents={"agent": agent},
            resolve_agent_provider_names=lambda _: ["p1", "p2"],
        )

        gateway = ParallelLLMGateway(
            settings=settings,
            clients={"p1": provider, "p2": provider},
        )

        with pytest.raises(AllProvidersFailedError, match="All parallel model calls failed"):
            await gateway.generate("agent", "system", "user")


# ── handlers.py: lines 217-229 ───────────────────────────────────────

class TestDirectHandler:
    """Cover the direct execution handler path (lines 217-229)."""

    @pytest.mark.asyncio
    async def test_handle_direct_executes_and_persists(self) -> None:
        """Lines 217-229: direct handler runs execute_direct and persiss artifacts."""
        from mergemate.domain.workflows.handlers import _handle_direct

        runtime = SimpleNamespace(
            workflow_service=AsyncMock(
                execute_direct=AsyncMock(return_value="direct result"),
            ),
            run_repository=SimpleNamespace(
                save_artifacts=Mock(),
            ),
        )
        artifacts = {
            "run_id": "run-dir-1",
            "system_prompt": "sys",
            "context_text": "ctx",
            "plan_text": "plan",
        }

        result = await _handle_direct(runtime, artifacts, agent_name="test-agent")

        assert result["result_text"] == "direct result"
        assert result["_is_direct"] is True
        runtime.workflow_service.execute_direct.assert_called_once_with(
            "test-agent", "sys", "ctx",
        )


# ── bot.py: lines 32, 59 ─────────────────────────────────────────────

class TestBotReadiness:
    """Cover bot.py readiness_state handling (lines 32, 59)."""

    @pytest.mark.asyncio
    async def test_stop_runtime_tasks_mark_stopping(self) -> None:
        """Line 32: readiness_state.mark_stopping is called."""
        from mergemate.interfaces.telegram.bot import stop_runtime_tasks

        readiness_mock = Mock()
        application = SimpleNamespace(
            bot_data={
                "webhook_readiness_state": readiness_mock,
                "runtime": SimpleNamespace(
                    worker=Mock(stop=AsyncMock()),
                ),
            },
        )

        await stop_runtime_tasks(application)
        readiness_mock.mark_stopping.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_app_sets_webhook_readiness(self) -> None:
        """Line 59: webhook_readiness_state stored in bot_data."""
        from mergemate.interfaces.telegram.bot import TelegramBotRuntime

        runtime = MagicMock()
        runtime.settings.resolve_telegram_token.return_value = "test:token"
        runtime.settings.agents = {}

        bot = TelegramBotRuntime(runtime=runtime)

        app = bot.build_application(readiness_state="fake_state")
        assert "webhook_readiness_state" in app.bot_data
        assert app.bot_data["webhook_readiness_state"] == "fake_state"


# ── health.py: lines 55, 68 ──────────────────────────────────────────

class TestHealthServer:
    """Cover WebhookHealthServer.start/stoop early returns (lines 55, 68)."""

    def test_start_returns_early_when_already_started(self) -> None:
        """Line 55: start() returns early if _server is not None."""
        from mergemate.interfaces.telegram.health import WebhookHealthServer

        server = WebhookHealthServer(
            listen_host="127.0.0.1",
            listen_port=0,
            path="/health",
            state=MagicMock(),
        )
        server._server = "pretend server"  # simulate already started

        result = server.start()
        assert result is None

    def test_stop_returns_early_when_not_started(self) -> None:
        """Line 68: stop() returns early if _server is None."""
        from mergemate.interfaces.telegram.health import WebhookHealthServer

        server = WebhookHealthServer(
            listen_host="127.0.0.1",
            listen_port=0,
            path="/health",
            state=MagicMock(),
        )

        result = server.stop()
        assert result is None


# ── progress_notifier.py: lines 18-20 ────────────────────────────────

class TestProgressNotifierFormat:
    """Cover _format_terminal_update branches (lines 18-20)."""

    def test_format_completion(self) -> None:
        """Line 17: COMPLETED -> format_completion."""
        from mergemate.interfaces.telegram.progress_notifier import _format_terminal_update

        run = SimpleNamespace(run_id="run-1", status=RunStatus.COMPLETED, result_text="success!")
        result = _format_terminal_update(run)
        assert isinstance(result, str)

    def test_format_cancelled(self) -> None:
        """Line 18-19: CANCELLED -> format_cancelled."""
        from mergemate.interfaces.telegram.progress_notifier import _format_terminal_update

        run = SimpleNamespace(run_id="run-2", status=RunStatus.CANCELLED)
        result = _format_terminal_update(run)
        assert isinstance(result, str)

    def test_format_failure(self) -> None:
        """Line 20: other status -> format_failure."""
        from mergemate.interfaces.telegram.progress_notifier import _format_terminal_update

        run = SimpleNamespace(run_id="run-3", status=RunStatus.FAILED, error_text="it broke")
        result = _format_terminal_update(run)
        assert isinstance(result, str)