# mypy: allow-untyped-defs
"""Planning and replanning prompts for approval-gated workflows.

The planning service now produces structured task breakdowns in addition
to the free-form plan text.  Each subtask identifies an owner role so
the workflow orchestration can track completion per task.
"""

from __future__ import annotations

import re
from typing import Any


class PlanningService:
    def __init__(self, llm_gateway, settings) -> None:
        self._llm_gateway = llm_gateway
        self._settings = settings

    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        system_prompt = (
            "You are the planning and coordination agent. Capture and confirm requirements. "
            "Always produce a plan that includes design and how to test. "
            "If requirements are unclear, include direct clarification questions. "
            "You also coordinate operational decisions such as tool installation or settings updates when required.\n\n"
            "IMPORTANT: After the free-form plan, append a structured task breakdown:\n\n"
            "## Task Breakdown\n"
            "- [ ] Task name — description (@role_name)\n"
            "  One line per task. Each task must specify the role responsible "
            "in parentheses after an @ symbol.\n"
            "  Valid roles: planner, architect, coder, tester, reviewer\n"
            "  Example: \"- [ ] Design auth flow — define API endpoints and user model (@architect)\"\n"
            "- [ ] ...\n"
        )
        user_prompt = (
            f"User request:\n{prompt.strip()}\n\n"
            "Return sections in this exact order:\n"
            "1. Confirmed requirements\n"
            "2. Open questions\n"
            "3. Proposed plan\n"
            "4. Design approach\n"
            "5. Test approach\n"
            "6. Approval instruction\n"
            "7. Task Breakdown (see system prompt for format)"
        )
        if prior_feedback:
            user_prompt += f"\n\nIncorporate this feedback or reviewer concern:\n{prior_feedback.strip()}"
        return await self._llm_gateway.generate(
            self._settings.resolve_agent_name_for_workflow("planning"),
            system_prompt,
            user_prompt,
        )

    async def revise_plan(self, existing_prompt: str, feedback: str) -> tuple[str, str]:
        updated_prompt = f"{existing_prompt}\n\nAdditional user feedback:\n{feedback.strip()}"
        plan_text = await self.draft_plan(updated_prompt)
        return updated_prompt, plan_text

    @staticmethod
    def extract_tasks(plan_text: str) -> list[dict[str, Any]]:
        """Parse a structured task breakdown from the plan text.

        Returns a list of dicts with keys: ``description``, ``owner``.
        Looks for lines starting with ``- [ ]`` that contain ``(@role)``.
        """
        tasks: list[dict[str, Any]] = []
        in_breakdown = False
        for raw_line in plan_text.splitlines():
            line = raw_line.strip()
            if line.lower().startswith("## task breakdown"):
                in_breakdown = True
                continue
            if not in_breakdown:
                continue
            # Stop at the next section heading
            if line.startswith("#") and not line.startswith("## task"):
                break
            match = re.match(r"^- \[.?\] (.+?)\(@(\w+)\)\s*$", line)
            if match:
                tasks.append({
                    "description": match.group(1).strip(),
                    "owner": match.group(2).strip(),
                })
        return tasks

    @staticmethod
    def build_progress_summary(
        tasks: list[dict[str, Any]],
        completed_tasks: list[str],
    ) -> str:
        """Build a human-readable progress summary from the task list.

        ``completed_tasks`` is a list of owner role names that have been
        successfully processed.
        """
        if not tasks:
            return ""
        lines = ["## Progress Summary\n"]
        for task in tasks:
            owner = task.get("owner", "?")
            done = "✅" if owner in completed_tasks else "❌"
            lines.append(f"- {done} {task['description']} (@{owner})")
        done_count = sum(1 for t in tasks if t["owner"] in completed_tasks)
        lines.append(f"\n**{done_count}/{len(tasks)} tasks completed**")
        return "\n".join(lines)