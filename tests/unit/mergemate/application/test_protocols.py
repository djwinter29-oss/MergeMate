from __future__ import annotations

import inspect

try:
    from typing import get_protocol_members  # Python >= 3.13
except ImportError:
    from typing import _get_protocol_attrs  # type: ignore[attr-defined]

    def get_protocol_members(tp: type) -> frozenset[str]:  # type: ignore[no-redef]
        return frozenset(_get_protocol_attrs(tp))


from mergemate.application.protocols import (
    ContextServiceProtocol,
    DocumentationServiceProtocol,
    LLMGatewayProtocol,
    LearningServiceProtocol,
    PlanningServiceProtocol,
    PromptServiceProtocol,
    ToolServiceProtocol,
    WorkflowServiceProtocol,
)
from mergemate.application.services.context_service import ContextService
from mergemate.application.services.documentation_service import DocumentationService
from mergemate.application.services.learning_service import LearningService
from mergemate.application.services.planning_service import PlanningService
from mergemate.application.services.prompt_service import PromptService
from mergemate.application.services.tool_service import ToolService
from mergemate.application.services.workflow_service import WorkflowService
from mergemate.infrastructure.llm.gateway import ParallelLLMGateway


def _protocol_methods(protocol: type) -> list[str]:
    return sorted(get_protocol_members(protocol))


def _normalized_signature(
    signature: inspect.Signature,
) -> list[tuple[str, inspect._ParameterKind, object]]:
    return [
        (parameter.name, parameter.kind, parameter.default)
        for parameter in signature.parameters.values()
    ]


def _assert_protocol_compatible(
    concrete_cls: type, protocol: type, async_methods: set[str] | None = None
) -> None:
    async_methods = async_methods or set()
    concrete_signature_targets = []

    for name in _protocol_methods(protocol):
        assert hasattr(concrete_cls, name), f"{concrete_cls.__name__} is missing member {name!r}"
        attr = getattr(concrete_cls, name)
        assert callable(attr), f"{concrete_cls.__name__}.{name} is not callable"
        assert _normalized_signature(inspect.signature(attr)) == _normalized_signature(
            inspect.signature(getattr(protocol, name))
        )
        if name in async_methods:
            assert inspect.iscoroutinefunction(attr), (
                f"{concrete_cls.__name__}.{name} should be async"
            )

        concrete_signature_targets.append((name, inspect.signature(attr)))

    # Guard against accidental drift in the concrete surface area: the
    # implementation should expose at least the protocol members and nothing
    # protocol-relevant should be renamed silently.
    assert concrete_signature_targets


def test_context_service_implements_context_service_protocol() -> None:
    _assert_protocol_compatible(ContextService, ContextServiceProtocol)


def test_documentation_service_implements_documentation_service_protocol() -> None:
    _assert_protocol_compatible(DocumentationService, DocumentationServiceProtocol)


def test_learning_service_implements_learning_service_protocol() -> None:
    _assert_protocol_compatible(
        LearningService,
        LearningServiceProtocol,
        async_methods={"remember_success"},
    )


def test_planning_service_implements_planning_service_protocol() -> None:
    _assert_protocol_compatible(
        PlanningService,
        PlanningServiceProtocol,
        async_methods={"draft_plan", "revise_plan"},
    )


def test_prompt_service_implements_prompt_service_protocol() -> None:
    _assert_protocol_compatible(PromptService, PromptServiceProtocol)


def test_tool_service_implements_tool_service_protocol() -> None:
    _assert_protocol_compatible(
        ToolService,
        ToolServiceProtocol,
        async_methods={"build_runtime_tool_context_async"},
    )


def test_workflow_service_implements_workflow_service_protocol() -> None:
    _assert_protocol_compatible(
        WorkflowService,
        WorkflowServiceProtocol,
        async_methods={
            "create_design",
            "generate_code",
            "execute_direct",
            "generate_tests",
            "review",
            "record_lesson",
        },
    )
    assert callable(getattr(WorkflowService, "has_high_concerns"))
    assert _normalized_signature(
        inspect.signature(WorkflowService.has_high_concerns)
    ) == _normalized_signature(
        inspect.signature(getattr(WorkflowServiceProtocol, "has_high_concerns"))
    )


def test_llm_gateway_implements_llm_gateway_protocol() -> None:
    _assert_protocol_compatible(ParallelLLMGateway, LLMGatewayProtocol, async_methods={"generate"})
