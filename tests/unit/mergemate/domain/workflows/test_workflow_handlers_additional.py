from __future__ import annotations

import warnings
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from mergemate.domain.workflows import handlers


@pytest.mark.asyncio
async def test_handle_direct_executes_and_persists_artifacts() -> None:
    runtime = SimpleNamespace(
        deps=SimpleNamespace(
            workflow_service=SimpleNamespace(
                execute_direct=AsyncMock(return_value="direct result"),
            ),
            run_repository=SimpleNamespace(
                save_artifacts=Mock(),
            ),
        ),
    )
    artifacts = {
        "run_id": "run-direct-1",
        "system_prompt": "system prompt",
        "context_text": "user context",
    }

    result = await handlers._handle_direct(runtime, artifacts, agent_name="direct-agent")

    assert result is artifacts
    assert result["result_text"] == "direct result"
    assert result["_is_direct"] is True
    runtime.deps.workflow_service.execute_direct.assert_awaited_once_with(
        "direct-agent",
        "system prompt",
        "user context",
    )
    runtime.deps.run_repository.save_artifacts.assert_called_once_with(
        "run-direct-1",
        current_stage="execution",
        result_text="direct result",
    )


def test_register_document_kind_warns_when_overwriting_existing_kind() -> None:
    original = handlers._DOCUMENT_KINDS["architecture"]

    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")

            @handlers.register_document_kind("architecture")
            def replacement_document_saver(*args, **kwargs):
                return None

        assert len(caught) == 1
        assert caught[0].category is UserWarning
        assert "already registered by" in str(caught[0].message)
        assert "overwriting with" in str(caught[0].message)
        assert handlers._DOCUMENT_KINDS["architecture"] is replacement_document_saver
    finally:
        handlers._DOCUMENT_KINDS["architecture"] = original
