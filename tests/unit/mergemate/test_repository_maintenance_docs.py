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


def test_repository_maintenance_prune_target_skips_the_current_branch() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    makefile_text = (repo_root / "Makefile").read_text(encoding="utf-8")
    maintenance_text = (repo_root / "docs" / "operations" / "repository-maintenance.md").read_text(
        encoding="utf-8"
    )

    assert "git branch --show-current" in makefile_text
    assert "excluding the current branch" in makefile_text
    assert 'grep -Fvx -e main -e "$$current_branch"' in makefile_text
    assert (
        "from a feature branch because it will not try to delete the current checkout"
        in maintenance_text
    )
