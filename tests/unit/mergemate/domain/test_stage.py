"""Tests for WorkflowStage ordering and WorkflowName enum completeness."""

import warnings

import pytest

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from mergemate.domain.shared.enums import (
        MULTI_STAGE_WORKFLOWS,
        USER_FACING_WORKFLOWS,
        WorkflowName,
    )
from mergemate.domain.policies import (
    resolve_workflow_name,
)
from mergemate.domain.workflows.stage import (
    WorkflowDefinition,
    WorkflowStage,
    get_workflow_definitions,
)


# ── WorkflowStage construction ────────────────────────────────────────────


def test_workflow_stage_defaults() -> None:
    """WorkflowStage uses sensible defaults for optional fields."""
    stage = WorkflowStage(name="design", current_stage="design")

    assert stage.name == "design"
    assert stage.current_stage == "design"
    assert stage.handler == ""  # Not defaulted to name
    assert stage.prompt_template == ""
    assert stage.uses_tool_context is False
    assert stage.checks_cancellation_before is False
    assert stage.checks_cancellation_after is False
    assert stage.produces == ()


def test_workflow_stage_with_all_fields() -> None:
    """WorkflowStage accepts all optional fields."""
    stage = WorkflowStage(
        name="implementation",
        current_stage="implementation",
        handler="code_gen",
        prompt_template="coder_prompt.md",
        uses_tool_context=True,
        checks_cancellation_before=True,
        checks_cancellation_after=True,
        produces=("result_text",),
    )

    assert stage.name == "implementation"
    assert stage.current_stage == "implementation"
    assert stage.handler == "code_gen"
    assert stage.prompt_template == "coder_prompt.md"
    assert stage.uses_tool_context is True
    assert stage.checks_cancellation_before is True
    assert stage.checks_cancellation_after is True
    assert stage.produces == ("result_text",)


def test_workflow_stage_is_frozen_and_slots() -> None:
    """WorkflowStage is frozen=True, so fields cannot be mutated."""
    stage = WorkflowStage(name="test", current_stage="test")

    with pytest.raises(AttributeError):
        stage.name = "changed"  # type: ignore[misc]

    with pytest.raises(AttributeError):
        _ = stage.__dict__  # type: ignore[attr-defined]


def test_workflow_stage_supports_equality() -> None:
    """Two stages with same fields are equal (frozen dataclass)."""
    stage_a = WorkflowStage(name="review", current_stage="review")
    stage_b = WorkflowStage(name="review", current_stage="review")

    assert stage_a == stage_b
    assert hash(stage_a) == hash(stage_b)


def test_workflow_stage_inequality() -> None:
    """Stages with different fields are not equal."""
    a = WorkflowStage(name="design", current_stage="design")
    b = WorkflowStage(name="implementation", current_stage="implementation")

    assert a != b


# ── WorkflowDefinition construction ───────────────────────────────────────


def test_workflow_definition_construction() -> None:
    """WorkflowDefinition stores name and stages."""
    stages = (
        WorkflowStage(name="design", current_stage="design"),
        WorkflowStage(name="impl", current_stage="implementation"),
    )
    wf = WorkflowDefinition(name="generate_code", stages=stages)

    assert wf.name == "generate_code"
    assert len(wf.stages) == 2
    assert wf.stages[0].name == "design"
    assert wf.stages[1].name == "impl"


def test_workflow_definition_is_frozen_and_slots() -> None:
    """WorkflowDefinition is frozen=True, not mutable."""
    wf = WorkflowDefinition(
        name="test",
        stages=(WorkflowStage(name="s1", current_stage="s1"),),
    )

    with pytest.raises(AttributeError):
        wf.name = "changed"  # type: ignore[misc]


# ── Built-in workflow definitions ────────────────────────────────────────


def test_get_workflow_definitions_returns_expected() -> None:
    """get_workflow_definitions returns the built-in workflow definitions."""
    defs = get_workflow_definitions()
    names = set(defs.keys())

    assert WorkflowName.GENERATE_CODE in names
    assert WorkflowName.LEARNING in names


def test_generate_code_workflow_stage_order() -> None:
    """generate_code workflow stages are in expected order."""
    defs = get_workflow_definitions()
    wf = defs[WorkflowName.GENERATE_CODE]
    stage_names = [s.name for s in wf.stages]

    assert stage_names == [
        "design",
        "implementation",
        "testing",
        "review",
        "chronicle",
        "replanning",
    ]


def test_generate_code_stage_produces() -> None:
    """Each generate_code stage produces the expected artifact."""
    defs = get_workflow_definitions()
    wf = defs[WorkflowName.GENERATE_CODE]

    produces = {s.name: s.produces for s in wf.stages}
    assert produces["design"] == ("design_text",)
    assert produces["implementation"] == ("result_text",)
    assert produces["testing"] == ("test_text",)
    assert produces["review"] == ("review_text",)
    assert produces["chronicle"] == ("lesson_text",)
    assert produces["replanning"] == ()


