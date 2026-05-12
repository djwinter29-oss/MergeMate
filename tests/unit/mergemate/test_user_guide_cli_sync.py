"""Ensure CLI commands documented in docs/user-guide.md stay in sync with the CLI."""

from pathlib import Path
import re

from mergemate.cli import app


def _user_guide_command_names(user_guide_text: str) -> list[str]:
    """Extract mergemate commands from the user-guide Basic Commands section.

    The user-guide uses fenced code blocks (```bash) with raw command invocations
    like ``mergemate validate-config``.  This function parses those out.

    Only the **primary** command name is extracted (e.g. ``validate-config`` from
    ``mergemate validate-config [--config ...]``).  Variants that differ only in
    flags (e.g. ``mergemate probe-readiness --wait``) are ignored to avoid
    duplicate assertions — the base command must be present regardless.
    """
    in_basics_section = False
    seen: set[str] = set()

    for line in user_guide_text.splitlines():
        stripped = line.strip()

        # Enter the Basic Commands section
        if stripped == "## Basic Commands":
            in_basics_section = True
            continue

        # Leave on the next top-level heading
        if in_basics_section and stripped.startswith("## "):
            break

        if not in_basics_section:
            continue

        # Match lines inside fenced code blocks that start with "mergemate "
        match = re.match(r"^mergemate (\S+)", stripped)
        if match:
            seen.add(match.group(1))

    return sorted(seen)


def test_user_guide_commands_stay_in_sync_with_cli() -> None:
    """All CLI commands should be documented in the user guide's Basic Commands section.

    This mirrors test_readme_commands_stay_in_sync_with_cli for README.md.
    """
    repo_root = Path(__file__).resolve().parents[3]
    user_guide_path = repo_root / "docs" / "user-guide.md"
    assert user_guide_path.is_file(), f"user-guide.md not found at {user_guide_path}"

    guide_commands = _user_guide_command_names(
        user_guide_path.read_text(encoding="utf-8"),
    )
    cli_commands = sorted(command.name for command in app.registered_commands)

    # Build a diff for a clear error message
    missing_from_guide = sorted(set(cli_commands) - set(guide_commands))
    extra_in_guide = sorted(set(guide_commands) - set(cli_commands))

    err_parts: list[str] = []
    if missing_from_guide:
        err_parts.append(f"CLI commands NOT documented in user-guide.md: {missing_from_guide}")
    if extra_in_guide:
        err_parts.append(f"user-guide.md lists commands NOT in CLI: {extra_in_guide}")

    if err_parts:
        msg = "; ".join(err_parts)
        # Provide helpful context
        msg += f"\n  CLI commands ({len(cli_commands)}): {cli_commands}"
        msg += f"\n  User-guide commands ({len(guide_commands)}): {guide_commands}"
        raise AssertionError(msg)