"""Configuration models for MergeMate."""

import os
from pathlib import Path
from typing import ClassVar, Literal, Self
from urllib.parse import ParseResult, urlparse

from pydantic import BaseModel, Field, model_validator

from mergemate.domain.shared import WorkflowName, is_user_facing_workflow

ParallelMode = Literal["single", "parallel"]
CombineStrategy = Literal["sectioned", "first_success"]


def _validate_absolute_url(*, url: str, label: str, allow_query_or_fragment: bool) -> ParseResult:
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError(f"{label} must be an absolute URL")
    if not allow_query_or_fragment and (parsed_url.query or parsed_url.fragment):
        raise ValueError(f"{label} must not include query or fragment components")
    return parsed_url


def _derive_normalized_host_category(
    normalization_map: dict[str, str],
    *,
    prefix: str,
) -> frozenset[str]:
    return frozenset(value for value in normalization_map.values() if value.startswith(prefix))


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

    @model_validator(mode="after")
    def validate_provider_url(self) -> Self:
        _validate_absolute_url(url=self.provider_url, label="Provider URL", allow_query_or_fragment=True)
        return self


class TelegramConfig(BaseModel):
    bot_token_env: str
    mode: Literal["polling", "webhook"] = "polling"
    webhook_listen_host: str = "0.0.0.0"
    webhook_listen_port: int = Field(default=8080, ge=1, le=65535)
    webhook_public_base_url: str | None = None
    webhook_path: str = "/telegram/webhook"
    webhook_secret_token_env: str | None = None
    webhook_healthcheck_enabled: bool = True
    webhook_healthcheck_listen_host: str = "127.0.0.1"
    webhook_healthcheck_listen_port: int = Field(default=8081, ge=1, le=65535)
    webhook_healthcheck_path: str = "/healthz"

    _HOST_NORMALIZATION_MAP: ClassVar[dict[str, str]] = {
        "localhost": "loopback-hostname",
        "0.0.0.0": "wildcard-ipv4",
        "::": "wildcard-ipv6",
        "127.0.0.1": "loopback-ipv4",
        "::1": "loopback-ipv6",
    }
    _WILDCARD_HOSTS: ClassVar[frozenset[str]] = _derive_normalized_host_category(
        _HOST_NORMALIZATION_MAP,
        prefix="wildcard-",
    )
    _LOOPBACK_HOSTS: ClassVar[frozenset[str]] = _derive_normalized_host_category(
        _HOST_NORMALIZATION_MAP,
        prefix="loopback-",
    )

    @model_validator(mode="after")
    def validate_webhook_settings(self) -> Self:
        self._validate_path(self.webhook_path, label="Telegram webhook path")
        self._validate_path(
            self.webhook_healthcheck_path,
            label="Telegram webhook healthcheck path",
        )
        if self.mode == "webhook":
            if not self.webhook_public_base_url:
                raise ValueError(
                    "Telegram webhook public base URL must be configured when mode is webhook"
                )
            parsed_base_url = _validate_absolute_url(
                url=self.webhook_public_base_url,
                label="Telegram webhook public base URL",
                allow_query_or_fragment=False,
            )

            is_loopback_host = (
                parsed_base_url.hostname is not None
                and TelegramConfig._normalize_listener_host(parsed_base_url.hostname)
                in TelegramConfig._LOOPBACK_HOSTS
            )
            if parsed_base_url.scheme != "https" and not (
                parsed_base_url.scheme == "http" and is_loopback_host
            ):
                raise ValueError(
                    "Telegram webhook public base URL must use https unless it points to localhost or a loopback address"
                )

            if not self.webhook_secret_token_env:
                raise ValueError(
                    "Telegram webhook secret token env must be configured when mode is webhook"
                )

            if (
                self.webhook_healthcheck_enabled
                and self.webhook_listen_port == self.webhook_healthcheck_listen_port
                and self._hosts_may_conflict(
                    self.webhook_listen_host,
                    self.webhook_healthcheck_listen_host,
                )
            ):
                raise ValueError(
                    "Telegram webhook and healthcheck listeners must not use conflicting host/port bindings"
                )
        return self

    @staticmethod
    def _validate_path(path: str, *, label: str) -> None:
        if not path.startswith("/"):
            raise ValueError(f"{label} must start with '/'")
        if "?" in path or "#" in path:
            raise ValueError(f"{label} must not include query or fragment components")

    @staticmethod
    def _hosts_may_conflict(first: str, second: str) -> bool:
        normalized_first = TelegramConfig._normalize_listener_host(first)
        normalized_second = TelegramConfig._normalize_listener_host(second)

        return (
            normalized_first == normalized_second
            or normalized_first in TelegramConfig._WILDCARD_HOSTS
            or normalized_second in TelegramConfig._WILDCARD_HOSTS
            or (
                normalized_first in TelegramConfig._LOOPBACK_HOSTS
                and normalized_second in TelegramConfig._LOOPBACK_HOSTS
            )
        )

    @staticmethod
    def _normalize_listener_host(host: str) -> str:
        normalized_host = host.strip().lower().strip("[]")
        return TelegramConfig._HOST_NORMALIZATION_MAP.get(normalized_host, normalized_host)


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
    job_lease_seconds: int = Field(default=30, ge=1)
    job_heartbeat_interval_seconds: int = Field(default=10, ge=1)


