"""Composition root for runtime wiring."""

from dataclasses import dataclass
from pathlib import Path

from mergemate.application.execution_plan import OrchestratorDependencies
from mergemate.application.jobs.dispatcher import RunDispatcher
from mergemate.application.jobs.worker import BackgroundRunWorker
from mergemate.application.orchestrator import AgentOrchestrator
from mergemate.application.services.context_service import ContextService
from mergemate.application.services.documentation_service import DocumentationService
from mergemate.application.services.learning_service import LearningService
from mergemate.application.services.planning_service import PlanningService
from mergemate.application.services.prompt_service import PromptService
from mergemate.application.services.tool_service import ToolService
from mergemate.application.services.workflow_service import WorkflowService
from mergemate.application.use_cases.cancel_run import CancelRunUseCase
from mergemate.application.use_cases.get_run_status import GetRunStatusUseCase
from mergemate.application.use_cases.submit_prompt import SubmitPromptUseCase
from typing import TYPE_CHECKING

from mergemate.config.loader import load_runtime_settings, resolve_config_path
from mergemate.config.models import AppConfig
from mergemate.infrastructure.llm.gateway import ParallelLLMGateway
from mergemate.infrastructure.llm.openai_adapter import OpenAIAdapter
from mergemate.infrastructure.persistence.sqlite import (
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteLearningRepository,
    SQLiteRunJobRepository,
    SQLiteRunRepository,
    SQLiteToolEventRepository,
)

if TYPE_CHECKING:
    from mergemate.infrastructure.persistence.sqlite import SQLiteRepoKnowledgeRepository
else:
    SQLiteRepoKnowledgeRepository = None

from mergemate.infrastructure.queue import JobQueueBackend
from mergemate.infrastructure.queue.local_queue import LocalQueue
from mergemate.infrastructure.telemetry.logger import configure_logging, log_startup_configuration
from mergemate.interfaces.telegram.lifecycle_notifier import (
    LifecycleNotifier,
    TelegramRunLifecycleNotifier,
)
from mergemate.infrastructure.tools.registry import ToolRegistryBuilder

# ── Workflow plugin discovery ───────────────────────────────────────────────


def discover_workflow_plugins() -> None:
    """Discover and load workflow plugins registered via entry points.

    Scans the ``mergemate.workflows`` entry point group and calls each
    registered registration function.  Plugin authors package their
    plugin as a Python package with::

        [project.entry-points."mergemate.workflows"]
        my_plugin = "my_plugin_package:register"

    Errors from individual plugins are logged as warnings so that a
    misbehaving plugin never blocks the rest of the bootstrap sequence.
    """
    from importlib.metadata import entry_points

    discovered = entry_points(group="mergemate.workflows")
    for ep in discovered:
        try:
            ep.load()()  # call the registration function
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to load workflow plugin: %s",
                ep.name,
                exc_info=True,
            )


def _load_workflow_config_plugins(settings: AppConfig) -> None:
    """Load file-based workflow plugins from the ``workflow_plugins`` config list.

    Each entry may be a ``str`` (module path) or a ``dict`` with keys
    ``module`` (required) and optional ``config`` passed to the module's
    ``register`` function.  Strings are treated as ``{"module": <str>}``.

    Errors from individual plugins are logged as warnings so that a
    misbehaving plugin never blocks the rest of the bootstrap sequence.
    """
    import importlib

    for entry in settings.workflow_plugins:
        if isinstance(entry, dict):
            module_path = entry.get("module", "")
            plugin_config = {k: v for k, v in entry.items() if k != "module"}
        else:
            module_path = str(entry)
            plugin_config = {}

        try:
            module = importlib.import_module(module_path)
            register_fn = getattr(module, "register", None)
            if register_fn is not None:
                if plugin_config:
                    register_fn(plugin_config)
                else:
                    register_fn()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to load config workflow plugin: %s",
                module_path,
                exc_info=True,
            )


@dataclass(slots=True)
class PersistenceContext:
    """Persistence-related sub-context for MergeMateRuntime — groups all DB-backed repositories."""

    database: SQLiteDatabase
    run_repository: SQLiteRunRepository
    run_job_repository: SQLiteRunJobRepository
    conversation_repository: SQLiteConversationRepository
    learning_repository: SQLiteLearningRepository
    tool_event_repository: SQLiteToolEventRepository
    repo_knowledge_repository: "SQLiteRepoKnowledgeRepository"


@dataclass(slots=True)
class ServiceContext:
    """Service-layer sub-context for MergeMateRuntime — groups logical services and use cases."""

    learning_service: LearningService
    tool_service: ToolService
    planning_service: PlanningService
    workflow_service: WorkflowService
    context_service: ContextService
    documentation_service: DocumentationService
    prompt_service: PromptService
    submit_prompt: SubmitPromptUseCase
    get_run_status: GetRunStatusUseCase
    cancel_run: CancelRunUseCase


@dataclass
class MergeMateRuntime:
    settings: AppConfig
    config_path: Path
    persistence: PersistenceContext
    services: ServiceContext
    queue_backend: JobQueueBackend
    worker: BackgroundRunWorker
    lifecycle_notifier: LifecycleNotifier


