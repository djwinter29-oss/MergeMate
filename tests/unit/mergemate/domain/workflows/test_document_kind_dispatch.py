from pathlib import Path
from types import SimpleNamespace

import pytest

from mergemate.domain.workflows import handlers


class DocumentationServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def write_architecture_design(self, **kwargs) -> Path:
        self.calls.append(("architecture", kwargs))
        return Path("/tmp/architecture.md")

    def write_test_plan(self, **kwargs) -> Path:
        self.calls.append(("testing", kwargs))
        return Path("/tmp/testing.md")

    def write_review_report(self, **kwargs) -> Path:
        self.calls.append(("review", kwargs))
        return Path("/tmp/review.md")

    def write_lesson(self, **kwargs) -> Path:
        self.calls.append(("lessons", kwargs))
        return Path("/tmp/lessons.md")


@pytest.fixture()
def runtime() -> SimpleNamespace:
    documentation_service = DocumentationServiceStub()
    return SimpleNamespace(deps=SimpleNamespace(documentation_service=documentation_service))


@pytest.mark.parametrize(
    ("kind", "artifact_key", "extra_kwargs", "doc_method"),
    [
        (
            "architecture",
            "_design_document_path",
            {"design_text": "Design A", "agent_name": "architect"},
            "architecture",
        ),
        (
            "testing",
            "_test_document_path",
            {"design_text": "Design T", "test_text": "Tests T", "agent_name": "tester"},
            "testing",
        ),
        (
            "review",
            "_review_document_path",
            {
                "design_text": "Design R",
                "implementation_text": "Implementation R",
                "test_text": "Tests R",
                "review_text": "Review R",
                "agent_name": "reviewer",
            },
            "review",
        ),
        (
            "lessons",
            "_lesson_document_path",
            {"lesson_text": "Lessons L", "agent_name": "chronicler"},
            "lessons",
        ),
    ],
)
def test_save_document_dispatches_to_registered_saver(
    runtime: SimpleNamespace,
    kind: str,
    artifact_key: str,
    extra_kwargs: dict[str, object],
    doc_method: str,
) -> None:
    artifacts: dict[str, object] = {
        "run_id": "run-123",
        "_iteration": 2,
        "plan_text": "Approved plan text",
    }

    handlers._save_document(runtime, artifacts, kind, **extra_kwargs)

    assert artifacts[artifact_key] == f"/tmp/{kind}.md"
    assert runtime.deps.documentation_service.calls == [
        (
            doc_method,
            {
                "run_id": "run-123",
                "iteration": 2,
                "plan_text": "Approved plan text",
                **({"design_text": extra_kwargs["design_text"]} if "design_text" in extra_kwargs else {}),
                **({"test_text": extra_kwargs["test_text"]} if "test_text" in extra_kwargs else {}),
                **({"implementation_text": extra_kwargs["implementation_text"]} if "implementation_text" in extra_kwargs else {}),
                **({"review_text": extra_kwargs["review_text"]} if "review_text" in extra_kwargs else {}),
                **({"lesson_text": extra_kwargs["lesson_text"]} if "lesson_text" in extra_kwargs else {}),
                "role_name": extra_kwargs["agent_name"],
            },
        )
    ]


def test_document_kind_registry_contains_expected_kinds() -> None:
    assert set(handlers._DOCUMENT_KINDS) == {"architecture", "testing", "review", "lessons"}
    assert handlers._DOCUMENT_KINDS["architecture"].__name__ == "_save_architecture_document"
    assert handlers._DOCUMENT_KINDS["testing"].__name__ == "_save_testing_document"
    assert handlers._DOCUMENT_KINDS["review"].__name__ == "_save_review_document"
    assert handlers._DOCUMENT_KINDS["lessons"].__name__ == "_save_lessons_document"


def test_save_document_unknown_kind_raises_value_error(runtime: SimpleNamespace) -> None:
    with pytest.raises(ValueError, match=r"Unknown document kind 'unknown'\. Registered kinds: \['architecture', 'lessons', 'review', 'testing'\]"):
        handlers._save_document(
            runtime,
            {"run_id": "run-123"},
            "unknown",
            agent_name="tester",
        )