class WorkflowControlConfig(BaseModel):
    require_confirmation: bool = True
    max_review_iterations: int = Field(default=5, ge=1)


class AgentConfig(BaseModel):
    workflow: WorkflowName
    tools: list[str] = Field(default_factory=list)
    provider_names: list[str] = Field(default_factory=list)
    parallel_mode: ParallelMode = "single"
    combine_strategy: CombineStrategy = "sectioned"


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
    def validate_provider_references(self) -> Self:
        if self.default_agent not in self.agents:
            raise ValueError(f"Default agent {self.default_agent} is not configured")

        default_agent_workflow = self.agents[self.default_agent].workflow
        if not is_user_facing_workflow(default_agent_workflow):
            raise ValueError(
                "Default agent must use a user-facing workflow: "
                "generate_code, debug_code, or explain_code"
            )

        if self.default_provider not in self.providers:
            raise ValueError(f"Default provider {self.default_provider} is not configured")

        for agent_name, agent in self.agents.items():
            for provider_name in agent.provider_names:
                if provider_name not in self.providers:
                    raise ValueError(
                        f"Agent {agent_name} references unknown provider {provider_name}"
                    )

        workflow_counts: dict[WorkflowName, int] = {}
        for agent in self.agents.values():
            workflow_counts[agent.workflow] = workflow_counts.get(agent.workflow, 0) + 1

        duplicated_workflows = sorted(
            workflow.value for workflow, count in workflow_counts.items() if count > 1
        )
        if duplicated_workflows:
            duplicate_text = ", ".join(duplicated_workflows)
            raise ValueError(
                "Each workflow must be assigned to exactly one agent. "
                f"Duplicate workflows: {duplicate_text}"
            )

        available_workflows = set(workflow_counts)
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
        return list(agent.provider_names)

    def resolve_agent_name_for_workflow(
        self,
        workflow: str | WorkflowName,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        resolved_workflow = WorkflowName(workflow)

        if preferred_agent_name is not None:
            preferred_agent = self.agents.get(preferred_agent_name)
            if preferred_agent is not None and preferred_agent.workflow == resolved_workflow:
                return preferred_agent_name

        for agent_name, agent in self.agents.items():
            if agent.workflow == resolved_workflow:
                return agent_name

        raise ValueError(f"No configured agent found for workflow {resolved_workflow.value}")

    def resolve_telegram_token(self) -> str:
        token = os.getenv(self.telegram.bot_token_env)
        if not token:
            raise ValueError(
                f"Telegram bot token not found in environment variable {self.telegram.bot_token_env}"
            )
        return token

    def resolve_telegram_webhook_url(self) -> str:
        base_url = self.telegram.webhook_public_base_url
        if not base_url:
            raise ValueError(
                "Telegram webhook public base URL must be configured when mode is webhook"
            )
        return f"{base_url.rstrip('/')}{self.telegram.webhook_path}"

    def resolve_telegram_webhook_secret_token(self) -> str | None:
        env_name = self.telegram.webhook_secret_token_env
        if env_name is None:
            return None
        token = os.getenv(env_name)
        if not token:
            raise ValueError(
                "Telegram webhook secret token not found in environment variable "
                f"{env_name}"
            )
        return token

    @staticmethod
    def _resolve_subpath(
        *,
        subpath_str: str,
        base_path: Path,
    ) -> Path:
        """Expand a subpath relative to a base path.

        If the subpath is absolute (after expanduser), returns it normalized.
        Otherwise joins it with the base path and resolves.
        """
        subpath = Path(subpath_str).expanduser()
        if subpath.is_absolute():
            return subpath.resolve()
        return (base_path / subpath).resolve()

    def resolve_database_path(self, config_path: Path) -> Path:
        workspace_root = self.resolve_workspace_root(config_path)
        return self._resolve_subpath(
            subpath_str=self.storage.database_path,
            base_path=workspace_root,
        )

    def preview_database_path(self, config_path: Path) -> Path:
        workspace_root = self.preview_workspace_root(config_path)
        return self._resolve_subpath(
            subpath_str=self.storage.database_path,
            base_path=workspace_root,
        )

    def resolve_workspace_root(self, config_path: Path) -> Path:
        resolved_workspace_root = self.preview_workspace_root(config_path)
        resolved_workspace_root.mkdir(parents=True, exist_ok=True)
        return resolved_workspace_root

    def preview_workspace_root(self, config_path: Path) -> Path:
        return self._resolve_subpath(
            subpath_str=self.storage.workspace_root,
            base_path=config_path.parent,
        )

    def resolve_docs_root(self, config_path: Path) -> Path:
        return (self.resolve_workspace_root(config_path) / "docs").resolve()

    def resolve_working_directory(self, config_path: Path) -> Path:
        workspace_root = self.resolve_workspace_root(config_path)
        return self._resolve_subpath(
            subpath_str=self.source_control.working_directory,
            base_path=workspace_root,
        )