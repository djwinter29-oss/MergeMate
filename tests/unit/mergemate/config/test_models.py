import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from mergemate.config.models import AppConfig
from mergemate.domain.shared import WorkflowName


def _build_config() -> AppConfig:
    return AppConfig.model_validate(
        {
            "default_agent": "coder",
            "default_provider": "primary",
            "providers": {
                "primary": {
                    "api_key_env": "PRIMARY_KEY",
                    "model": "gpt-5.4",
                },
                "secondary": {
                    "api_key_env": "SECONDARY_KEY",
                    "model": "gpt-4.1",
                },
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


def test_config_model_resolves_provider_names_and_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _build_config()
    monkeypatch.setenv("PRIMARY_KEY", "primary-secret")

    assert config.resolve_provider_api_key() == "primary-secret"
    assert config.agents["coder"].workflow == WorkflowName.GENERATE_CODE
    assert config.resolve_agent_provider_names("coder") == ["secondary"]
    assert config.resolve_agent_provider_names("missing") == ["primary"]
    assert config.resolve_agent_provider_names("reviewer") == ["primary"]


def test_config_model_resolves_telegram_token_and_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _build_config()
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)

    with pytest.raises(ValueError, match="Telegram bot token not found"):
        config.resolve_telegram_token()

    monkeypatch.setenv("TELEGRAM_TOKEN", "telegram-secret")
    assert config.resolve_telegram_token() == "telegram-secret"


def test_config_model_resolves_telegram_webhook_url_and_secret_token(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "https://bot.example.com/root/",
        "webhook_path": "/telegram/hook",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
    }
    config = AppConfig.model_validate(payload)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "hook-secret")

    assert config.resolve_telegram_webhook_url() == "https://bot.example.com/root/telegram/hook"
    assert config.resolve_telegram_webhook_secret_token() == "hook-secret"


def test_config_model_allows_http_webhook_url_for_loopback_development() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "http://127.0.0.1:8081",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
    }
    config = AppConfig.model_validate(payload)

    assert config.resolve_telegram_webhook_url() == "http://127.0.0.1:8081/telegram/webhook"


def test_config_model_resolves_workspace_database_docs_and_absolute_paths(tmp_path: Path) -> None:
    config = _build_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("config: true\n", encoding="utf-8")

    assert config.resolve_workspace_root(config_path) == (tmp_path / "workspace").resolve()
    assert config.resolve_database_path(config_path) == (tmp_path / "workspace" / ".state" / "runtime.db").resolve()
    assert config.resolve_docs_root(config_path) == (tmp_path / "workspace" / "docs").resolve()
    assert config.resolve_working_directory(config_path) == (tmp_path / "workspace" / "repo").resolve()

    config.storage.database_path = str((tmp_path / "absolute.db").resolve())
    config.source_control.working_directory = str((tmp_path / "absolute-repo").resolve())
    assert config.resolve_database_path(config_path) == (tmp_path / "absolute.db").resolve()
    assert config.resolve_working_directory(config_path) == (tmp_path / "absolute-repo").resolve()

    config.storage.workspace_root = str((tmp_path / "absolute-workspace").resolve())
    assert config.resolve_workspace_root(config_path) == (tmp_path / "absolute-workspace").resolve()


def test_config_model_preview_paths_do_not_create_workspace(tmp_path: Path) -> None:
    config = _build_config()
    config_path = tmp_path / "config.yaml"
    config_path.write_text("config: true\n", encoding="utf-8")

    workspace_root = config.preview_workspace_root(config_path)
    database_path = config.preview_database_path(config_path)

    assert workspace_root == (tmp_path / "workspace").resolve()
    assert database_path == (tmp_path / "workspace" / ".state" / "runtime.db").resolve()
    assert workspace_root.exists() is False


