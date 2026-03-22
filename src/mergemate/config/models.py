"""Configuration models for MergeMate."""

import os
from pathlib import Path

from pydantic import BaseModel, Field


class LoggingConfig(BaseModel):
    level: str = "INFO"


class ProviderConfig(BaseModel):
    provider_type: str = "openai"
    api_key_env: str
    model: str
    timeout_seconds: int = 90
    api_base_url: str | None = None


class TelegramConfig(BaseModel):
    bot_token_env: str
    mode: str = "polling"


class StorageConfig(BaseModel):
    database_path: str = ".state/mergemate.db"


class LearningConfig(BaseModel):
    enabled: bool = True
    max_context_items: int = 3
    max_result_chars: int = 1200


class ToolRuntimeConfig(BaseModel):
    allow_package_install: bool = False
    allowed_packages: list[str] = Field(default_factory=list)
    pip_executable: str = "python3"


class RuntimeConfig(BaseModel):
    max_concurrent_runs: int = 2
    status_update_interval_seconds: int = 5
    default_request_timeout_seconds: int = 300


class WorkflowControlConfig(BaseModel):
    require_confirmation: bool = True
    max_review_iterations: int = 5
    planner_agent_name: str = "planner"
    coder_agent_name: str = "coder"
    tester_agent_name: str = "tester"
    reviewer_agent_name: str = "reviewer"


class AgentConfig(BaseModel):
    workflow: str
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
    runtime: RuntimeConfig
    workflow_control: WorkflowControlConfig = Field(default_factory=WorkflowControlConfig)
    agents: dict[str, AgentConfig]
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def resolve_provider_api_key(self, provider_name: str | None = None) -> str | None:
        provider = self.providers[provider_name or self.default_provider]
        return os.getenv(provider.api_key_env)

    def resolve_agent_provider_names(self, agent_name: str) -> list[str]:
        agent = self.agents.get(agent_name)
        if agent is None or not agent.provider_names:
            return [self.default_provider]
        return agent.provider_names

    def resolve_telegram_token(self) -> str:
        token = os.getenv(self.telegram.bot_token_env)
        if not token:
            raise ValueError(
                f"Telegram bot token not found in environment variable {self.telegram.bot_token_env}"
            )
        return token

    def resolve_database_path(self, config_path: Path) -> Path:
        database_path = Path(self.storage.database_path).expanduser()
        if database_path.is_absolute():
            return database_path
        return (config_path.parent / database_path).resolve()