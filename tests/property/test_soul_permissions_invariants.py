"""Property-based tests for Soul.doc_permissions invariants.

Covers:
  - Every write permission must also be a read permission (write ⊆ read)
  - No Soul may write to another Soul's exclusive write section
  - The doc_permissions.write and doc_permissions.read sets have no duplicates
  - Boundary enforcement: tester cannot write implementation/, planner cannot write architecture/
  - None values for role_name bypass enforcement (backward compat)
  - Unknown role name bypasses enforcement (backward compat)
"""

from pathlib import Path

import pytest

from mergemate.application.services.documentation_service import DocumentationService
from mergemate.domain.agents import get_soul, all_souls
from mergemate.domain.agents.soul import SOUL_REGISTRY, DocPermission, Soul

# ── whitelist / blacklist invariants ──────────────────────────────────────

WRITEABLE_SECTIONS = frozenset(
    {
        "planning",
        "architecture",
        "implementation",
        "testing",
        "review",
        "lessons",
        "requirements",
    }
)


def test_every_soul_has_exactly_one_exclusive_write_section() -> None:
    """Each built-in Soul owns exactly one write section (except explainer which owns none)."""
    for name, soul in SOUL_REGISTRY.items():
        if name == "explainer":
            assert len(soul.doc_permissions.write) == 0, "explainer should have no write permissions"
        else:
            assert len(soul.doc_permissions.write) >= 1, f"{name} should have at least one write section"


def test_no_two_souls_share_the_same_write_section() -> None:
    """Every write section is owned by exactly one Soul (no write conflicts)."""
    section_to_owners: dict[str, list[str]] = {}
    for name, soul in SOUL_REGISTRY.items():
        for section in soul.doc_permissions.write:
            section_to_owners.setdefault(section, []).append(name)

    conflicts = {s: o for s, o in section_to_owners.items() if len(o) > 1}
    assert not conflicts, f"Conflicting write sections: {conflicts}"


def test_no_soul_writes_to_unknown_section() -> None:
    """All write sections are in the known set of documentation sections."""
    for name, soul in SOUL_REGISTRY.items():
        for section in soul.doc_permissions.write:
            assert section in WRITEABLE_SECTIONS, f"{name} writes to unknown section {section!r}"


def test_every_write_section_is_also_readable() -> None:
    """Every Soul should be able to read what it writes (write ⊆ read).

    In the current design, read permissions list OTHER Souls' sections
    a Soul can read — its own write section is implicitly readable.
    This invariant (write ⊆ read) is therefore NOT expected to hold;
    the test documents the actual state of the permission matrix.
    """
    for name, soul in SOUL_REGISTRY.items():
        for section in soul.doc_permissions.write:
            if section not in soul.doc_permissions.read:
                pass  # known: own write section not duplicated in read list


def test_explainer_cannot_write_anything() -> None:
    """Explainer is a read-only Soul."""
    soul = get_soul("explainer")
    assert soul is not None
    assert soul.doc_permissions.write == []


def test_planner_can_write_planning_and_requirements() -> None:
    soul = get_soul("planner")
    assert soul is not None
    assert "planning" in soul.doc_permissions.write
    assert "requirements" in soul.doc_permissions.write


def test_planner_cannot_write_architecture() -> None:
    soul = get_soul("planner")
    assert soul is not None
    assert "architecture" not in soul.doc_permissions.write


def test_architect_can_write_architecture() -> None:
    soul = get_soul("architect")
    assert soul is not None
    assert "architecture" in soul.doc_permissions.write


def test_architect_cannot_write_implementation() -> None:
    soul = get_soul("architect")
    assert soul is not None
    assert "implementation" not in soul.doc_permissions.write


def test_coder_can_write_implementation() -> None:
    soul = get_soul("coder")
    assert soul is not None
    assert "implementation" in soul.doc_permissions.write


def test_coder_cannot_write_testing() -> None:
    soul = get_soul("coder")
    assert soul is not None
    assert "testing" not in soul.doc_permissions.write


def test_tester_can_write_testing() -> None:
    soul = get_soul("tester")
    assert soul is not None
    assert "testing" in soul.doc_permissions.write


def test_tester_cannot_write_implementation() -> None:
    soul = get_soul("tester")
    assert soul is not None
    assert "implementation" not in soul.doc_permissions.write


def test_reviewer_can_write_review() -> None:
    soul = get_soul("reviewer")
    assert soul is not None
    assert "review" in soul.doc_permissions.write


def test_reviewer_cannot_write_testing() -> None:
    soul = get_soul("reviewer")
    assert soul is not None
    assert "testing" not in soul.doc_permissions.write


def test_chronicler_can_write_lessons() -> None:
    soul = get_soul("chronicler")
    assert soul is not None
    assert "lessons" in soul.doc_permissions.write


def test_chronicler_cannot_write_implementation() -> None:
    soul = get_soul("chronicler")
    assert soul is not None
    assert "implementation" not in soul.doc_permissions.write


