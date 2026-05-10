"""Tests for Soul entity — permission checking, whitelist/blacklist."""


from mergemate.domain.agents.soul import (
    DocPermission,
    Soul,
    all_souls,
    get_soul,
)


# ── DocPermission construction ────────────────────────────────────────────


def test_doc_permission_empty() -> None:
    """DocPermission defaults to empty lists."""
    perm = DocPermission()
    assert perm.write == []
    assert perm.read == []


def test_doc_permission_with_lists() -> None:
    """DocPermission stores write and read lists given at construction."""
    perm = DocPermission(
        write=["testing", "implementation"],
        read=["planning", "architecture"],
    )
    assert perm.write == ["testing", "implementation"]
    assert perm.read == ["planning", "architecture"]


# ── Soul construction ────────────────────────────────────────────────────


def test_soul_construction() -> None:
    """Soul stores all supplied fields."""
    soul = Soul(
        name="test_role",
        display_name="测试角色",
        personality="严谨、细致。不写实现代码。",
        expertise=["单元测试", "边界条件测试"],
        responsibilities=["编写测试用例", "执行测试"],
        boundaries=["不得编写实现代码", "不得做架构设计"],
        doc_permissions=DocPermission(write=["testing"], read=["planning"]),
    )

    assert soul.name == "test_role"
    assert soul.display_name == "测试角色"
    assert soul.personality == "严谨、细致。不写实现代码。"
    assert soul.expertise == ["单元测试", "边界条件测试"]
    assert soul.responsibilities == ["编写测试用例", "执行测试"]
    assert soul.boundaries == ["不得编写实现代码", "不得做架构设计"]
    assert soul.doc_permissions.write == ["testing"]
    assert soul.doc_permissions.read == ["planning"]


# ── Soul.to_system_prompt() ──────────────────────────────────────────────


def test_soul_to_system_prompt_format() -> None:
    """to_system_prompt produces expected section headings and content."""
    soul = Soul(
        name="tester",
        display_name="质量保障",
        personality="严谨的测试者",
        expertise=["单元测试"],
        responsibilities=["写测试"],
        boundaries=["不写代码"],
        doc_permissions=DocPermission(
            write=["testing"],
            read=["architecture", "planning"],
        ),
    )

    prompt = soul.to_system_prompt()

    assert "## Your Role: 质量保障 (tester)" in prompt
    assert "### Personality\n严谨的测试者" in prompt
    assert "### Expertise" in prompt
    assert "- 单元测试" in prompt
    assert "### Core Responsibilities" in prompt
    assert "- 写测试" in prompt
    assert "### Strict Boundaries" in prompt
    assert "- 不写代码" in prompt
    assert "### Document sections you may WRITE" in prompt
    assert "- docs/testing/" in prompt
    assert "### Document sections you may READ" in prompt
    assert "- docs/architecture/" in prompt
    assert "- docs/planning/" in prompt


def test_soul_to_system_prompt_sorted_read_sections() -> None:
    """READ sections are alphabetically sorted in the prompt."""
    soul = Soul(
        name="reviewer",
        display_name="评审",
        personality="挑剔",
        expertise=["代码审查"],
        responsibilities=["审查代码"],
        boundaries=["不写代码"],
        doc_permissions=DocPermission(
            write=["review"],
            read=["testing", "planning", "implementation", "architecture"],
        ),
    )

    prompt = soul.to_system_prompt()
    # Extract the READ section lines
    lines = prompt.split("\n")
    read_idx = next(
        i for i, l in enumerate(lines) if l.startswith("### Document sections you may READ")
    )
    read_sections = [l.strip("- ").strip() for l in lines[read_idx + 1:] if l.startswith("- ")]

    # The READ lines should be docs/architecture/, docs/implementation/, docs/planning/, docs/testing/
    assert len(read_sections) == 4
    assert read_sections == sorted(read_sections)


def test_soul_to_system_prompt_empty_permissions() -> None:
    """A Soul with empty doc_permissions still produces valid sections with no entries."""
    soul = Soul(
        name="explainer",
        display_name="解说员",
        personality="善于解释",
        expertise=["解读代码"],
        responsibilities=["回答代码问题"],
        boundaries=["不得编写代码"],
        doc_permissions=DocPermission(write=[], read=[]),
    )

    prompt = soul.to_system_prompt()

    assert "### Document sections you may WRITE" in prompt
    assert "### Document sections you may READ" in prompt
    # No section lines after the headers
    lines = prompt.split("\n")
    for section_header in [
        "### Document sections you may WRITE",
        "### Document sections you may READ",
    ]:
        idx = lines.index(section_header)
        next_lines = lines[idx + 1:]
        next_content = next((l for l in next_lines if l.strip()), None)
        assert next_content is None or not next_content.startswith("- docs/")