def test_config_model_expands_environment_based_provider_override(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _build_config()
    monkeypatch.setenv("SECONDARY_KEY", "secondary-secret")

    assert config.resolve_provider_api_key("secondary") == "secondary-secret"
    assert os.getenv("SECONDARY_KEY") == "secondary-secret"


def test_config_model_resolves_agent_name_for_workflow() -> None:
    config = _build_config()

    assert config.resolve_agent_name_for_workflow("generate_code") == "coder"
    assert config.resolve_agent_name_for_workflow(WorkflowName.GENERATE_CODE) == "coder"
    assert config.resolve_agent_name_for_workflow("generate_code", preferred_agent_name="coder") == "coder"
    assert config.resolve_agent_name_for_workflow("generate_code", preferred_agent_name="reviewer") == "coder"


def test_config_model_raises_for_unknown_workflow() -> None:
    config = _build_config()

    with pytest.raises(ValueError, match="No configured agent found"):
        config.resolve_agent_name_for_workflow("debug_code")


def test_config_model_rejects_duplicate_planning_workflow_assignment() -> None:
    payload = _build_config().model_dump()
    payload["agents"]["backup-planner"] = {"workflow": "planning"}

    with pytest.raises(ValidationError, match="Duplicate workflows: planning"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_duplicate_generate_code_workflow_assignment() -> None:
    payload = _build_config().model_dump()
    payload["agents"]["backup-coder"] = {"workflow": "generate_code"}

    with pytest.raises(ValidationError, match="Duplicate workflows: generate_code"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_non_positive_concurrency() -> None:
    payload = _build_config().model_dump()
    payload["runtime"]["max_concurrent_runs"] = 0

    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        AppConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("learning", "max_context_items"),
        ("learning", "max_result_chars"),
        ("workflow_control", "max_review_iterations"),
    ],
)
def test_config_model_rejects_non_positive_learning_and_review_values(section: str, key: str) -> None:
    payload = _build_config().model_dump()
    payload.setdefault(section, {})[key] = 0

    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        AppConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("runtime", "status_update_interval_seconds"),
        ("runtime", "default_request_timeout_seconds"),
        ("providers", "timeout_seconds"),
    ],
)
def test_config_model_rejects_non_positive_timeout_values(section: str, key: str) -> None:
    payload = _build_config().model_dump()
    if section == "providers":
        payload["providers"]["primary"][key] = 0
    else:
        payload[section][key] = 0

    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_webhook_mode_without_public_base_url() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
    }

    with pytest.raises(ValidationError, match="public base URL"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_webhook_mode_without_secret_token_env() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "https://bot.example.com",
    }

    with pytest.raises(ValidationError, match="secret token env"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_webhook_path_without_leading_slash() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "https://bot.example.com",
        "webhook_path": "telegram-hook",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
    }

    with pytest.raises(ValidationError, match="must start with '/'"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_webhook_path_with_query_or_fragment() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "https://bot.example.com",
        "webhook_path": "/telegram-hook?foo=bar",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
    }

    with pytest.raises(ValidationError, match="must not include query or fragment"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_non_https_webhook_url_for_non_loopback_hosts() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "http://bot.example.com",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
    }

    with pytest.raises(ValidationError, match="must use https"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_webhook_url_with_query_or_fragment() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "https://bot.example.com/base?foo=bar",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
    }

    with pytest.raises(ValidationError, match="must not include query or fragment"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_webhook_healthcheck_path_with_query_or_fragment() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_public_base_url": "https://bot.example.com",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
        "webhook_healthcheck_path": "/healthz?full=true",
    }

    with pytest.raises(ValidationError, match="healthcheck path"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_conflicting_webhook_and_healthcheck_bindings() -> None:
    payload = _build_config().model_dump()
    payload["telegram"] = {
        "bot_token_env": "TELEGRAM_TOKEN",
        "mode": "webhook",
        "webhook_listen_host": "0.0.0.0",
        "webhook_listen_port": 8080,
        "webhook_public_base_url": "https://bot.example.com",
        "webhook_secret_token_env": "TELEGRAM_WEBHOOK_SECRET",
        "webhook_healthcheck_enabled": True,
        "webhook_healthcheck_listen_host": "127.0.0.1",
        "webhook_healthcheck_listen_port": 8080,
    }

    with pytest.raises(ValidationError, match="conflicting host/port bindings"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_unknown_default_provider() -> None:
    payload = _build_config().model_dump()
    payload["default_provider"] = "missing"

    with pytest.raises(ValidationError, match="Default provider missing is not configured"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_unknown_agent_provider_reference() -> None:
    payload = _build_config().model_dump()
    payload["agents"]["coder"]["provider_names"] = ["missing"]

    with pytest.raises(ValidationError, match="Agent coder references unknown provider missing"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_unknown_agent_workflow() -> None:
    payload = _build_config().model_dump()
    payload["agents"]["coder"]["workflow"] = "ship_it"

    with pytest.raises(ValidationError, match="workflow"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_unknown_default_agent() -> None:
    payload = _build_config().model_dump()
    payload["default_agent"] = "missing"

    with pytest.raises(ValidationError, match="Default agent missing is not configured"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_internal_default_agent() -> None:
    payload = _build_config().model_dump()
    payload["default_agent"] = "planner"

    with pytest.raises(ValidationError, match="Default agent must use a user-facing workflow"):
        AppConfig.model_validate(payload)


def test_config_model_requires_planning_agent() -> None:
    payload = _build_config().model_dump()
    payload["agents"].pop("planner")

    with pytest.raises(ValidationError, match="A planning agent must be configured"):
        AppConfig.model_validate(payload)


def test_config_model_requires_multi_stage_support_agents_for_generate_code() -> None:
    payload = _build_config().model_dump()
    payload["agents"].pop("architect")
    payload["agents"].pop("tester")

    with pytest.raises(ValidationError, match="design, testing"):
        AppConfig.model_validate(payload)


def test_config_model_rejects_duplicate_workflow_assignments() -> None:
    payload = _build_config().model_dump()
    payload["agents"]["backup_coder"] = {"workflow": "generate_code"}

    with pytest.raises(ValidationError, match="Duplicate workflows: generate_code"):
        AppConfig.model_validate(payload)