"""Configuration models for MergeMate."""

from collections import Counter
import os
from pathlib import Path
from typing import Any, ClassVar, Literal, Self
from urllib.parse import ParseResult, urlparse

from pydantic import BaseModel, Field, model_validator

# ── Workflow name constants (mirrors domain WorkflowName, no import needed) ──

_WORKFLOW_PLANNING = "planning"
_WORKFLOW_DESIGN = "design"
_WORKFLOW_GENERATE_CODE = "generate_code"
_WORKFLOW_DEBUG_CODE = "debug_code"
_WORKFLOW_EXPLAIN_CODE = "explain_code"
_WORKFLOW_TESTING = "testing"
_WORKFLOW_REVIEW = "review"
_WORKFLOW_LEARNING = "learning"

_USER_FACING_WORKFLOWS: frozenset[str] = frozenset(
    {
        _WORKFLOW_GENERATE_CODE,
        _WORKFLOW_DEBUG_CODE,
        _WORKFLOW_EXPLAIN_CODE,
    }
)

# ── Config-local exception classes (mirrors domain exceptions, no import) ──


class ConfigError(ValueError):
    """Base exception for config-layer errors."""


class ConfigAgentNotFoundError(ConfigError):
    """Referenced agent is not configured."""


class ConfigProviderNotFoundError(ConfigError):
    """Referenced provider is not configured."""


class ConfigWorkflowNotFoundError(ConfigError):
    """No agent found for the requested workflow."""


ParallelMode = Literal["single", "parallel"]
CombineStrategy = Literal["sectioned", "first_success"]


def _validate_absolute_url(*, url: str, label: str, allow_query_or_fragment: bool) -> ParseResult:
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise ConfigError(f"{label} must be an absolute URL")
    if not allow_query_or_fragment and (parsed_url.query or parsed_url.fragment):
        raise ConfigError(f"{label} must not include query or fragment components")
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
        _validate_absolute_url(
            url=self.provider_url, label="Provider URL", allow_query_or_fragment=True
        )
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
    extraction_agent: str | None = None


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


class RetryConfig(BaseModel):
    """Exponential backoff with full-jitter retry policy for LLM gateway calls."""

    max_retries: int = Field(default=3, ge=0)
    base_delay_seconds: float = Field(default=2.0, ge=0.001)
    max_delay_seconds: float = Field(default=60.0, ge=1.0)
    budget_window_seconds: int = Field(default=60, ge=1)
    budget_max_retries: int = Field(default=10, ge=1)


class RuntimeConfig(BaseModel):
    max_concurrent_runs: int = Field(default=2, ge=1)
    status_update_interval_seconds: int = Field(default=5, ge=1)
    default_request_timeout_seconds: int = Field(default=300, ge=1)
    job_lease_seconds: int = Field(default=30, ge=1)
    job_heartbeat_interval_seconds: int = Field(default=10, ge=1)
    max_poll_iterations: int | None = Field(default=None, ge=1)
    llm_retry: RetryConfig = Field(default_factory=RetryConfig)


class WorkflowControlConfig(BaseModel):
    require_confirmation: bool = True
    max_review_iterations: int = Field(default=5, ge=1)


class WorkerConfig(BaseModel):
    """A single worker instance within a role.

    Multiple workers means parallel LLM invocations for the same role.
    """

    name: str
    provider_names: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class RoleConfig(BaseModel):
    """Configuration for a role with its Soul, workflow, and parallel workers."""

    soul: str = ""
    workflow: str
    workers: list[WorkerConfig] = Field(default_factory=list)
    provider_names: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    parallel_mode: ParallelMode = "single"
    combine_strategy: CombineStrategy = "sectioned"