# ── get_soul() ────────────────────────────────────────────────────────────


def test_get_soul_returns_soul() -> None:
    """get_soul returns the correct Soul for known role names."""
    soul = get_soul("tester")
    assert soul is not None
    assert soul.name == "tester"
    assert soul.display_name == "质量保障"


def test_get_soul_unknown_returns_none() -> None:
    """get_soul returns None for an unregistered role name."""
    assert get_soul("nonexistent_role") is None


def test_get_soul_all_registered_roles() -> None:
    """All expected Souls are accessible by name."""
    expected_names = {
        "planner",
        "architect",
        "coder",
        "tester",
        "reviewer",
        "chronicler",
        "explainer",
    }
    for name in expected_names:
        soul = get_soul(name)
        assert soul is not None, f"Missing Soul for '{name}'"
        assert soul.name == name


# ── all_souls() ──────────────────────────────────────────────────────────


def test_all_souls_returns_all() -> None:
    """all_souls() returns every built-in Soul."""
    souls = all_souls()
    names = {s.name for s in souls}
    expected = {
        "planner",
        "architect",
        "coder",
        "tester",
        "reviewer",
        "chronicler",
        "explainer",
    }
    assert names == expected


def test_all_souls_no_duplicates() -> None:
    """all_souls() contains no duplicate names."""
    souls = all_souls()
    names = [s.name for s in souls]
    assert len(names) == len(set(names))


# ── SOUL_REGISTRY internal check ─────────────────────────────────────────


def test_soul_registry_immutable_at_top_level() -> None:
    """SoulRegistry is a plain dict but its values are Soul instances."""
    from mergemate.domain.agents.soul import SOUL_REGISTRY

    assert isinstance(SOUL_REGISTRY, dict)
    assert all(isinstance(s, Soul) for s in SOUL_REGISTRY.values())


# ── Built-in Soul boundary verification ──────────────────────────────────


def test_tester_soul_boundaries() -> None:
    """Tester Soul has correct boundaries."""
    soul = get_soul("tester")
    assert soul is not None
    assert "不得编写实现代码" in soul.boundaries
    assert "不得做架构设计" in soul.boundaries
    assert "不得审查他人代码" in soul.boundaries
    assert "不负责制定计划" in soul.boundaries
    assert soul.doc_permissions.write == ["testing"]
    assert "planning" in soul.doc_permissions.read
    assert "architecture" in soul.doc_permissions.read
    assert "implementation" in soul.doc_permissions.read


def test_planner_soul_permissions() -> None:
    """Planner Soul can write to planning/ and requirements/, read from architecture/."""
    soul = get_soul("planner")
    assert soul is not None
    assert "planning" in soul.doc_permissions.write
    assert "requirements" in soul.doc_permissions.write
    assert "architecture" in soul.doc_permissions.read
    assert "testing" not in soul.doc_permissions.write


def test_coder_soul_cannot_write_to_testing() -> None:
    """Coder Soul is prohibited from writing to testing docs."""
    soul = get_soul("coder")
    assert soul is not None
    assert "testing" not in soul.doc_permissions.write
    assert "implementation" in soul.doc_permissions.write


def test_reviewer_soul_reads_everything() -> None:
    """Reviewer Soul can read all document sections."""
    soul = get_soul("reviewer")
    assert soul is not None
    all_sections = {
        "planning",
        "architecture",
        "implementation",
        "testing",
        "shared",
        "requirements",
    }
    assert all_sections.issubset(set(soul.doc_permissions.read))


def test_chronicler_soul_writes_lessons() -> None:
    """Chronicler Soul writes to lessons/ and reads all sections."""
    soul = get_soul("chronicler")
    assert soul is not None
    assert soul.doc_permissions.write == ["lessons"]
    # Chronicler reads everything
    assert len(soul.doc_permissions.read) >= 6


def test_explainer_soul_no_write_permissions() -> None:
    """Explainer Soul has no write permissions (read-only role)."""
    soul = get_soul("explainer")
    assert soul is not None
    assert soul.doc_permissions.write == []
    assert len(soul.doc_permissions.read) >= 4


# ── Cross-Soul uniqueness ────────────────────────────────────────────────


def test_all_soul_names_unique() -> None:
    """Every built-in Soul has a distinct name."""
    souls = all_souls()
    names = [s.name for s in souls]
    assert len(names) == len(set(names))


def test_all_soul_display_names_nonempty() -> None:
    """Every built-in Soul has a non-empty display_name."""
    for soul in all_souls():
        assert soul.display_name.strip(), f"Soul '{soul.name}' has empty display_name"