def bootstrap(config_path: Path | None = None) -> MergeMateRuntime:
    resolved_config_path = resolve_config_path(config_path)
    settings = load_runtime_settings(config_path)
    configure_logging(settings.logging.level)

    # Discover and load workflow plugins before any service references them
    discover_workflow_plugins()
    _load_workflow_config_plugins(settings)

    resolved_database_path = settings.resolve_database_path(resolved_config_path)
    database = SQLiteDatabase(resolved_database_path)
    database.initialize()
    log_startup_configuration(
        settings,
        config_path=resolved_config_path,
        database_path=resolved_database_path,
    )

    repo_knowledge_repository_cls = SQLiteRepoKnowledgeRepository
    if repo_knowledge_repository_cls is None:
        from mergemate.infrastructure.persistence.sqlite import (
            SQLiteRepoKnowledgeRepository as repo_knowledge_repository_cls,
        )

    run_repository = SQLiteRunRepository(database)
    run_job_repository = SQLiteRunJobRepository(database)
    queue_backend = LocalQueue()
    conversation_repository = SQLiteConversationRepository(database)
    learning_repository = SQLiteLearningRepository(database)
    tool_event_repository = SQLiteToolEventRepository(database)
    repo_knowledge_repository = repo_knowledge_repository_cls(database)
    context_service = ContextService(conversation_repository)
    learning_service = LearningService(
        learning_repository,
        enabled=settings.learning.enabled,
        max_context_items=settings.learning.max_context_items,
        max_result_chars=settings.learning.max_result_chars,
        repo_knowledge_repository=repo_knowledge_repository,
    )
    documentation_service = DocumentationService(settings.resolve_docs_root(resolved_config_path))
    prompt_service = PromptService(Path(__file__).resolve().parent / "prompts")
    working_directory = settings.resolve_working_directory(resolved_config_path)

    llm_clients = {}
    for provider_name, provider_settings in settings.providers.items():
        llm_clients[provider_name] = OpenAIAdapter(
            model=provider_settings.model,
            api_key=settings.resolve_provider_api_key(provider_name),
            timeout_seconds=provider_settings.timeout_seconds,
            provider_url=provider_settings.provider_url,
            api_key_header=provider_settings.api_key_header,
            api_key_prefix=provider_settings.api_key_prefix,
            extra_headers=provider_settings.extra_headers,
        )
    llm_gateway = ParallelLLMGateway(settings, llm_clients)

    tool_registry_builder = ToolRegistryBuilder(settings, working_directory=working_directory)
    if settings.source_control.enable_git:
        tool_registry_builder.with_git()
    if settings.source_control.enable_github:
        tool_registry_builder.with_github_cli()
    if settings.source_control.enable_gitlab:
        tool_registry_builder.with_gitlab_cli()
    tool_registry = tool_registry_builder.build()
    tool_service = ToolService(
        tool_registry,
        settings,
        run_repository=run_repository,
        tool_event_repository=tool_event_repository,
    )
    planning_service = PlanningService(llm_gateway, settings)
    workflow_service = WorkflowService(llm_gateway, settings)
    lifecycle_notifier = TelegramRunLifecycleNotifier(settings)

    dispatcher = RunDispatcher(run_job_repository, queue_backend)

    submit_prompt_use_case = SubmitPromptUseCase(
        run_repository,
        context_service,
        dispatcher,
        planning_service,
        settings,
    )

    orchestrator = AgentOrchestrator(
        deps=OrchestratorDependencies(
            run_repository=run_repository,
            context_service=context_service,
            documentation_service=documentation_service,
            learning_service=learning_service,
            planning_service=planning_service,
            prompt_service=prompt_service,
            tool_service=tool_service,
            workflow_service=workflow_service,
            llm_gateway=llm_gateway,
            settings=settings,
        ),
    )
    worker = BackgroundRunWorker(
        orchestrator=orchestrator,
        run_repository=run_repository,
        run_job_repository=run_job_repository,
        queue_backend=queue_backend,
        submit_prompt=submit_prompt_use_case,
        lifecycle_notifier=lifecycle_notifier,
        max_concurrent_runs=settings.runtime.max_concurrent_runs,
        lease_seconds=settings.runtime.job_lease_seconds,
        heartbeat_interval_seconds=settings.runtime.job_heartbeat_interval_seconds,
    )

    runtime = MergeMateRuntime(
        settings=settings,
        config_path=resolved_config_path,
        persistence=PersistenceContext(
            database=database,
            run_repository=run_repository,
            run_job_repository=run_job_repository,
            conversation_repository=conversation_repository,
            learning_repository=learning_repository,
            tool_event_repository=tool_event_repository,
            repo_knowledge_repository=repo_knowledge_repository,
        ),
        services=ServiceContext(
            learning_service=learning_service,
            tool_service=tool_service,
            planning_service=planning_service,
            workflow_service=workflow_service,
            context_service=context_service,
            documentation_service=documentation_service,
            prompt_service=prompt_service,
            submit_prompt=submit_prompt_use_case,
            get_run_status=GetRunStatusUseCase(run_repository, tool_event_repository),
            cancel_run=CancelRunUseCase(run_repository),
        ),
        queue_backend=queue_backend,
        worker=worker,
        lifecycle_notifier=lifecycle_notifier,
    )
    lifecycle_notifier.bind_runtime(runtime)
    return runtime
