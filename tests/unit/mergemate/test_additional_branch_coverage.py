from __future__ import annotations

import asyncio
import io
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from mergemate.application.jobs.dispatcher import RunDispatcher
from mergemate.application.orchestrator import AgentOrchestrator
from mergemate.application.services.tool_service import ToolService
from mergemate.application.services.workflow_service import WorkflowService
from mergemate.application.use_cases.cancel_run import CancelRunUseCase
from mergemate.application.use_cases.submit_prompt import PromptSubmissionError, SubmitPromptUseCase
from mergemate.cli import _probe_readiness_once
from mergemate.config import loader as loader_module
from mergemate.config.loader import _discover_default_local_config_path
from mergemate.config.models import AppConfig
from mergemate.domain.runs.repository import ApprovalDecision
from mergemate.domain.shared import RunJobType, RunStage, RunStatus
from mergemate.domain.shared.exceptions import JobQueueError
from mergemate.domain.tools.entities import ToolMetadata
from mergemate.infrastructure.persistence.sqlite import SQLiteRunJobRepository
from mergemate.interfaces.telegram import bot as telegram_bot
from mergemate.interfaces.telegram import handlers as telegram_handlers
from mergemate.interfaces.telegram.health import WebhookHealthServer, WebhookReadinessState
from mergemate.interfaces.telegram.progress_notifier import _format_terminal_update


class QueueBackendStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.calls.append(job_id)


class RunJobRepositoryWithMissingJob:
    def ensure_queued_job(self, run_id: str, *, job_type=RunJobType.EXECUTE_RUN):
        class Decision:
            job = None
            created = False

        return Decision()


class OrchestratorRunRepositoryStub:
    def __init__(self, run) -> None:
        self.run = run
        self.transition_result = None

    def get(self, run_id: str):
        return self.run if self.run.run_id == run_id else None

    def try_update_status(self, run_id: str, status: RunStatus, *, expected_current_status=None, current_stage=None):
        return self.transition_result


class ToolStub:
    def __init__(self, response: dict[str, str], metadata: ToolMetadata) -> None:
        self.response = response
        self.metadata = metadata
        self.payloads: list[dict[str, str]] = []

    def invoke(self, payload: dict[str, str]) -> dict[str, str]:
        self.payloads.append(payload)
        return self.response


class ToolRegistryStub:
    def __init__(self, tools: dict[str, ToolStub]) -> None:
        self.tools = tools

    def get_tool(self, name: str):
        return self.tools.get(name)

    def get_tool_metadata(self, name: str):
        tool = self.tools.get(name)
        return None if tool is None else tool.metadata

    def list_tools(self):
        return list(self.tools)


class RunRepositoryStub:
    def __init__(self) -> None:
        self.runs: dict[str, object] = {}
        self.updated_plans: list[tuple[str, str]] = []
        self.approve_result = ApprovalDecision(run=None, transitioned=False)
        self.try_update_result = SimpleNamespace(run=None, transitioned=False)

    def get(self, run_id: str):
        return self.runs.get(run_id)

    def create(self, run) -> None:
        self.runs[run.run_id] = run

    def update_plan(self, run_id: str, plan_text: str, prompt: str | None = None, *, current_stage: str | None = None):
        run = self.runs.get(run_id)
        if run is None:
            return None
        run.plan_text = plan_text
        if prompt is not None:
            run.prompt = prompt
        if current_stage is not None:
            run.current_stage = current_stage
        self.updated_plans.append((run_id, plan_text))
        return run

    def update_status(self, run_id: str, status: RunStatus, *, expected_current_status=None, current_stage=None, result_text=None, error_text=None):
        run = self.runs.get(run_id)
        if run is None:
            return None
        run.status = status
        if current_stage is not None:
            run.current_stage = current_stage
        if error_text is not None:
            run.error_text = error_text
        return run

    def try_update_status(self, run_id: str, status: RunStatus, *, expected_current_status=None, current_stage=None, result_text=None, error_text=None):
        return self.try_update_result

    def approve(self, run_id: str):
        return self.approve_result


class ContextServiceStub:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, str]] = []

    def append_message(self, chat_id: int, role: str, content: str) -> None:
        self.messages.append((chat_id, role, content))


class PlanningServiceStub:
    async def draft_plan(self, prompt: str, prior_feedback: str | None = None) -> str:
        return f"plan for {prompt}"


class GatewayStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def generate(self, agent_name: str, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((agent_name, system_prompt, user_prompt))
        return f"response-from-{agent_name}"


class ReadinessStateSpy:
    def __init__(self) -> None:
        self.statuses: list[str] = []

    def mark_ready(self) -> None:
        self.statuses.append("ready")

    def mark_stopping(self) -> None:
        self.statuses.append("stopping")


class WorkerSpy:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class BotStub:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.messages.append((chat_id, text))


class ApplicationStub:
    def __init__(self, runtime) -> None:
        self.bot_data = {"runtime": runtime}
        self.bot = BotStub()
        self.created_tasks = []

    def create_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.created_tasks.append(task)
        return task


class MessageStub:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class UpdateStub:
    def __init__(self, message: MessageStub | None) -> None:
        self.effective_message = message
        self.effective_user = SimpleNamespace(id=3)
        self.effective_chat = SimpleNamespace(id=5)


class ContextStub:
    def __init__(self, application: ApplicationStub) -> None:
        self.application = application
        self.args: list[str] = []


class SubmitPromptStub:
    def __init__(self, execute_result=None, complete_result=None, complete_error: Exception | None = None) -> None:
        self.execute_result = execute_result
        self.complete_result = complete_result
        self.complete_error = complete_error
        self.execute_calls = []
        self.complete_calls = []

    async def execute(self, **kwargs):
        self.execute_calls.append(kwargs)
        return self.execute_result

    async def complete_planning(self, run_id: str):
        self.complete_calls.append(run_id)
        if self.complete_error is not None:
            raise self.complete_error
        return self.complete_result


class GetRunStatusStub:
    def __init__(self, results=None) -> None:
        self.results = list(results or [])

    def execute(self, **kwargs):
        return self.results.pop(0) if self.results else None


class TelegramRuntimeStub:
    def __init__(self, settings, *, worker=None, lifecycle_notifier=None) -> None:
        self.settings = settings
        self.worker = worker
        self.lifecycle_notifier = lifecycle_notifier


class RuntimeSettingsStub:
    def __init__(self, *, mode: str = "polling") -> None:
        self.default_provider = "openai"
        self.default_agent = "coder"
        self.telegram = SimpleNamespace(
            mode=mode,
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
            webhook_listen_host="127.0.0.1",
            webhook_listen_port=9443,
            webhook_path="/telegram/webhook",
        )
        self.agents = {"coder": SimpleNamespace(workflow="generate_code")}

    def resolve_telegram_token(self) -> str:
        return "token"

    def resolve_telegram_webhook_url(self) -> str:
        return "https://bot.example.com/telegram/webhook"

    def resolve_telegram_webhook_secret_token(self) -> str:
        return "secret"

    def resolve_provider_api_key(self, provider_name: str | None = None) -> str:
        return "provider-token"

    def resolve_agent_provider_names(self, agent_name: str) -> list[str]:
        return ["openai"]

    def resolve_agent_name_for_workflow(self, workflow: str, *, preferred_agent_name: str | None = None) -> str:
        return preferred_agent_name or "planner"

    def preview_database_path(self, resolved_path: Path) -> Path:
        return Path("/tmp/runtime.db")


class BrokenConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        raise sqlite3.IntegrityError("duplicate")


class BrokenDatabase:
    def connection(self):
        return BrokenConnection()


class LearningSettingsStub:
    def __init__(self, roles=None, agents=None):
        self.roles = roles or {}
        self.agents = agents or {}

    def resolve_agent_name_for_workflow(self, workflow: str, *, preferred_agent_name: str | None = None) -> str:
        return preferred_agent_name or "learning"


@pytest.mark.asyncio
async def test_dispatcher_raises_when_queue_repository_returns_no_job() -> None:
    dispatcher = RunDispatcher(RunJobRepositoryWithMissingJob(), QueueBackendStub())

    with pytest.raises(JobQueueError, match="Unable to queue background job for run run-99"):
        dispatcher.dispatch_run("run-99")


@pytest.mark.asyncio
async def test_orchestrator_returns_early_for_non_queued_run() -> None:
    run = SimpleNamespace(run_id="run-1", status=RunStatus.RUNNING, approved=True)
    repo = OrchestratorRunRepositoryStub(run)
    deps = SimpleNamespace(
        run_repository=repo,
        context_service=SimpleNamespace(load_recent_messages=lambda _chat_id: []),
        documentation_service=SimpleNamespace(),
        learning_service=SimpleNamespace(load_recent_learnings=lambda _chat_id: []),
        planning_service=SimpleNamespace(),
        prompt_service=SimpleNamespace(render=lambda *args: ("system", "context")),
        tool_service=SimpleNamespace(build_runtime_tool_context_async=lambda *args, **kwargs: ""),
        workflow_service=SimpleNamespace(build_execution_plan=lambda *args, **kwargs: None),
        llm_gateway=SimpleNamespace(),
        settings=SimpleNamespace(),
    )
    orchestrator = AgentOrchestrator(deps)

    result = await orchestrator.process_run("run-1")

    assert result is run


@pytest.mark.asyncio
async def test_orchestrator_returns_run_when_transition_does_not_happen() -> None:
    run = SimpleNamespace(run_id="run-1", status=RunStatus.QUEUED, approved=True, chat_id=1, prompt="prompt", workflow="generate_code", agent_name="coder")
    repo = OrchestratorRunRepositoryStub(run)
    repo.transition_result = SimpleNamespace(run=run, transitioned=False)
    deps = SimpleNamespace(
        run_repository=repo,
        context_service=SimpleNamespace(load_recent_messages=lambda _chat_id: []),
        documentation_service=SimpleNamespace(),
        learning_service=SimpleNamespace(load_recent_learnings=lambda _chat_id: []),
        planning_service=SimpleNamespace(),
        prompt_service=SimpleNamespace(render=lambda *args: ("system", "context")),
        tool_service=SimpleNamespace(build_runtime_tool_context_async=lambda *args, **kwargs: ""),
        workflow_service=SimpleNamespace(build_execution_plan=lambda *args, **kwargs: None),
        llm_gateway=SimpleNamespace(),
        settings=SimpleNamespace(),
    )
    orchestrator = AgentOrchestrator(deps)

    result = await orchestrator.process_run("run-1")

    assert result is run


def test_tool_service_skips_resume_transition_when_current_run_is_not_waiting_tool() -> None:
    run = SimpleNamespace(status=RunStatus.RUNNING)
    run_repo = SimpleNamespace(get=lambda _run_id: run, try_update_status=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not transition")))
    service = ToolService(
        ToolRegistryStub({}),
        SimpleNamespace(source_control=SimpleNamespace(default_platform="github"), agents={}),
        run_repository=run_repo,
    )

    service._transition_run_for_tool(
        "run-1",
        blocks_run_state=RunStatus.WAITING_TOOL.value,
        tool_name="tool",
        resume_stage=RunStage.RETRIEVE_CONTEXT,
        entering=False,
    )


def test_tool_service_skips_repository_context_metadata_for_other_platforms() -> None:
    github_meta = ToolMetadata(
        name="github_context",
        runtime_mode="context",
        default_action="status",
        read_only=True,
        context_key="github",
        platform="github",
    )
    gitlab_meta = ToolMetadata(
        name="gitlab_context",
        runtime_mode="context",
        default_action="status",
        read_only=True,
        context_key="gitlab",
        platform="gitlab",
    )
    service = ToolService(
        ToolRegistryStub(
            {
                "github_context": ToolStub({"status": "ok", "detail": "github"}, github_meta),
                "gitlab_context": ToolStub({"status": "ok", "detail": "gitlab"}, gitlab_meta),
            }
        ),
        SimpleNamespace(source_control=SimpleNamespace(default_platform="github"), agents={}),
    )

    names = [name for name, _metadata in service._iter_repository_context_metadata("github")]

    assert names == ["github_context"]


@pytest.mark.asyncio
async def test_workflow_service_record_lesson_includes_error_section() -> None:
    gateway = GatewayStub()
    settings = LearningSettingsStub()
    service = WorkflowService(gateway, settings)

    result = await service.record_lesson(plan_text="plan", error_text="boom", agent_name="planner")

    assert result == "response-from-planner"
    assert "## Error\nboom" in gateway.calls[0][2]


def test_cancel_run_returns_none_when_repository_update_clears_run() -> None:
    repository = SimpleNamespace(
        get=lambda _run_id: SimpleNamespace(run_id="run-1", chat_id=10, status=RunStatus.AWAITING_CONFIRMATION),
        try_update_status=lambda *args, **kwargs: SimpleNamespace(run=None, transitioned=False),
    )
    use_case = CancelRunUseCase(repository)

    assert use_case.execute("run-1", chat_id=10) is None


@pytest.mark.asyncio
async def test_submit_prompt_complete_planning_returns_none_when_run_missing() -> None:
    repository = RunRepositoryStub()
    use_case = SubmitPromptUseCase(repository, ContextServiceStub(), SimpleNamespace(dispatch_run=lambda *args, **kwargs: None), PlanningServiceStub(), SimpleNamespace(workflow_control=SimpleNamespace(require_confirmation=False)))

    assert await use_case.complete_planning("missing") is None


@pytest.mark.asyncio
async def test_submit_prompt_complete_planning_raises_when_approval_missing_before_dispatch() -> None:
    repository = RunRepositoryStub()
    run = SimpleNamespace(
        run_id="run-1",
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.QUEUED,
        current_stage=RunStage.PLANNING,
        prompt="build feature",
        estimate_seconds=30,
        plan_text=None,
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text=None,
        error_text=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.create(run)
    repository.approve_result = ApprovalDecision(run=None, transitioned=False)
    use_case = SubmitPromptUseCase(repository, ContextServiceStub(), SimpleNamespace(dispatch_run=lambda *args, **kwargs: None), PlanningServiceStub(), SimpleNamespace(workflow_control=SimpleNamespace(require_confirmation=False)))

    with pytest.raises(PromptSubmissionError, match="approval failed before dispatch"):
        await use_case.complete_planning("run-1")


def test_submit_prompt_approve_returns_non_transitioned_result_when_approval_does_not_transition() -> None:
    repository = RunRepositoryStub()
    run = SimpleNamespace(
        run_id="run-1",
        chat_id=1,
        user_id=2,
        agent_name="coder",
        workflow="generate_code",
        status=RunStatus.AWAITING_CONFIRMATION,
        current_stage=RunStage.PLANNING,
        prompt="build feature",
        estimate_seconds=30,
        plan_text="plan",
        design_text=None,
        test_text=None,
        review_text=None,
        review_iterations=0,
        approved=False,
        result_text=None,
        error_text=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repository.create(run)
    repository.approve_result = ApprovalDecision(run=run, transitioned=False)
    use_case = SubmitPromptUseCase(repository, ContextServiceStub(), SimpleNamespace(dispatch_run=lambda *args, **kwargs: None), PlanningServiceStub(), SimpleNamespace(workflow_control=SimpleNamespace(require_confirmation=False)))

    result = use_case.approve("run-1")

    assert result is not None
    assert result.dispatched is False
    assert result.status == RunStatus.AWAITING_CONFIRMATION.value


@pytest.mark.asyncio
async def test_cli_probe_readiness_handles_invalid_json_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(_url, timeout):
        raise HTTPError("http://example.com", 500, "boom", hdrs=None, fp=io.BytesIO(b"not-json"))

    monkeypatch.setattr("mergemate.cli.urlopen", fake_urlopen)

    body, payload, is_ready = _probe_readiness_once("http://example.com", timeout_seconds=1.0)

    assert body == "not-json"
    assert payload == {"status": "http_error", "detail": "not-json"}
    assert is_ready is False


def test_loader_falls_back_to_cwd_when_no_pyproject_is_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader_module, "PACKAGE_DEFAULTS_PATH", tmp_path / "package" / "defaults.yaml")
    monkeypatch.chdir(tmp_path)

    assert _discover_default_local_config_path() == tmp_path / "config" / "config.yaml"


def _build_config_with_roles() -> AppConfig:
    return AppConfig.model_validate(
        {
            "default_agent": "coder",
            "default_provider": "primary",
            "providers": {
                "primary": {"api_key_env": "PRIMARY_KEY", "model": "gpt-5.4"},
                "secondary": {"api_key_env": "SECONDARY_KEY", "model": "gpt-4.1"},
            },
            "telegram": {"bot_token_env": "TELEGRAM_TOKEN"},
            "storage": {"workspace_root": "workspace", "database_path": ".state/runtime.db"},
            "source_control": {"working_directory": "repo"},
            "runtime": {"max_concurrent_runs": 2},
            "agents": {
                "planner": {"workflow": "planning"},
                "architect": {"workflow": "design"},
                "coder": {"workflow": "generate_code", "provider_names": ["secondary"]},
                "tester": {"workflow": "testing"},
                "reviewer": {"workflow": "review"},
                "explainer": {"workflow": "explain_code"},
            },
        }
    )


def test_config_model_resolves_roles_and_agent_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _build_config_with_roles()
    config.roles["planner"].provider_names = ["role-provider"]
    config.agents["coder"].provider_names = ["secondary"]

    assert config.resolve_agent_provider_names("planner") == ["role-provider"]
    assert config.resolve_agent_provider_names("coder") == ["secondary"]
    assert config.resolve_agent_provider_names("missing") == ["primary"]

    assert config.resolve_agent_name_for_workflow("planning", preferred_agent_name="planner") == "planner"
    assert config.resolve_agent_name_for_workflow("planning", preferred_agent_name="architect") == "planner"

    config.roles = {}
    assert config.resolve_agent_name_for_workflow("generate_code", preferred_agent_name="coder") == "coder"
    assert config.resolve_agent_name_for_workflow("generate_code", preferred_agent_name="missing") == "coder"


@pytest.mark.asyncio
async def test_bot_stop_runtime_tasks_marks_readiness_state_and_stops_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    readiness_state = ReadinessStateSpy()
    worker = WorkerSpy()
    runtime = TelegramRuntimeStub(RuntimeSettingsStub(), worker=worker)
    application = ApplicationStub(runtime)
    application.bot_data["webhook_readiness_state"] = readiness_state
    monkeypatch.setattr(telegram_bot, "stop_progress_watchers", lambda _application: asyncio.sleep(0))

    await telegram_bot.stop_runtime_tasks(application)

    assert readiness_state.statuses == ["stopping"]
    assert worker.stopped is True


def test_bot_build_application_stores_readiness_state(monkeypatch: pytest.MonkeyPatch) -> None:
    builder_application = SimpleNamespace(bot_data={}, handlers=[], add_handler=lambda handler: None)

    class BuilderStub:
        def token(self, value: str):
            return self

        def post_init(self, callback):
            return self

        def post_stop(self, callback):
            return self

        def post_shutdown(self, callback):
            return self

        def build(self):
            return builder_application

    class FilterStub:
        def __init__(self, name: str) -> None:
            self.name = name

        def __and__(self, other):
            return FilterStub(f"({self.name}&{other.name})")

        def __invert__(self):
            return FilterStub(f"~{self.name}")

    monkeypatch.setattr(telegram_bot, "ApplicationBuilder", lambda: BuilderStub())
    monkeypatch.setattr(telegram_bot, "CommandHandler", lambda name, fn: (name, fn.__name__))
    monkeypatch.setattr(telegram_bot, "MessageHandler", lambda *_args: ("message", "handle_prompt"))
    monkeypatch.setattr(telegram_bot, "filters", SimpleNamespace(TEXT=FilterStub("text"), COMMAND=FilterStub("command")))

    runtime = TelegramRuntimeStub(RuntimeSettingsStub())
    bot_runtime = telegram_bot.TelegramBotRuntime(runtime)
    readiness_state = ReadinessStateSpy()

    application = bot_runtime.build_application(readiness_state=readiness_state)

    assert application.bot_data["webhook_readiness_state"] is readiness_state


def test_health_server_start_is_idempotent_and_stop_is_safe_when_not_started() -> None:
    state = WebhookReadinessState()
    server = WebhookHealthServer(listen_host="127.0.0.1", listen_port=0, path="/healthz", state=state)

    server.start()
    first_port = server.listen_port
    server.start()
    assert server.listen_port == first_port
    server.stop()

    not_started = WebhookHealthServer(listen_host="127.0.0.1", listen_port=0, path="/healthz", state=state)
    not_started.stop()


def test_progress_notifier_formats_cancelled_and_failed_terminal_updates() -> None:
    cancelled = SimpleNamespace(status=RunStatus.CANCELLED, run_id="run-1")
    failed = SimpleNamespace(status=RunStatus.FAILED, run_id="run-2", error_text="boom")

    assert "run-1" in _format_terminal_update(cancelled)
    assert "boom" in _format_terminal_update(failed)


@pytest.mark.asyncio
async def test_handlers_send_confirmation_when_plan_text_is_present() -> None:
    run = SimpleNamespace(
        run_id="run-1",
        status=RunStatus.AWAITING_CONFIRMATION,
        plan_text="approved plan",
        estimate_seconds=15,
        chat_id=5,
        created_at="now",
        current_stage="planning",
        review_iterations=0,
        approved=False,
        result_text=None,
    )
    submit = SubmitPromptStub(execute_result=run, complete_result=run)
    runtime = SimpleNamespace(
        settings=RuntimeSettingsStub(),
        submit_prompt=submit,
        get_run_status=GetRunStatusStub(),
    )
    application = ApplicationStub(runtime)
    update = UpdateStub(MessageStub("/ask build something"))
    context = ContextStub(application)

    await telegram_handlers.handle_prompt(update, context)
    assert len(application.created_tasks) == 1
    await asyncio.gather(*application.created_tasks)

    assert any("approved plan" in text for _chat_id, text in application.bot.messages)


def test_sqlite_ensure_queued_job_raises_when_integrity_error_has_no_active_job() -> None:
    repo = SQLiteRunJobRepository(SimpleNamespace(connection=lambda: BrokenConnection()))
    repo.get_active_for_run = lambda *args, **kwargs: None

    with pytest.raises(sqlite3.IntegrityError):
        repo.ensure_queued_job("run-1")
