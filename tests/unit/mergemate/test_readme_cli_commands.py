from pathlib import Path
import re

from mergemate.cli import app


def _readme_command_names(readme_text: str) -> list[str]:
    in_commands_section = False
    commands: list[str] = []

    for line in readme_text.splitlines():
        stripped = line.strip()
        if stripped == "## Commands":
            in_commands_section = True
            continue
        if in_commands_section and stripped.startswith("## "):
            break
        if not in_commands_section:
            continue

        match = re.match(r"^- `mergemate ([a-z-]+)", stripped)
        if match:
            commands.append(match.group(1))

    return commands


def test_readme_commands_stay_in_sync_with_cli() -> None:
    readme_path = Path(__file__).resolve().parents[3] / "README.md"
    readme_commands = _readme_command_names(readme_path.read_text(encoding="utf-8"))
    cli_commands = [command.name for command in app.registered_commands]

    assert readme_commands == cli_commands