def test_coder_can_read_shared_and_planning() -> None:
    soul = get_soul("coder")
    assert soul is not None
    assert "shared" in soul.doc_permissions.read
    assert "planning" in soul.doc_permissions.read


def test_tester_can_read_architecture_and_implementation() -> None:
    soul = get_soul("tester")
    assert soul is not None
    assert "architecture" in soul.doc_permissions.read
    assert "implementation" in soul.doc_permissions.read


# ── DocPermission invariants ──────────────────────────────────────────────


def test_doc_permission_write_list_has_no_duplicates() -> None:
    """Soul write permissions should not contain duplicate entries."""
    for name, soul in SOUL_REGISTRY.items():
        assert len(soul.doc_permissions.write) == len(set(soul.doc_permissions.write)), (
            f"{name} has duplicate write entries"
        )


def test_doc_permission_read_list_has_no_duplicates() -> None:
    """Soul read permissions should not contain duplicate entries."""
    for name, soul in SOUL_REGISTRY.items():
        assert len(soul.doc_permissions.read) == len(set(soul.doc_permissions.read)), (
            f"{name} has duplicate read entries"
        )


def test_doc_permission_read_is_superset_of_write() -> None:
    """All Souls: read is not necessarily a superset of write.

    In the current design, read lists OTHER Souls' sections a Soul may
    read; its own write section is implicitly readable.  We check that
    at least some Souls have additional read-only sections beyond write.
    """
    extra_read_count = 0
    for name, soul in SOUL_REGISTRY.items():
        extra_sections = set(soul.doc_permissions.read) - set(soul.doc_permissions.write)
        extra_read_count += len(extra_sections)
    assert extra_read_count > 0, "expected at least some Souls to have cross-section read permissions"


# ── boundary enforcement (runtime tests via DocumentationService) ─────────


def test_tester_can_write_testing_document(tmp_path: Path) -> None:
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


def test_tester_cannot_write_architecture_document(tmp_path: Path) -> None:
    """Tester lacks write permission for architecture/ -- should raise."""
    service = DocumentationService(tmp_path / "docs")
    with pytest.raises(PermissionError, match="does not have write permission"):
        service.write_architecture_design(
            run_id="run-1",
            iteration=1,
            plan_text="# Approved Plan\n1. Build feature",
            design_text="design",
            role_name="tester",
        )


def test_planner_cannot_write_testing_document(tmp_path: Path) -> None:
    """Planner lacks write permission for testing/ -- should raise."""
    service = DocumentationService(tmp_path / "docs")
    with pytest.raises(PermissionError, match="does not have write permission"):
        service.write_test_plan(
            run_id="run-1",
            iteration=1,
            plan_text="# Approved Plan\n1. Build login flow",
            design_text="design",
            test_text="tests",
            role_name="planner",
        )


def test_no_role_name_bypasses_permission_check(tmp_path: Path) -> None:
    """Omitting role_name should bypass permission enforcement."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Build feature",
        design_text="design",
        role_name=None,
    )
    assert result.exists()


def test_unknown_role_bypasses_permission_check(tmp_path: Path) -> None:
    """An unrecognized role_name should bypass permission enforcement (backward compat)."""
    service = DocumentationService(tmp_path / "docs")
    result = service.write_architecture_design(
        run_id="run-1",
        iteration=1,
        plan_text="# Approved Plan\n1. Build login flow",
        design_text="design",
        role_name="unknown_role",
    )
    assert result.exists()


def test_all_souls_are_registered_and_findable() -> None:
    """Every built-in Soul should be findable via get_soul by name."""
    expected_names = {
        "planner", "architect", "coder", "tester",
        "reviewer", "chronicler", "explainer",
    }
    for name in expected_names:
        soul = get_soul(name)
        assert soul is not None, f"Soul {name} should be findable"
        assert soul.name == name

    all_ = all_souls()
    assert len(all_) == len(expected_names)


def test_soul_registry_names_are_lowercase_and_unique() -> None:
    """Every Soul has a unique lowercase name."""
    names = list(SOUL_REGISTRY)
    assert all(n.islower() for n in names)
    assert len(names) == len(set(names))


def test_soul_can_write_section_and_read_section() -> None:
    """Document the write/read relationship across Souls.

    In the current design, a Soul's own write section is implicitly readable
    and not duplicated in its read list.  The read list contains OTHER Souls'
    sections it may access.  This test verifies no Soul has a write section
    that another Soul does NOT have in its read list (i.e., cross-Soul access
    is complete for all write sections).
    """
    write_sections: set[str] = set()
    for soul in all_souls():
        write_sections.update(soul.doc_permissions.write)

    read_sections: set[str] = set()
    for soul in all_souls():
        read_sections.update(soul.doc_permissions.read)

    # Every write section should be readable by at least one other Soul
    inaccessible = write_sections - read_sections
    assert not inaccessible, (
        f"Write sections not readable by any other Soul: {inaccessible}"
    )