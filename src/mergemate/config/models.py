"""Configuration models for MergeMate."""

import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from mergemate.domain.shared import WorkflowName


class LoggingConfig(BaseModel):
    level: str = "INFO"


class ProviderConfig(BaseModel):
    api_key_env: str
    model: str
    timeout_seconds: int = Field(default=90, ge=1)
    provider_url: str = "https://api.openai.com/v1/chat/completions"
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    extra_headers: dict[str, str] = Field(default_factory=dict)


class TelegramConfig(BaseModel):
    bot_token_env: str
    mode: str = "polling"


class StorageConfig(BaseModel):
    workspace_root: str = "./workspace"
    database_path: str = ".state/mergemate.db"


class LearningConfig(BaseModel):
    enabled: bool = True
    max_context_items: int = Field(default=3, ge=1)
    max_result_chars: int = Field(default=1200, ge=1)


class ToolRuntimeConfig(BaseModel):
    allow_package_install: bool = False
    allowed_packages: list[str] = Field(default_factory=list)
    pip_executable: str = "python3"


class SourceControlConfig(BaseModel):
    working_directory: str = "."
    default_platform: str = "github"
    enable_git: bool = True
    enable_github: bool = True
    enable_gitlab: bool = True
    git_executable: str = "git"
    github_executable: str = "gh"
    gitlab_executable: str = "glab"


class RuntimeConfig(BaseModel):
    max_concurrent_runs: int = Field(default=2, ge=1)
    status_update_interval_seconds: int = Field(default=5, ge=1)
    default_request_timeout_seconds: int = Field(default=300, ge=1)


class WorkflowControlConfig(BaseModel):
    require_confirmation: bool = True
    max_review_iterations: int = Field(default=5, ge=1)


class AgentConfig(BaseModel):
    workflow: WorkflowName
    tools: list[str] = Field(default_factory=list)
    provider_names: list[str] = Field(default_factory=list)
    parallel_mode: str = "single"
    combine_strategy: str = "sectioned"


class AppConfig(BaseModel):
    default_agent: str
    default_provider: str
    providers: dict[str, ProviderConfig]
    telegram: TelegramConfig
    storage: StorageConfig = Field(default_factory=StorageConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    tools: ToolRuntimeConfig = Field(default_factory=ToolRuntimeConfig)
    source_control: SourceControlConfig = Field(default_factory=SourceControlConfig)
    runtime: RuntimeConfig
    workflow_control: WorkflowControlConfig = Field(default_factory=WorkflowControlConfig)
    agents: dict[str, AgentConfig]
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    @model_validator(mode="after")
    def validate_provider_references(self):
        if self.default_agent not in self.agents:
            raise ValueError(f"Default agent {self.default_agent} is not configured")

        if self.default_provider not in self.providers:
            raise ValueError(f"Default provider {self.default_provider} is not configured")

        for agent_name, agent in self.agents.items():
            for provider_name in agent.provider_names:
                if provider_name not in self.providers:
                    raise ValueError(
                        f"Agent {agent_name} references unknown provider {provider_name}"
                    )

        available_workflows = {agent.workflow for agent in self.agents.values()}
        if WorkflowName.PLANNING not in available_workflows:
            raise ValueError("A planning agent must be configured")

        if WorkflowName.GENERATE_CODE in available_workflows:
            required_multi_stage_workflows = {
                WorkflowName.DESIGN,
                WorkflowName.TESTING,
                WorkflowName.REVIEW,
            }
            missing_workflows = sorted(
                workflow.value
                for workflow in required_multi_stage_workflows
                if workflow not in available_workflows
            )
            if missing_workflows:
                missing_text = ", ".join(missing_workflows)
                raise ValueError(
                    "Generate-code workflows require configured agents for: "
                    f"{missing_text}"
                )
        return self

    def resolve_provider_api_key(self, provider_name: str | None = None) -> str | None:
        provider = self.providers[provider_name or self.default_provider]
        return os.getenv(provider.api_key_env)

    def resolve_agent_provider_names(self, agent_name: str) -> list[str]:
        agent = self.agents.get(agent_name)
        if agent is None or not agent.provider_names:
            return [self.default_provider]
        return agent.provider_names

    def resolve_agent_name_for_workflow(
        self,
        workflow: str | WorkflowName,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        if preferred_agent_name is not None:
            preferred_agent = self.agents.get(preferred_agent_name)
            if preferred_agent is not None and preferred_agent.workflow == workflow:
                return preferred_agent_name

        for agent_name, agent in self.agents.items():
            if agent.workflow == workflow:
                return agent_name

        raise ValueError(f"No configured agent found for workflow {workflow}")

    def resolve_telegram_token(self) -> str:
        token = os.getenv(self.telegram.bot_token_env)
        if not token:
            raise ValueError(
                f"Telegram bot token not found in environment variable {self.telegram.bot_token_env}"
            )
        return token

    def resolve_database_path(self, config_path: Path) -> Path:
        workspace_root = self.resolve_workspace_root(config_path)
        database_path = Path(self.storage.database_path).expanduser()
        if database_path.is_absolute():
            return database_path
        return (workspace_root / database_path).resolve()

    def preview_database_path(self, config_path: Path) -> Path:
        workspace_root = self.preview_workspace_root(config_path)
        database_path = Path(self.storage.database_path).expanduser()
        if database_path.is_absolute():
            return database_path.resolve()
        return (workspace_root / database_path).resolve()

    def resolve_workspace_root(self, config_path: Path) -> Path:
        resolved_workspace_root = self.preview_workspace_root(config_path)
        resolved_workspace_root.mkdir(parents=True, exist_ok=True)
        return resolved_workspace_root

    def preview_workspace_root(self, config_path: Path) -> Path:
        workspace_root = Path(self.storage.workspace_root).expanduser()
        if workspace_root.is_absolute():
            return workspace_root.resolve()
        return (config_path.parent / workspace_root).resolve()

    def resolve_docs_root(self, config_path: Path) -> Path:
        return (self.resolve_workspace_root(config_path) / "docs").resolve()

    def resolve_working_directory(self, config_path: Path) -> Path:
        workspace_root = self.resolve_workspace_root(config_path)
        working_directory = Path(self.source_control.working_directory).expanduser()
        if working_directory.is_absolute():
            return working_directory
        return (workspace_root / working_directory).resolve()