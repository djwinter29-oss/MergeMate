"""Approve a planned run and dispatch it for execution."""


class ApproveRunUseCase:
    def __init__(self, submit_prompt_use_case) -> None:
        self._submit_prompt_use_case = submit_prompt_use_case

    def execute(self, run_id: str, *, chat_id: int | None = None, on_finished=None):
        return self._submit_prompt_use_case.approve(run_id, chat_id=chat_id, on_finished=on_finished)