def test_generate_code_checks_cancellation() -> None:
    """Design stage checks cancellation before and after; all stages check after."""
    defs = get_workflow_definitions()
    wf = defs[WorkflowName.GENERATE_CODE]

    for stage in wf.stages:
        if stage.name == "design":
            assert stage.checks_cancellation_before is True
        else:
            assert stage.checks_cancellation_before is False

        assert stage.checks_cancellation_after is True


def test_learning_workflow_stages() -> None:
    """learning workflow has a single chronicle stage."""
    defs = get_workflow_definitions()
    wf = defs[WorkflowName.LEARNING]
    stage_names = [s.name for s in wf.stages]

    assert stage_names == ["chronicle"]
    assert wf.stages[0].checks_cancellation_before is False
    assert wf.stages[0].checks_cancellation_after is False


# ── WorkflowName enum completeness ────────────────────────────────────────


def test_workflow_name_values() -> None:
    """WorkflowName enum values match expected strings."""
    assert WorkflowName.PLANNING.value == "planning"
    assert WorkflowName.DESIGN.value == "design"
    assert WorkflowName.GENERATE_CODE.value == "generate_code"
    assert WorkflowName.DEBUG_CODE.value == "debug_code"
    assert WorkflowName.EXPLAIN_CODE.value == "explain_code"
    assert WorkflowName.TESTING.value == "testing"
    assert WorkflowName.REVIEW.value == "review"
    assert WorkflowName.LEARNING.value == "learning"


def test_workflow_name_all_members() -> None:
    """WorkflowName enum covers all planned workflows."""
    expected = {
        "PLANNING",
        "DESIGN",
        "GENERATE_CODE",
        "DEBUG_CODE",
        "EXPLAIN_CODE",
        "TESTING",
        "REVIEW",
        "LEARNING",
    }
    actual = {m.name for m in WorkflowName}
    assert actual == expected


# ── Multi-stage workflow derivation ──────────────────────────────────────


def test_only_generate_code_is_multi_stage() -> None:
    """Only GENERATE_CODE is in MULTI_STAGE_WORKFLOWS."""
    assert MULTI_STAGE_WORKFLOWS == frozenset({WorkflowName.GENERATE_CODE})


def test_multi_stage_workflows_match_definitions() -> None:
    """Multi-stage workflows match the workflow definitions keys."""
    defs = get_workflow_definitions()
    assert set(defs.keys()) == MULTI_STAGE_WORKFLOWS.union({WorkflowName.LEARNING})


# ── User-facing workflow classification ──────────────────────────────────


def test_user_facing_workflows() -> None:
    """User-facing workflows are code generation, debugging, and explanation."""
    assert WorkflowName.GENERATE_CODE in USER_FACING_WORKFLOWS
    assert WorkflowName.DEBUG_CODE in USER_FACING_WORKFLOWS
    assert WorkflowName.EXPLAIN_CODE in USER_FACING_WORKFLOWS
    assert WorkflowName.PLANNING not in USER_FACING_WORKFLOWS
    assert WorkflowName.DESIGN not in USER_FACING_WORKFLOWS
    assert WorkflowName.TESTING not in USER_FACING_WORKFLOWS
    assert WorkflowName.REVIEW not in USER_FACING_WORKFLOWS
    assert WorkflowName.LEARNING not in USER_FACING_WORKFLOWS


# ── resolve_workflow_name ────────────────────────────────────────────────


def test_resolve_workflow_name_from_string() -> None:
    """resolve_workflow_name converts valid string to WorkflowName."""
    assert resolve_workflow_name("generate_code") == WorkflowName.GENERATE_CODE
    assert resolve_workflow_name("planning") == WorkflowName.PLANNING
    assert resolve_workflow_name("learning") == WorkflowName.LEARNING


def test_resolve_workflow_name_from_enum() -> None:
    """resolve_workflow_name passes through existing WorkflowName."""
    assert resolve_workflow_name(WorkflowName.DEBUG_CODE) == WorkflowName.DEBUG_CODE


def test_resolve_workflow_name_unknown() -> None:
    """resolve_workflow_name returns None for unknown strings."""
    assert resolve_workflow_name("nonexistent_workflow") is None
    assert resolve_workflow_name("") is None


# ── Workflow stage handler ───────────────────────────────────────────────


def test_workflow_stage_handler_default_is_empty() -> None:
    """WorkflowStage.handler defaults to empty string (not name)."""
    stage = WorkflowStage(name="testing", current_stage="testing")

    assert stage.handler == ""


def test_workflow_stage_uses_tool_context_only_on_design_and_impl() -> None:
    """Only design and implementation stages use tool context."""
    defs = get_workflow_definitions()
    wf = defs[WorkflowName.GENERATE_CODE]

    for s in wf.stages:
        if s.name in ("design", "implementation"):
            assert s.uses_tool_context is True
        else:
            assert s.uses_tool_context is False


def test_workflow_stage_prompt_template_default_empty() -> None:
    """All stages have empty prompt_template (no custom templates yet)."""
    defs = get_workflow_definitions()
    for wf in defs.values():
        for stage in wf.stages:
            assert stage.prompt_template == ""
