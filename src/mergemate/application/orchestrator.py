# mypy: allow-untyped-defs
"""Workflow orchestration entrypoint."""

from mergemate.application.execution_plan import (
    ExecutionContext,
    ExecutionRuntime,
    OrchestratorDependencies,
)
from mergemate.domain.agents import get_soul
from mergemate.domain.shared import RunStage, RunStatus
from mergemate.domain.shared.exceptions import RunNotFoundError


class AgentOrchestrator:
    """Coordinates workflow selection, tools, and provider execution."""

    def __init__(
        self,
        deps: OrchestratorDependencies,
    ) -> None:
        self._deps = deps

    def _is_cancelled(self, run_id: str) -> bool:
        latest_run = self._deps.run_repository.get(run_id)
        return latest_run is not None and latest_run.status == RunStatus.CANCELLED

    async def process_run(self, run_id: str):
        run = self._deps.run_repository.get(run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id} was not found")
        if run.status in RunStatus.skip_process_statuses():
            return run
        if not run.approved:
            return run
        if run.status != RunStatus.QUEUED:
            return run

        start_decision = self._deps.run_repository.try_update_status(
            run_id,
            RunStatus.RUNNING,
            expected_current_status=RunStatus.QUEUED,
            current_stage=RunStage.RETRIEVE_CONTEXT,
        )
        run = start_decision.run
        assert run is not None
        if not start_decision.transitioned:
            return run

        recent_messages = self._deps.context_service.load_recent_messages(run.chat_id)
        if (
            recent_messages
            and recent_messages[-1]["role"] == "user"
            and recent_messages[-1]["content"] == run.prompt
        ):
            recent_messages = recent_messages[:-1]
        learned_items = self._deps.learning_service.load_grouped_learnings(
            run.chat_id,
            current_workflow=run.workflow,
        )
        repo_knowledge = self._deps.learning_service.load_repo_knowledge(
            run.chat_id,
            repo_name=run.repo_name if run.repo_name is not None else self._deps.settings.repo_name,
        )

        system_prompt, context_text = self._deps.prompt_service.render(
            run.workflow,
            recent_messages,
            learned_items,
            run.prompt,
            repo_knowledge=repo_knowledge,
        )

        # Inject role Soul definition for boundary enforcement
        system_prompt = self._inject_soul_to_prompt(system_prompt, run.agent_name)
        execution_plan = self._deps.workflow_service.build_execution_plan(
            run.workflow,
            agent_name=run.agent_name,
        )
        if execution_plan.requires_tool_context:
            tool_context = await self._deps.tool_service.build_runtime_tool_context_async(
                run.run_id,
                run.agent_name,
                resume_stage=RunStage.RETRIEVE_CONTEXT,
            )
            if tool_context:
                context_text = f"{context_text}\n\nRuntime tool context:\n{tool_context}".strip()

        runtime = ExecutionRuntime(
            deps=self._deps,
            is_cancelled=self._is_cancelled,
        )
        execution = ExecutionContext(
            run=run, system_prompt=system_prompt, context_text=context_text
        )
        return await execution_plan.execute(runtime, execution)

    @staticmethod
    def _inject_soul_to_prompt(system_prompt: str, agent_name: str) -> str:
        """Append the agent's Soul definition (role identity + boundaries)
        to the system prompt if a matching Soul is found."""
        soul = get_soul(agent_name)
        if soul is not None:
            return system_prompt + "\n\n" + soul.to_system_prompt()
        return system_prompt
