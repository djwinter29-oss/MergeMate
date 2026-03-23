"""Composition root for runtime wiring."""

from dataclasses import dataclass
from pathlib import Path

from mergemate.application.jobs.dispatcher import RunDispatcher
from mergemate.application.jobs.worker import BackgroundRunWorker
from mergemate.application.orchestrator import AgentOrchestrator
from mergemate.application.services.context_service import ContextService
from mergemate.application.services.documentation_service import DocumentationService
from mergemate.application.services.learning_service import LearningService
from mergemate.application.services.prompt_service import PromptService
from mergemate.application.services.tool_service import ToolService
from mergemate.application.services.workflow_service import WorkflowService
from mergemate.application.use_cases.approve_run import ApproveRunUseCase
from mergemate.application.use_cases.cancel_run import CancelRunUseCase
from mergemate.application.use_cases.get_run_status import GetRunStatusUseCase
from mergemate.application.use_cases.submit_prompt import SubmitPromptUseCase
from mergemate.config.loader import load_runtime_settings, resolve_config_path
from mergemate.infrastructure.llm.gateway import ParallelLLMGateway
from mergemate.infrastructure.llm.openai_adapter import OpenAIAdapter
from mergemate.infrastructure.persistence.sqlite import (
    SQLiteConversationRepository,
    SQLiteDatabase,
    SQLiteLearningRepository,
    SQLiteRunRepository,
    SQLiteToolEventRepository,
)
from mergemate.infrastructure.telemetry.logger import configure_logging
from mergemate.infrastructure.tools.builtin.code_formatter import CodeFormatterTool
from mergemate.infrastructure.tools.builtin.package_installer import PackageInstallerTool
from mergemate.infrastructure.tools.builtin.source_control import (
    GitHubCliTool,
    GitLabCliTool,
    GitRepositoryTool,
)
from mergemate.infrastructure.tools.builtin.syntax_checker import SyntaxCheckerTool
from mergemate.infrastructure.tools.registry import ToolRegistry


@dataclass(slots=True)
class MergeMateRuntime:
    settings: object
    config_path: Path
    database: SQLiteDatabase
    run_repository: SQLiteRunRepository
    conversation_repository: SQLiteConversationRepository
    learning_repository: SQLiteLearningRepository
    tool_event_repository: SQLiteToolEventRepository
    learning_service: LearningService
    tool_service: ToolService
    workflow_service: WorkflowService
    submit_prompt: SubmitPromptUseCase
    approve_run: ApproveRunUseCase
    get_run_status: GetRunStatusUseCase
    cancel_run: CancelRunUseCase
    worker: BackgroundRunWorker


def bootstrap(config_path: Path | None = None) -> MergeMateRuntime:
    resolved_config_path = resolve_config_path(config_path)
    settings = load_runtime_settings(config_path)
    configure_logging(settings.logging.level)

    database = SQLiteDatabase(settings.resolve_database_path(resolved_config_path))
    database.initialize()

    run_repository = SQLiteRunRepository(database)
    conversation_repository = SQLiteConversationRepository(database)
    learning_repository = SQLiteLearningRepository(database)
    tool_event_repository = SQLiteToolEventRepository(database)
    context_service = ContextService(conversation_repository)
    learning_service = LearningService(
        learning_repository,
        enabled=settings.learning.enabled,
        max_context_items=settings.learning.max_context_items,
        max_result_chars=settings.learning.max_result_chars,
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

    tool_registry = ToolRegistry(
        {
            "code_formatter": CodeFormatterTool(),
            "package_installer": PackageInstallerTool(
                allow_package_install=settings.tools.allow_package_install,
                allowed_packages=settings.tools.allowed_packages,
                pip_executable=settings.tools.pip_executable,
            ),
            "syntax_checker": SyntaxCheckerTool(),
            **(
                {
                    "git_repository": GitRepositoryTool(
                        settings.source_control.git_executable,
                        working_directory,
                    )
                }
                if settings.source_control.enable_git
                else {}
            ),
            **(
                {
                    "github_cli": GitHubCliTool(
                        settings.source_control.github_executable,
                        working_directory,
                    )
                }
                if settings.source_control.enable_github
                else {}
            ),
            **(
                {
                    "gitlab_cli": GitLabCliTool(
                        settings.source_control.gitlab_executable,
                        working_directory,
                    )
                }
                if settings.source_control.enable_gitlab
                else {}
            ),
        }
    )
    tool_service = ToolService(
        tool_registry,
        settings,
        run_repository=run_repository,
        tool_event_repository=tool_event_repository,
    )
    workflow_service = WorkflowService(llm_gateway, settings)

    orchestrator = AgentOrchestrator(
        run_repository=run_repository,
        context_service=context_service,
        documentation_service=documentation_service,
        learning_service=learning_service,
        prompt_service=prompt_service,
        tool_service=tool_service,
        workflow_service=workflow_service,
        llm_gateway=llm_gateway,
        settings=settings,
    )
    worker = BackgroundRunWorker(
        orchestrator=orchestrator,
        run_repository=run_repository,
        max_concurrent_runs=settings.runtime.max_concurrent_runs,
    )
    dispatcher = RunDispatcher(worker)

    submit_prompt_use_case = SubmitPromptUseCase(
        run_repository,
        context_service,
        dispatcher,
        workflow_service,
        settings,
    )

    return MergeMateRuntime(
        settings=settings,
        config_path=resolved_config_path,
        database=database,
        run_repository=run_repository,
        conversation_repository=conversation_repository,
        learning_repository=learning_repository,
        tool_event_repository=tool_event_repository,
        learning_service=learning_service,
        tool_service=tool_service,
        workflow_service=workflow_service,
        submit_prompt=submit_prompt_use_case,
        approve_run=ApproveRunUseCase(submit_prompt_use_case),
        get_run_status=GetRunStatusUseCase(run_repository),
        cancel_run=CancelRunUseCase(run_repository),
        worker=worker,
    )