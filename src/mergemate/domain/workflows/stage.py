"""Workflow stage and definition models.

These types describe the structure of a multi-stage workflow:
- *WorkflowStage* — a single stage within a workflow pipeline
- *WorkflowDefinition* — a named workflow composed of ordered stages
"""

from __future__ import annotations

from dataclasses import dataclass

from mergemate.domain.shared.enums import WorkflowName


__all__ = [
    "WorkflowStage",
    "WorkflowDefinition",
    "get_workflow_definitions",
]


@dataclass(slots=True, frozen=True)
class WorkflowStage:
    """A single stage within a workflow execution pipeline.

    Attributes:
        name: Human-readable stage name (e.g. "design", "implementation").
        current_stage: Value written to RunStage / run.current_stage during
            execution (e.g. "design", "implementation").
        handler: Key identifying the stage handler that executes this stage.
            The execution plan uses ``handler`` to look up the correct
            execution logic from the handler registry.  Built-in values
            include ``"design"``, ``"implementation"``, ``"testing"``,
            ``"review"``, ``"replanning"``, ``"direct"``.
        prompt_template: Optional path or identifier for the stage-level
            system prompt template.  When empty the parent workflow's
            prompt is used.
        uses_tool_context: If ``True``, runtime tool context is gathered
            and injected into the prompt before this stage runs.
        checks_cancellation_before: If ``True``, the run is checked for
            cancellation *before* executing this stage.  Typically set on
            the first stage of a pipeline.
        checks_cancellation_after: If ``True``, the run is checked for
            cancellation *after* executing this stage.  Set on stages
            where rollback or partial state is expensive / irreversible.
        produces: Names of artifacts this stage produces, used by the
            handler to determine what to persist and how to structure
            documentation.  Example: ``("design_text",)`` or
            ``("result_text",)``.
    """

    name: str
    current_stage: str
    handler: str = ""
    prompt_template: str = ""
    uses_tool_context: bool = False
    checks_cancellation_before: bool = False
    checks_cancellation_after: bool = False
    produces: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class WorkflowDefinition:
    """A named workflow composed of an ordered sequence of stages."""

    name: str
    stages: tuple[WorkflowStage, ...]


def _stage(
    name: str,
    current_stage: str,
    *,
    handler: str = "",
    uses_tool_context: bool = False,
    checks_cancellation_before: bool = False,
    checks_cancellation_after: bool = False,
    produces: tuple[str, ...] = (),
) -> WorkflowStage:
    """Convenience constructor for ``WorkflowStage`` with keyword-only extras."""
    return WorkflowStage(
        name=name,
        current_stage=current_stage,
        handler=handler or name,
        uses_tool_context=uses_tool_context,
        checks_cancellation_before=checks_cancellation_before,
        checks_cancellation_after=checks_cancellation_after,
        produces=produces,
    )


# ── Built-in multi-stage workflow definitions ──────────────────────────────
# Each WorkflowName maps to a WorkflowDefinition whose stages serve as
# the single source of truth for the pipeline.  New workflows are added
# here without touching any other file.

_BUILTIN_WORKFLOWS: dict[WorkflowName, WorkflowDefinition] = {
    WorkflowName.GENERATE_CODE: WorkflowDefinition(
        name=WorkflowName.GENERATE_CODE.value,
        stages=(
            _stage(
                name="design",
                current_stage="design",
                uses_tool_context=True,
                checks_cancellation_before=True,
                checks_cancellation_after=True,
                produces=("design_text",),
            ),
            _stage(
                name="implementation",
                current_stage="implementation",
                uses_tool_context=True,
                checks_cancellation_after=True,
                produces=("result_text",),
            ),
            _stage(
                name="testing",
                current_stage="testing",
                checks_cancellation_after=True,
                produces=("test_text",),
            ),
            _stage(
                name="review",
                current_stage="review",
                checks_cancellation_after=True,
                produces=("review_text",),
            ),
            _stage(
                name="replanning",
                current_stage="internal_replanning",
                checks_cancellation_after=True,
            ),
        ),
    ),
}


def get_workflow_definitions() -> dict[WorkflowName, WorkflowDefinition]:
    """Return the map of known workflow definitions.

    Currently contains the built-in ``generate_code`` multi-stage workflow.
    Additional definitions can be registered at startup or loaded from config.
    """
    return dict(_BUILTIN_WORKFLOWS)