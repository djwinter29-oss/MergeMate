from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


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


def test_architecture_review_notes_the_tool_invoker_protocol() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    architecture_review_text = (
        repo_root / "docs" / "architecture" / "architecture-review-2026-05-10.md"
    ).read_text(encoding="utf-8")

    assert "ToolInvoker" in architecture_review_text
    assert "the tool-interface gap" in architecture_review_text
    assert "now exists" in architecture_review_text


def test_repository_maintenance_prune_target_skips_the_current_branch() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    makefile_text = (repo_root / "Makefile").read_text(encoding="utf-8")
    maintenance_text = (repo_root / "docs" / "operations" / "repository-maintenance.md").read_text(
        encoding="utf-8"
    )

    assert "git branch --show-current" in makefile_text
    assert "excluding the current branch" in makefile_text
    assert "git for-each-ref --format='%(refname:short)' refs/heads --merged main" in makefile_text
    assert 'while IFS= read -r branch; do git branch -d "$$branch"; done' in makefile_text
    assert 'grep -Fvx -e main -e "$$current_branch"' in makefile_text
    assert "uses `git for-each-ref` for the branch listings" in maintenance_text
    assert "from a feature branch" in maintenance_text
    assert "will not try to delete the current checkout" in maintenance_text


def test_branch_maintenance_targets_succeed_when_there_are_no_matches() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    with TemporaryDirectory() as tmp_dir:
        tmp_repo = Path(tmp_dir)
        subprocess.run(["git", "init", "-b", "main"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "MergeMate Tests"],
            cwd=tmp_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "tests@example.com"],
            cwd=tmp_repo,
            check=True,
            capture_output=True,
        )
        (tmp_repo / "README.md").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "seed repo"],
            cwd=tmp_repo,
            check=True,
            capture_output=True,
        )

        merged = subprocess.run(
            ["make", "-f", str(repo_root / "Makefile"), "branches-merged"],
            cwd=tmp_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        stale = subprocess.run(
            ["make", "-f", str(repo_root / "Makefile"), "branches-list"],
            cwd=tmp_repo,
            check=True,
            capture_output=True,
            text=True,
        )

    assert "Local branches merged into main" in merged.stdout
    assert "Remote tracking branches merged into main" in merged.stdout
    assert "Stale branches (no remote tracking)" in stale.stdout
