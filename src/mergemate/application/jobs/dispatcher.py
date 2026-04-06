"""Dispatch accepted work to the background worker."""

from dataclasses import dataclass

from mergemate.domain.runs.value_objects import RunJobType


@dataclass(slots=True)
class DispatchResult:
    run_id: str
    job_id: str
    status: str
    created: bool


class RunDispatcher:
    def __init__(self, run_job_repository, queue_backend) -> None:
        self._run_job_repository = run_job_repository
        self._queue_backend = queue_backend

    def dispatch_run(
        self,
        run_id: str,
        *,
        job_type: RunJobType = RunJobType.EXECUTE_RUN,
    ) -> DispatchResult:
        decision = self._run_job_repository.ensure_queued_job(run_id, job_type=job_type)
        job = decision.job
        if job is None:
            raise RuntimeError(f"Unable to queue background job for run {run_id}.")
        self._queue_backend.enqueue(job.job_id)
        return DispatchResult(
            run_id=run_id,
            job_id=job.job_id,
            status=job.status.value,
            created=decision.created,
        )