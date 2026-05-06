"""Workflow planning, design, implementation, testing, and review orchestration prompts."""

from mergemate.application.execution_plan import DirectExecutionPlan, MultiStageExecutionPlan
from mergemate.domain.shared import uses_multi_stage_delivery


class WorkflowService:
    def __init__(self, llm_gateway, settings) -> None:
        self._llm_gateway = llm_gateway
        self._settings = settings

    def build_execution_plan(self, workflow: str, *, agent_name: str) -> DirectExecutionPlan | MultiStageExecutionPlan:
        if uses_multi_stage_delivery(workflow):
            return MultiStageExecutionPlan(
                agent_name=agent_name,
                max_iterations=self._settings.workflow_control.max_review_iterations,
            )
        return DirectExecutionPlan(agent_name=agent_name)

    def resolve_stage_agent_name(self, workflow: str, *, preferred_agent_name: str | None = None) -> str:
        return self._settings.resolve_agent_name_for_workflow(
            workflow,
            preferred_agent_name=preferred_agent_name,
        )

    async def _generate_stage_output(
        self,
        workflow: str,
        system_prompt: str,
        user_prompt: str,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        agent_name = self.resolve_stage_agent_name(
            workflow,
            preferred_agent_name=preferred_agent_name,
        )
        return await self._llm_gateway.generate(agent_name, system_prompt, user_prompt)

    async def create_design(self, plan_text: str, context_text: str) -> str:
        system_prompt = (
            "You are the architect agent. Create an implementation-ready design from the approved plan. "
            "Be concrete about modules, interfaces, data flow, and testing seams."
        )
        user_prompt = f"Approved plan:\n{plan_text}\n\nRetrieved context:\n{context_text}"
        return await self._generate_stage_output("design", system_prompt, user_prompt)

    async def generate_code(
        self,
        plan_text: str,
        design_text: str,
        context_text: str,
        *,
        agent_name: str | None = None,
    ) -> str:
        system_prompt = (
            "You are the coding agent. Implement according to the approved plan and design. "
            "Return a practical implementation summary, key file changes, and important code snippets."
        )
        user_prompt = (
            f"Plan:\n{plan_text}\n\nDesign:\n{design_text}\n\nContext:\n{context_text}\n\n"
            "Produce implementation details and code-oriented output."
        )
        return await self._generate_stage_output(
            "generate_code",
            system_prompt,
            user_prompt,
            preferred_agent_name=agent_name,
        )

    async def execute_direct(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        return await self._llm_gateway.generate(agent_name, system_prompt, user_prompt)

    async def generate_tests(self, plan_text: str, design_text: str, implementation_text: str) -> str:
        system_prompt = (
            "You are the test agent. Produce tests and a validation approach for the implementation. "
            "Focus on runnable tests, edge cases, and verification steps."
        )
        user_prompt = (
            f"Plan:\n{plan_text}\n\nDesign:\n{design_text}\n\nImplementation:\n{implementation_text}"
        )
        return await self._generate_stage_output("testing", system_prompt, user_prompt)

    async def review(self, plan_text: str, design_text: str, implementation_text: str, test_text: str) -> str:
        system_prompt = (
            "You are the review agent. Review the design and implementation. "
            "Start with 'HIGH_CONCERNS: yes' if there are serious concerns, otherwise 'HIGH_CONCERNS: no'. "
            "Then provide findings, rationale, and whether replanning is required."
        )
        user_prompt = (
            f"Plan:\n{plan_text}\n\nDesign:\n{design_text}\n\nImplementation:\n{implementation_text}\n\nTests:\n{test_text}"
        )
        return await self._generate_stage_output("review", system_prompt, user_prompt)

    @staticmethod
    def has_high_concerns(review_text: str) -> bool:
        lines = review_text.strip().splitlines()
        if not lines:
            return False
        first_line = lines[0].lower()
        return first_line.startswith("high_concerns: yes")