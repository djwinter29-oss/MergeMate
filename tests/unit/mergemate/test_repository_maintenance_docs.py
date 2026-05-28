from __future__ import annotations

from pathlib import Path


def test_repository_maintenance_docs_cover_the_prune_target() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    readme_text = (repo_root / "README.md").read_text(encoding="utf-8")
    maintenance_text = (repo_root / "docs" / "operations" / "repository-maintenance.md").read_text(
        encoding="utf-8"
    )
    makefile_text = (repo_root / "Makefile").read_text(encoding="utf-8")

    assert "branches-prune" in makefile_text
    assert "branches-prune" in readme_text
    assert "branches-prune" in maintenance_text
    assert "branches-clean" in maintenance_text
