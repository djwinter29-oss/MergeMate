from mergemate.application.jobs.dispatcher import RunDispatcher
from mergemate.domain.runs.value_objects import RunJobType
from mergemate.domain.runs.value_objects import RunJobStatus


class QueueBackendStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enqueue(self, job_id: str) -> bool:
        self.calls.append(job_id)
        return True


class RunJobRepositoryStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, RunJobType]] = []

    def ensure_queued_job(self, run_id: str, *, job_type=RunJobType.EXECUTE_RUN):
        self.calls.append((run_id, job_type))

        class Job:
            job_id = f"job-for-{run_id}"
            status = RunJobStatus.QUEUED

        class Decision:
            job = Job()
            created = True

        return Decision()
def test_dispatch_run_enqueues_work_and_returns_result() -> None:
    queue_backend = QueueBackendStub()
    run_job_repository = RunJobRepositoryStub()
    dispatcher = RunDispatcher(run_job_repository, queue_backend)

    result = dispatcher.dispatch_run("run-42")

    assert result.run_id == "run-42"
    assert result.job_id == "job-for-run-42"
    assert result.status == "queued"
    assert result.created is True
    assert run_job_repository.calls == [("run-42", RunJobType.EXECUTE_RUN)]
    assert queue_backend.calls == ["job-for-run-42"]
