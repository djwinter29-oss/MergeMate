"""Tests for lazy deprecation warnings in shared enums constants.

The deprecated aliases remain backward-compatible, but import-time noise should
be avoided. The warning should appear only when the alias is actually accessed.
"""

from __future__ import annotations

import importlib
import sys
import warnings
from unittest.mock import patch

import pytest

MODULE_NAME = "mergemate.domain.shared.enums"
PACKAGE_NAME = "mergemate.domain.shared"


@pytest.fixture(autouse=True)
def _patch_metadata():
    with patch("importlib.metadata.version", return_value="0.1.0"):
        yield


def import_fresh() -> object:
    """Import the enums module afresh so lazy warnings can be observed cleanly."""

    sys.modules.pop(MODULE_NAME, None)
    sys.modules.pop(PACKAGE_NAME, None)
    with patch("importlib.metadata.version", return_value="0.1.0"):
        return importlib.import_module(MODULE_NAME)


class TestMULTI_STAGE_WORKFLOWS_DeprecationWarning:
    """DeprecationWarning on MULTI_STAGE_WORKFLOWS."""

    def test_module_import_is_quiet(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            module = import_fresh()

        assert caught == []
        assert module.WorkflowName.GENERATE_CODE.value == "generate_code"

    def test_warns_on_access_from_enums_module(self) -> None:
        module = import_fresh()

        with pytest.warns(
            DeprecationWarning,
            match="MULTI_STAGE_WORKFLOWS is deprecated",
        ):
            value = module.MULTI_STAGE_WORKFLOWS

        assert value == frozenset({module.WorkflowName.GENERATE_CODE})
        assert isinstance(value, frozenset)

    def test_warns_on_access_from_shared_package(self) -> None:
        import_fresh()
        shared_module = importlib.import_module(PACKAGE_NAME)

        with pytest.warns(
            DeprecationWarning,
            match="MULTI_STAGE_WORKFLOWS is deprecated",
        ):
            value = shared_module.MULTI_STAGE_WORKFLOWS

        assert value == frozenset({shared_module.WorkflowName.GENERATE_CODE})


class TestPROMPT_FILE_BY_WORKFLOW_DeprecationWarning:
    """DeprecationWarning on PROMPT_FILE_BY_WORKFLOW."""

    def test_module_import_is_quiet(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            module = import_fresh()

        assert caught == []
        assert module.WorkflowName.EXPLAIN_CODE.value == "explain_code"

    def test_warns_on_access_from_enums_module(self) -> None:
        module = import_fresh()

        with pytest.warns(
            DeprecationWarning,
            match="PROMPT_FILE_BY_WORKFLOW is deprecated",
        ):
            value = module.PROMPT_FILE_BY_WORKFLOW

        assert value == {
            module.WorkflowName.GENERATE_CODE: "code_generation.md",
            module.WorkflowName.DEBUG_CODE: "debugging.md",
            module.WorkflowName.EXPLAIN_CODE: "explanation.md",
        }
        assert isinstance(value, dict)

    def test_warns_on_access_from_shared_package(self) -> None:
        import_fresh()
        shared_module = importlib.import_module(PACKAGE_NAME)

        with pytest.warns(
            DeprecationWarning,
            match="PROMPT_FILE_BY_WORKFLOW is deprecated",
        ):
            value = shared_module.PROMPT_FILE_BY_WORKFLOW

        assert value == {
            shared_module.WorkflowName.GENERATE_CODE: "code_generation.md",
            shared_module.WorkflowName.DEBUG_CODE: "debugging.md",
            shared_module.WorkflowName.EXPLAIN_CODE: "explanation.md",
        }
