"""Prompt assembly service placeholder."""

import json
from pathlib import Path

from mergemate.domain.policies import workflow_prompt_file


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
        repo_knowledge: list[dict[str, str]] | None = None,
    ) -> tuple[str, str]:
        context_lines = [f"{message['role'].upper()}: {message['content']}" for message in recent_messages]
        contextual_user_prompt = user_prompt.strip()
        learning_lines = self._build_learning_lines(learned_items)
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

        # Inject repo knowledge section
        if repo_knowledge:
            repo_lines = ["\nCurrent repository knowledge:"]
            for item in repo_knowledge:
                repo_lines.append(
                    f"- [{item['repo_name']}] {item['topic']}: {item['summary']}"
                )
            contextual_user_prompt += "\n" + "\n".join(repo_lines)

        return self._load_system_prompt(workflow), contextual_user_prompt

    def _build_learning_lines(self, learned_items: list[dict[str, str]]) -> list[str]:
        """Build learning context lines, mixing raw excerpts and structured lessons."""
        if not learned_items:
            return []
        lines = ["Previously successful patterns:"]
        for item in learned_items:
            lines.append(f"- Workflow: {item['workflow']}")
            lines.append(f"  Prior prompt: {item['prompt']}")
            lines.append(f"  Prior result excerpt: {item['result_excerpt']}")
            # Inject structured lessons when available
            lessons_raw = item.get("learning_lessons")
            if lessons_raw:
                try:
                    lessons = json.loads(lessons_raw)
                    if lessons.get("technical_points"):
                        lines.append(
                            f"  Key technical points: {', '.join(lessons['technical_points'])}"
                        )
                    if lessons.get("pitfalls"):
                        lines.append(
                            f"  Known pitfalls: {', '.join(lessons['pitfalls'])}"
                        )
                    if lessons.get("conclusion"):
                        lines.append(f"  Conclusion: {lessons['conclusion']}")
                except (json.JSONDecodeError, TypeError):
                    pass  # malformed JSON, silently skip
        return lines