class AgentConfig(BaseModel):
    workflow: str
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
    roles: dict[str, RoleConfig] = Field(default_factory=dict)
    workflow_plugins: list[str | dict] = Field(default_factory=list)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    repo_name: str | None = Field(
        default=None, description="Current repo name for session-scoped knowledge"
    )

    @model_validator(mode="before")
    @classmethod
    def _populate_roles_from_agents(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Backward compat: if roles is empty but agents exist, populate roles from agents."""
        agents = data.get("agents", {})
        roles = data.get("roles", {})
        if not roles and agents:
            data["roles"] = {
                name: {
                    "soul": name,
                    "workflow": cfg["workflow"] if isinstance(cfg, dict) else cfg.workflow,
                    "provider_names": cfg.get("provider_names", [])
                    if isinstance(cfg, dict)
                    else cfg.provider_names,
                    "tools": cfg.get("tools", []) if isinstance(cfg, dict) else cfg.tools,
                    "parallel_mode": cfg.get("parallel_mode", "single")
                    if isinstance(cfg, dict)
                    else cfg.parallel_mode,
                    "combine_strategy": cfg.get("combine_strategy", "sectioned")
                    if isinstance(cfg, dict)
                    else cfg.combine_strategy,
                }
                for name, cfg in agents.items()
            }
        return data

    @model_validator(mode="after")
    def validate_provider_references(self) -> Self:
        if self.default_agent not in self.agents:
            raise ConfigAgentNotFoundError(f"Default agent {self.default_agent} is not configured")

        default_agent_workflow = self.agents[self.default_agent].workflow
        if default_agent_workflow not in _USER_FACING_WORKFLOWS:
            raise ValueError(
                "Default agent must use a user-facing workflow: "
                "generate_code, debug_code, or explain_code"
            )

        if self.default_provider not in self.providers:
            raise ConfigProviderNotFoundError(
                f"Default provider {self.default_provider} is not configured"
            )

        for agent_name, agent in self.agents.items():
            for provider_name in agent.provider_names:
                if provider_name not in self.providers:
                    raise ValueError(
                        f"Agent {agent_name} references unknown provider {provider_name}"
                    )

        workflow_counts = Counter(agent.workflow for agent in self.agents.values())

        duplicated_workflows = sorted(
            workflow for workflow, count in workflow_counts.items() if count > 1
        )
        if duplicated_workflows:
            duplicate_text = ", ".join(duplicated_workflows)
            raise ValueError(
                "Each workflow must be assigned to exactly one agent. "
                f"Duplicate workflows: {duplicate_text}"
            )

        available_workflows = set(workflow_counts)
        if _WORKFLOW_PLANNING not in available_workflows:
            raise ConfigError("A planning role must be configured")

        if _WORKFLOW_GENERATE_CODE in available_workflows:
            required_multi_stage_workflows = {
                _WORKFLOW_DESIGN,
                _WORKFLOW_TESTING,
                _WORKFLOW_REVIEW,
            }
            missing_workflows = sorted(
                workflow
                for workflow in required_multi_stage_workflows
                if workflow not in available_workflows
            )
            if missing_workflows:
                missing_text = ", ".join(missing_workflows)
                raise ValueError(
                    f"Generate-code workflows require configured agents for: {missing_text}"
                )
        return self

    def resolve_provider_api_key(self, provider_name: str | None = None) -> str | None:
        provider = self.providers[provider_name or self.default_provider]
        return os.getenv(provider.api_key_env)

    def resolve_agent_provider_names(self, agent_name: str) -> list[str]:
        # First check roles, then agents
        role = self.roles.get(agent_name)
        if role and role.provider_names:
            return list(role.provider_names)
        agent = self.agents.get(agent_name)
        if agent is None or not agent.provider_names:
            return [self.default_provider]
        return list(agent.provider_names)

    def resolve_agent_name_for_workflow(
        self,
        workflow: str,
        *,
        preferred_agent_name: str | None = None,
    ) -> str:
        resolved_workflow = workflow

        # Check roles first (new-style config)
        for role_name, role in self.roles.items():
            if role.workflow == resolved_workflow:
                if preferred_agent_name is not None and role_name == preferred_agent_name:
                    return preferred_agent_name
                return role_name

        if preferred_agent_name is not None:
            preferred_agent = self.agents.get(preferred_agent_name)
            if preferred_agent is not None and preferred_agent.workflow == resolved_workflow:
                return preferred_agent_name

        for agent_name, agent in self.agents.items():
            if agent.workflow == resolved_workflow:
                return agent_name

        configured_workflows = sorted(
            {str(role.workflow) for role in self.roles.values()}
            | {str(agent.workflow) for agent in self.agents.values()}
        )
        available_text = ", ".join(configured_workflows)
        raise ConfigWorkflowNotFoundError(
            f"No configured agent found for workflow {resolved_workflow}. "
            f"Configured workflows: {available_text}"
        )

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
                f"Telegram webhook secret token not found in environment variable {env_name}"
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
        return self._resolve_subpath(
            subpath_str=self.storage.database_path,
            base_path=self.resolve_workspace_root(config_path),
        )

    def preview_database_path(self, config_path: Path) -> Path:
        return self._resolve_subpath(
            subpath_str=self.storage.database_path,
            base_path=self.preview_workspace_root(config_path),
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
        return self._resolve_subpath(
            subpath_str=self.source_control.working_directory,
            base_path=self.resolve_workspace_root(config_path),
        )
