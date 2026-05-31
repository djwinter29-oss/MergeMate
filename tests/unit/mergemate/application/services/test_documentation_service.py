from pathlib import Path

import pytest

from mergemate.application.services.documentation_service import DocumentationService


def test_write_architecture_design_uses_plan_based_filename(tmp_path: Path) -> None:
    service = DocumentationService(tmp_path / "docs")

    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Build login flow",
        design_text="design content",
    )

    assert result == tmp_path / "docs" / "architecture" / "build-login-flow.md"
    assert result.exists() is True
    contents = result.read_text(encoding="utf-8")
    assert "Approved Plan" in contents
    assert "Architecture Design: Build login flow" in contents
    assert "design content" in contents


def test_write_test_and_review_documents_use_final_paths(tmp_path: Path) -> None:
    service = DocumentationService(tmp_path / "docs")

    test_plan_path = service.write_test_plan(
        run_id="run-1",
        iteration=2,
        plan_text="# Approved Plan\n1. Build login flow",
        design_text="design content",
        test_text="test content",
    )
    review_report_path = service.write_review_report(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Build login flow",
        design_text="design content",
        implementation_text="implementation content",
        test_text="test content",
        review_text="review content",
    )

    assert (
        test_plan_path
        == tmp_path / "docs" / "testing" / "build-login-flow-test-plan-iteration-2.md"
    )
    assert review_report_path == tmp_path / "docs" / "reviews" / "build-login-flow-review-report.md"
    assert "Test Plan" in test_plan_path.read_text(encoding="utf-8")
    assert "Review Report" in review_report_path.read_text(encoding="utf-8")


def test_service_initialization_creates_review_directories(tmp_path: Path) -> None:
    DocumentationService(tmp_path / "docs")

    assert (tmp_path / "docs" / "review").is_dir()
    assert (tmp_path / "docs" / "reviews").is_dir()


def test_write_document_deduplicates_existing_filename(tmp_path: Path) -> None:
    service = DocumentationService(tmp_path / "docs")

    first = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="1. Build login flow",
        design_text="design",
    )
    second = service.write_architecture_design(
        run_id="run-2",
        iteration=1,
        plan_text="1. Build login flow",
        design_text="design",
    )
    third = service.write_architecture_design(
        run_id="run-3",
        iteration=1,
        plan_text="1. Build login flow",
        design_text="design",
    )

    assert first.name == "build-login-flow.md"
    assert second.name == "build-login-flow-2.md"
    assert third.name == "build-login-flow-3.md"


def test_extract_plan_summary_skips_generic_headings_and_slugifies_unicode(tmp_path: Path) -> None:
    service = DocumentationService(tmp_path / "docs")

    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\nRequirements\n1. Café login flow:",
        design_text="design",
    )

    assert result.name == "cafe-login-flow.md"


def test_extract_plan_summary_falls_back_when_no_meaningful_line_exists(tmp_path: Path) -> None:
    service = DocumentationService(tmp_path / "docs")

    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\nRequirements:\n",
        design_text="design",
    )

    assert result.name == "work-item.md"


def test_write_document_skips_blank_lines_when_extracting_summary(tmp_path: Path) -> None:
    service = DocumentationService(tmp_path / "docs")

    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="\n\n# Approved Plan\n\n* Scope\n2. Build dashboard\n",
        design_text="design",
    )

    assert result.name == "build-dashboard.md"


def test_write_architecture_permission_allowed_for_architect(tmp_path: Path) -> None:
    """Architect has write permission for architecture/ -- should succeed."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Build login flow",
        design_text="design content",
        role_name="architect",
    )
    assert result.exists()


def test_write_architecture_permission_denied_for_coder(tmp_path: Path) -> None:
    """Coder has NO write permission for architecture/ -- should raise."""
    service = DocumentationService(tmp_path / "docs")
    with pytest.raises(PermissionError, match="does not have write permission"):
        service.write_architecture_design(
            run_id="run-1",
            iteration=1,
            plan_text="# Approved Plan\n1. Build login flow",
            design_text="design content",
            role_name="coder",
        )


def test_write_test_plan_permission_allowed_for_tester(tmp_path: Path) -> None:
    """Tester has write permission for testing/ -- should succeed."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_test_plan(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Build login flow",
        design_text="design",
        test_text="tests",
        role_name="tester",
    )
    assert result.exists()


def test_write_lesson_permission_allowed_for_chronicler(tmp_path: Path) -> None:
    """Chronicler has write permission for lessons/ -- should succeed."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_lesson(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Build login flow",
        lesson_text="lessons learned",
        role_name="chronicler",
    )
    assert result.exists()


def test_write_lesson_permission_denied_for_planner(tmp_path: Path) -> None:
    """Planner has NO write permission for lessons/ -- should raise."""
    service = DocumentationService(tmp_path / "docs")
    with pytest.raises(PermissionError, match="does not have write permission"):
        service.write_lesson(
            run_id="run-1",
            iteration=1,
            plan_text="# Approved Plan\n1. Build login flow",
            lesson_text="lessons learned",
            role_name="planner",
        )


def test_write_requirement_permission_allowed_for_planner(tmp_path: Path) -> None:
    """Planner has write permission for requirements/ -- should succeed."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_requirement(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Add auth",
        requirement_text="auth requirement",
        role_name="planner",
    )
    assert result.exists()


def test_write_document_without_role_name_backward_compat(tmp_path: Path) -> None:
    """Omitting role_name should work (backward compat)."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Do something",
        design_text="design",
    )
    assert result.exists()


def test_write_document_with_unknown_role_backward_compat(tmp_path: Path) -> None:
    """An unknown role name should be allowed (backward compat)."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Do something",
        design_text="design",
        role_name="unknown-role",
    )
    assert result.exists()
