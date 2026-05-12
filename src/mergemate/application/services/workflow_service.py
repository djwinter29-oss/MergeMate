# mypy: allow-untyped-defs
"""Workflow planning, design, implementation, testing, and review orchestration prompts."""

import asyncio
from typing import Any

from mergemate.application.execution_plan import DirectExecutionPlan, MultiStageExecutionPlan
from mergemate.domain.policies import uses_multi_stage_delivery
from mergemate.domain.shared.enums import WorkflowName
from mergemate.domain.shared.exceptions import ParallelWorkerError
from mergemate.domain.workflows.stage import get_workflow_definitions


class WorkflowService:
    def __init__(self, llm_gateway, settings) -> None:
        self._llm_gateway = llm_gateway
        self._settings = settings

    def build_execution_plan(
        self, workflow: str, *, agent_name: str
    ) -> DirectExecutionPlan | MultiStageExecutionPlan:
        if uses_multi_stage_delivery(workflow):
            wf_def = get_workflow_definitions().get(WorkflowName(workflow))
            return MultiStageExecutionPlan(
                agent_name=agent_name,
                max_iterations=self._settings.workflow_control.max_review_iterations,
                workflow_definition=wf_def,
            )
        return DirectExecutionPlan(agent_name=agent_name)

    async def _generate_stage_output(
        self,
        workflow: str,
        system_prompt: str,
        user_prompt: str,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        agent_name = self._settings.resolve_agent_name_for_workflow(
            workflow,
            preferred_agent_name=preferred_agent_name,
        )
        role_config = getattr(self._settings, "roles", None)
        if role_config is not None:
            role_config = role_config.get(agent_name)
        if (
            role_config is not None
            and role_config.parallel_mode == "parallel"
            and len(role_config.workers) > 1
        ):
            return await self._run_parallel_stage(
                workflow=workflow,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                role_config=role_config,
                preferred_agent_name=preferred_agent_name,
            )
        return await self._llm_gateway.generate(agent_name, system_prompt, user_prompt)

    async def _run_parallel_stage(
        self,
        workflow: str,
        system_prompt: str,
        user_prompt: str,
        role_config: Any,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        """Run multiple workers in parallel and combine results."""

        async def _run_worker(worker_name: str) -> str:
            agent_name = self._settings.resolve_agent_name_for_workflow(
                workflow,
                preferred_agent_name=preferred_agent_name or worker_name,
            )
            return await self._llm_gateway.generate(agent_name, system_prompt, user_prompt)

        worker_names = [w.name for w in role_config.workers]
        raw_results: list[Any] = await asyncio.gather(
            *[_run_worker(name) for name in worker_names],
            return_exceptions=True,
        )

        non_error_results = [r for r in raw_results if not isinstance(r, Exception)]

        if not non_error_results:
            err_msgs = [str(r) for r in raw_results if isinstance(r, Exception)]
            raise ParallelWorkerError(f"All parallel workers failed: {'; '.join(err_msgs)}")

        strategy = role_config.combine_strategy or "sectioned"
        if strategy == "first_success":
            return non_error_results[0]

        # sectioned: join results with worker name headers
        output_parts: list[str] = []
        for name, result in zip(worker_names, raw_results):
            if isinstance(result, Exception):
                output_parts.append(f"## {name} (FAILED)\n{result}")
            else:
                output_parts.append(f"## {name}\n{result}")
        return "\n\n".join(output_parts)

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

    async def generate_tests(
        self, plan_text: str, design_text: str, implementation_text: str
    ) -> str:
        system_prompt = (
            "You are the test agent. Produce tests and a validation approach for the implementation. "
            "Focus on runnable tests, edge cases, and verification steps."
        )
        user_prompt = f"Plan:\n{plan_text}\n\nDesign:\n{design_text}\n\nImplementation:\n{implementation_text}"
        return await self._generate_stage_output("testing", system_prompt, user_prompt)

    async def review(
        self, plan_text: str, design_text: str, implementation_text: str, test_text: str
    ) -> str:
        system_prompt = (
            "You are the review agent. Review the design and implementation. "
            "Start with 'HIGH_CONCERNS: yes' if there are serious concerns, otherwise 'HIGH_CONCERNS: no'. "
            "Then provide findings, rationale, and whether replanning is required."
        )
        user_prompt = f"Plan:\n{plan_text}\n\nDesign:\n{design_text}\n\nImplementation:\n{implementation_text}\n\nTests:\n{test_text}"
        return await self._generate_stage_output("review", system_prompt, user_prompt)

    async def record_lesson(
        self,
        *,
        plan_text: str = "",
        design_text: str = "",
        implementation_text: str = "",
        test_text: str = "",
        review_text: str = "",
        result_text: str = "",
        error_text: str = "",
        agent_name: str = "",
    ) -> str:
        """Record a lesson-learned entry for the current workflow run.

        This is the chronicler role — it reflects on what happened and
        extracts experiences, pitfalls, and best practices to persist.
        """
        parts = []
        for label, text in [
            ("Plan", plan_text),
            ("Design", design_text),
            ("Implementation", implementation_text),
            ("Tests", test_text),
            ("Review", review_text),
            ("Result", result_text),
        ]:
            if text:
                parts.append(f"## {label}\n{text.strip()}")
        if error_text:
            parts.append(f"## Error\n{error_text.strip()}")

        user_prompt = (
            "Review the following workflow artifacts and produce a brief "
            "lessons-learned summary. Include:\n\n"
            "**Lessons Learned** — what went well, what could be improved\n"
            "**Pitfalls to Avoid** — mistakes, gotchas, anti-patterns\n"
            "**Best Practices** — conventions and patterns to reuse\n\n"
            "Be concise and concrete.\n\n" + "\n\n".join(parts)
        )
        return await self._generate_stage_output(
            "learning",
            "You are an experience recordist. Extract lessons, pitfalls, and best practices "
            "from the artifacts below.",
            user_prompt,
            preferred_agent_name=agent_name or None,
        )

    @staticmethod
    def has_high_concerns(review_text: str) -> bool:
        lines = review_text.strip().splitlines()
        if not lines:
            return False
        first_line = lines[0].lower()
        return first_line.startswith("high_concerns: yes")
