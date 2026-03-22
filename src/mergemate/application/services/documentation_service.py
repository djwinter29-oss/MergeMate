"""Persist workflow documents under the docs folder."""

import re
import unicodedata
from pathlib import Path


class DocumentationService:
    def __init__(self, docs_root: Path) -> None:
        self._docs_root = docs_root

    def write_architecture_design(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
    ) -> Path:
        return self._write_document(
            run_id=run_id,
            iteration=iteration,
            plan_text=plan_text,
            section_name="architecture",
            document_suffix="",
            title_prefix="Architecture Design",
            sections=(
                ("Approved Plan", plan_text),
                ("Architecture Design", design_text),
            ),
        )

    def write_test_plan(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
        test_text: str,
    ) -> Path:
        return self._write_document(
            run_id=run_id,
            iteration=iteration,
            plan_text=plan_text,
            section_name="testing",
            document_suffix="test-plan",
            title_prefix="Test Plan",
            sections=(
                ("Approved Plan", plan_text),
                ("Architecture Design", design_text),
                ("Test Plan", test_text),
            ),
        )

    def write_review_report(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        design_text: str,
        implementation_text: str,
        test_text: str,
        review_text: str,
    ) -> Path:
        return self._write_document(
            run_id=run_id,
            iteration=iteration,
            plan_text=plan_text,
            section_name="reviews",
            document_suffix="review-report",
            title_prefix="Review Report",
            sections=(
                ("Approved Plan", plan_text),
                ("Architecture Design", design_text),
                ("Implementation", implementation_text),
                ("Test Plan", test_text),
                ("Review Report", review_text),
            ),
        )

    def _write_document(
        self,
        *,
        run_id: str,
        iteration: int,
        plan_text: str,
        section_name: str,
        document_suffix: str,
        title_prefix: str,
        sections: tuple[tuple[str, str], ...],
    ) -> Path:
        plan_summary = self._extract_plan_summary(plan_text)
        target_dir = self._docs_root / section_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = self._build_document_path(
            target_dir=target_dir,
            plan_summary=plan_summary,
            document_suffix=document_suffix,
            iteration=iteration,
        )
        content = [
            f"# {title_prefix}: {plan_summary}",
            "",
            f"- Run ID: {run_id}",
            f"- Iteration: {iteration}",
            f"- Plan Summary: {plan_summary}",
            "",
        ]
        for heading, body in sections:
            content.extend((f"## {heading}", "", body.strip(), ""))
        target_path.write_text("\n".join(content).rstrip() + "\n", encoding="utf-8")
        return target_path

    def _build_document_path(
        self,
        *,
        target_dir: Path,
        plan_summary: str,
        document_suffix: str,
        iteration: int,
    ) -> Path:
        filename_root = self._slugify(plan_summary)
        if document_suffix:
            filename_root = f"{filename_root}-{document_suffix}"
        if iteration > 1:
            filename_root = f"{filename_root}-iteration-{iteration}"
        candidate = target_dir / f"{filename_root}.md"
        if not candidate.exists():
            return candidate

        counter = 2
        while True:
            deduplicated = target_dir / f"{filename_root}-{counter}.md"
            if not deduplicated.exists():
                return deduplicated
            counter += 1

    def _extract_plan_summary(self, plan_text: str) -> str:
        for raw_line in plan_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                line = line.lstrip("#").strip()
            line = re.sub(r"^[-*+]\s+", "", line)
            line = re.sub(r"^\d+[.)]\s+", "", line)
            normalized = line.lower().rstrip(":")
            if normalized in {"approved plan", "plan", "implementation plan", "requirements", "scope"}:
                continue
            return line[:80].rstrip()
        return "Work Item"

    def _slugify(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
        return slug[:80].rstrip("-") or "work-item"