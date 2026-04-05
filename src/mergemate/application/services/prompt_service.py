"""Prompt assembly service placeholder."""

from pathlib import Path

from mergemate.domain.shared import workflow_prompt_file


class PromptService:
    def __init__(self, prompts_root: Path) -> None:
        self._prompts_root = prompts_root

    def _load_system_prompt(self, workflow: str) -> str:
        prompt_name = workflow_prompt_file(workflow)
        return (self._prompts_root / "system" / prompt_name).read_text(encoding="utf-8").strip()

    def render(
        self,
        workflow: str,
        recent_messages: list[dict[str, str]],
        learned_items: list[dict[str, str]],
        user_prompt: str,
    ) -> tuple[str, str]:
        context_lines = [f"{message['role'].upper()}: {message['content']}" for message in recent_messages]
        contextual_user_prompt = user_prompt.strip()
        learning_lines = [
            "Previously successful patterns:",
            *[
                (
                    f"- Workflow: {item['workflow']}\n"
                    f"  Prior prompt: {item['prompt']}\n"
                    f"  Prior result excerpt: {item['result_excerpt']}"
                )
                for item in learned_items
            ],
        ] if learned_items else []
        if context_lines:
            contextual_user_prompt = (
                "Recent conversation:\n"
                + "\n".join(context_lines)
                + ("\n\n" + "\n".join(learning_lines) if learning_lines else "")
                + "\n\nLatest user request:\n"
                + user_prompt.strip()
            )
        elif learning_lines:
            contextual_user_prompt = (
                "\n".join(learning_lines) + "\n\nLatest user request:\n" + user_prompt.strip()
            )
        return self._load_system_prompt(workflow), contextual_user_prompt