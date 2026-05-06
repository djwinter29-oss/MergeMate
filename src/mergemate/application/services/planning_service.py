"""Planning and replanning prompts for approval-gated workflows."""


class PlanningService:
    def __init__(self, llm_gateway, settings) -> None:
        self._llm_gateway = llm_gateway
        self._settings = settings

    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        system_prompt = (
            "You are the planning and coordination agent. Capture and confirm requirements. "
            "Always produce a plan that includes design and how to test. "
            "If requirements are unclear, include direct clarification questions. "
            "You also coordinate operational decisions such as tool installation or settings updates when required."
        )
        user_prompt = (
            f"User request:\n{prompt.strip()}\n\n"
            "Return sections in this exact order:\n"
            "1. Confirmed requirements\n"
            "2. Open questions\n"
            "3. Proposed plan\n"
            "4. Design approach\n"
            "5. Test approach\n"
            "6. Approval instruction"
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