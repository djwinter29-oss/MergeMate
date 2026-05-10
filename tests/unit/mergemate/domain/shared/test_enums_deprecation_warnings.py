"""Tests for deprecation warnings emitted by shared enums constants.

Tests verify that importing ``src/mergemate/domain/shared/enums.py``
emits ``DeprecationWarning`` for both ``MULTI_STAGE_WORKFLOWS`` and
``PROMPT_FILE_BY_WORKFLOW``, while preserving backward-compatible values.
"""

from __future__ import annotations

import importlib
import sys
import warnings
from unittest.mock import patch

import pytest

MODULE_NAME = "mergemate.domain.shared.enums"

# Expected reference values stored before import-time deprecation warnings re-fire.
# We patch importlib.metadata.version so the package's __init__.py works.
@pytest.fixture(autouse=True)
def _patch_metadata():
    with patch("importlib.metadata.version", return_value="0.1.0"):
        yield


def import_fresh() -> object:
    """Import the enums module afresh so import-time warnings re-fire.

    Only pops ``mergemate.domain.shared.enums`` from ``sys.modules`` to
    avoid invalidating other cached modules (e.g. soul, workflows).
    """
    sys.modules.pop(MODULE_NAME, None)
    sys.modules.pop("mergemate.domain.shared", None)
    with patch("importlib.metadata.version", return_value="0.1.0"):
        return importlib.import_module(MODULE_NAME)


class TestMULTI_STAGE_WORKFLOWS_DeprecationWarning:
    """DeprecationWarning on MULTI_STAGE_WORKFLOWS."""

    def test_warns_on_import(self) -> None:
        with pytest.warns(
            DeprecationWarning,
            match="MULTI_STAGE_WORKFLOWS is deprecated",
        ):
            import_fresh()

    def test_captured_warning_message(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            import_fresh()

        messages = [str(w.message) for w in caught]
        assert any("MULTI_STAGE_WORKFLOWS" in m for m in messages)
        assert any("uses_multi_stage_delivery()" in m for m in messages)

    def test_backward_compatible_value_preserved(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always", DeprecationWarning)
            module = import_fresh()

        assert module.MULTI_STAGE_WORKFLOWS == frozenset(
            {module.WorkflowName.GENERATE_CODE}
        )
        assert isinstance(module.MULTI_STAGE_WORKFLOWS, frozenset)


class TestPROMPT_FILE_BY_WORKFLOW_DeprecationWarning:
    """DeprecationWarning on PROMPT_FILE_BY_WORKFLOW."""

    def test_warns_on_import(self) -> None:
        with pytest.warns(
            DeprecationWarning,
            match="PROMPT_FILE_BY_WORKFLOW is deprecated",
        ):
            import_fresh()

    def test_captured_warning_message(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            import_fresh()

        messages = [str(w.message) for w in caught]
        assert any("PROMPT_FILE_BY_WORKFLOW" in m for m in messages)
        assert any("resolve_prompt_file()" in m for m in messages)

    def test_backward_compatible_value_preserved(self) -> None:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always", DeprecationWarning)
            module = import_fresh()

        assert module.PROMPT_FILE_BY_WORKFLOW == {
            module.WorkflowName.GENERATE_CODE: "code_generation.md",
            module.WorkflowName.DEBUG_CODE: "debugging.md",
            module.WorkflowName.EXPLAIN_CODE: "explanation.md",
        }
        assert isinstance(module.PROMPT_FILE_BY_WORKFLOW, dict)