"""Workflow orchestration entrypoint."""

from mergemate.application.execution_plan import ExecutionContext, ExecutionRuntime
from mergemate.domain.runs.value_objects import RunStatus


class AgentOrchestrator:
    """Coordinates workflow selection, tools, and provider execution."""

    def __init__(
        self,
        run_repository,
        context_service,
        documentation_service,
        learning_service,
        prompt_service,
        tool_service,
        workflow_service,
        llm_gateway,
        settings,
    ) -> None:
        self._run_repository = run_repository
        self._context_service = context_service
        self._documentation_service = documentation_service
        self._learning_service = learning_service
        self._prompt_service = prompt_service
        self._tool_service = tool_service
        self._workflow_service = workflow_service
        self._llm_gateway = llm_gateway
        self._settings = settings

    def _is_cancelled(self, run_id: str) -> bool:
        latest_run = self._run_repository.get(run_id)
        return latest_run is not None and latest_run.status == RunStatus.CANCELLED

    async def process_run(self, run_id: str):
        run = self._run_repository.get(run_id)
        if run is None:
            raise ValueError(f"Run {run_id} was not found")
        if run.status == RunStatus.CANCELLED:
            return run
        if not run.approved:
            return run

        run = self._run_repository.update_status(
            run_id,
            RunStatus.RUNNING,
            current_stage="retrieve_context",
        )
        assert run is not None

        recent_messages = self._context_service.load_recent_messages(run.chat_id)
        if recent_messages and recent_messages[-1]["role"] == "user" and recent_messages[-1]["content"] == run.prompt:
            recent_messages = recent_messages[:-1]
        learned_items = self._learning_service.load_recent_learnings(run.chat_id)

        system_prompt, context_text = self._prompt_service.render(
            run.workflow,
            recent_messages,
            learned_items,
            run.prompt,
        )
        execution_plan = self._workflow_service.build_execution_plan(
            run.workflow,
            agent_name=run.agent_name,
        )
        if execution_plan.requires_tool_context:
            tool_context = self._tool_service.build_runtime_tool_context(
                run.run_id,
                run.agent_name,
                resume_stage="retrieve_context",
            )
            if tool_context:
                context_text = f"{context_text}\n\nRuntime tool context:\n{tool_context}".strip()

        runtime = ExecutionRuntime(
            run_repository=self._run_repository,
            context_service=self._context_service,
            documentation_service=self._documentation_service,
            learning_service=self._learning_service,
            workflow_service=self._workflow_service,
            settings=self._settings,
            is_cancelled=self._is_cancelled,
        )
        execution = ExecutionContext(run=run, system_prompt=system_prompt, context_text=context_text)
        return await execution_plan.execute(runtime, execution)