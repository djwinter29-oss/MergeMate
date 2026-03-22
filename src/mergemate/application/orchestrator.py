"""Workflow orchestration entrypoint."""

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
        workflow_service,
        llm_gateway,
        settings,
    ) -> None:
        self._run_repository = run_repository
        self._context_service = context_service
        self._documentation_service = documentation_service
        self._learning_service = learning_service
        self._prompt_service = prompt_service
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

        _, context_text = self._prompt_service.render(run.workflow, recent_messages, learned_items, run.prompt)

        max_iterations = self._settings.workflow_control.max_review_iterations
        current_plan = run.plan_text or "No approved plan available."
        implementation_text = ""
        test_text = ""
        review_text = ""
        design_document_path = ""
        test_document_path = ""
        review_document_path = ""

        for iteration in range(1, max_iterations + 1):
            if self._is_cancelled(run_id):
                return self._run_repository.get(run_id)

            design_text = await self._workflow_service.create_design(current_plan, context_text)
            design_document_path = str(
                self._documentation_service.write_architecture_design(
                    run_id=run_id,
                    iteration=iteration,
                    plan_text=current_plan,
                    design_text=design_text,
                )
            )
            self._run_repository.save_artifacts(
                run_id,
                current_stage="design",
                design_text=design_text,
                review_iterations=iteration,
            )
            if self._is_cancelled(run_id):
                return self._run_repository.get(run_id)

            implementation_text = await self._workflow_service.generate_code(
                current_plan,
                design_text,
                context_text,
            )
            self._run_repository.save_artifacts(
                run_id,
                current_stage="implementation",
                result_text=implementation_text,
                review_iterations=iteration,
            )
            if self._is_cancelled(run_id):
                return self._run_repository.get(run_id)

            test_text = await self._workflow_service.generate_tests(
                current_plan,
                design_text,
                implementation_text,
            )
            test_document_path = str(
                self._documentation_service.write_test_plan(
                    run_id=run_id,
                    iteration=iteration,
                    plan_text=current_plan,
                    design_text=design_text,
                    test_text=test_text,
                )
            )
            self._run_repository.save_artifacts(
                run_id,
                current_stage="testing",
                test_text=test_text,
                review_iterations=iteration,
            )
            if self._is_cancelled(run_id):
                return self._run_repository.get(run_id)

            review_text = await self._workflow_service.review(
                current_plan,
                design_text,
                implementation_text,
                test_text,
            )
            review_document_path = str(
                self._documentation_service.write_review_report(
                    run_id=run_id,
                    iteration=iteration,
                    plan_text=current_plan,
                    design_text=design_text,
                    implementation_text=implementation_text,
                    test_text=test_text,
                    review_text=review_text,
                )
            )
            self._run_repository.save_artifacts(
                run_id,
                current_stage="review",
                review_text=review_text,
                review_iterations=iteration,
            )
            if self._is_cancelled(run_id):
                return self._run_repository.get(run_id)

            if not self._workflow_service.has_high_concerns(review_text):
                break

            if iteration >= max_iterations:
                break

            current_plan = await self._workflow_service.draft_plan(run.prompt, prior_feedback=review_text)
            self._run_repository.update_plan(
                run_id,
                current_plan,
                current_stage="internal_replanning",
            )
            if self._is_cancelled(run_id):
                return self._run_repository.get(run_id)

        latest_run = self._run_repository.get(run_id)
        if latest_run is not None and latest_run.status == RunStatus.CANCELLED:
            return latest_run

        final_result = (
            f"Approved plan:\n{current_plan}\n\n"
            f"Design document:\n{design_document_path}\n\n"
            f"Test plan document:\n{test_document_path}\n\n"
            f"Review report:\n{review_document_path}\n\n"
            f"Design:\n{latest_run.design_text if latest_run and latest_run.design_text else ''}\n\n"
            f"Implementation:\n{implementation_text}\n\n"
            f"Tests:\n{test_text}\n\n"
            f"Review:\n{review_text}"
        ).strip()

        self._context_service.append_message(run.chat_id, "assistant", final_result)
        self._learning_service.remember_success(
            chat_id=run.chat_id,
            workflow=run.workflow,
            prompt=run.prompt,
            result_text=final_result,
        )
        completed_run = self._run_repository.update_status(
            run_id,
            RunStatus.COMPLETED,
            current_stage="completed",
            result_text=final_result,
        )
        assert completed_run is not None
        return completed_run