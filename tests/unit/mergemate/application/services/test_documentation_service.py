from pathlib import Path

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

    assert test_plan_path == tmp_path / "docs" / "testing" / "build-login-flow-test-plan-iteration-2.md"
    assert review_report_path == tmp_path / "docs" / "reviews" / "build-login-flow-review-report.md"
    assert "Test Plan" in test_plan_path.read_text(encoding="utf-8")
    assert "Review Report" in review_report_path.read_text(encoding="utf-8")


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

    assert first.name == "build-login-flow.md"
    assert second.name == "build-login-flow-2.md"


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