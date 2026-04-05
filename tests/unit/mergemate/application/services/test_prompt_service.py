from pathlib import Path

from mergemate.application.services.prompt_service import PromptService
from mergemate.domain.shared import WorkflowName


def _write_prompt(root: Path, name: str, content: str) -> None:
    system_dir = root / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / name).write_text(content, encoding="utf-8")


def test_render_uses_workflow_specific_prompt_file(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "code_generation.md", "system-code")
    service = PromptService(tmp_path)

    system_prompt, user_prompt = service.render("generate_code", [], [], "build feature")

    assert system_prompt == "system-code"
    assert user_prompt == "build feature"


def test_render_accepts_workflow_enum(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "debugging.md", "debug-system")
    service = PromptService(tmp_path)

    system_prompt, user_prompt = service.render(WorkflowName.DEBUG_CODE, [], [], "debug this")

    assert system_prompt == "debug-system"
    assert user_prompt == "debug this"


def test_render_falls_back_to_base_prompt(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "base.md", "base-system")
    service = PromptService(tmp_path)

    system_prompt, user_prompt = service.render("unknown", [], [], "hello")

    assert system_prompt == "base-system"
    assert user_prompt == "hello"


def test_render_includes_recent_messages_and_learning(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "debugging.md", "debug-system")
    service = PromptService(tmp_path)

    system_prompt, user_prompt = service.render(
        "debug_code",
        [{"role": "user", "content": "previous request"}, {"role": "assistant", "content": "previous answer"}],
        [{"workflow": "debug_code", "prompt": "older", "result_excerpt": "fix syntax"}],
        "latest prompt",
    )

    assert system_prompt == "debug-system"
    assert "Recent conversation:" in user_prompt
    assert "USER: previous request" in user_prompt
    assert "ASSISTANT: previous answer" in user_prompt
    assert "Previously successful patterns:" in user_prompt
    assert "Prior result excerpt: fix syntax" in user_prompt
    assert user_prompt.endswith("Latest user request:\nlatest prompt")


def test_render_includes_learning_without_recent_messages(tmp_path: Path) -> None:
    _write_prompt(tmp_path, "explanation.md", "explain-system")
    service = PromptService(tmp_path)

    system_prompt, user_prompt = service.render(
        "explain_code",
        [],
        [{"workflow": "explain_code", "prompt": "older", "result_excerpt": "summary"}],
        "latest prompt",
    )

    assert system_prompt == "explain-system"
    assert user_prompt.startswith("Previously successful patterns:")
    assert user_prompt.endswith("Latest user request:\nlatest prompt")
