import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from mergemate.config.models import AppConfig


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
                "coder": {"workflow": "generate_code", "provider_names": ["secondary"]},
                "reviewer": {"workflow": "explain_code"},
            },
        }
    )


def test_config_model_resolves_provider_names_and_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _build_config()
    monkeypatch.setenv("PRIMARY_KEY", "primary-secret")

    assert config.resolve_provider_api_key() == "primary-secret"
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
    assert config.resolve_agent_name_for_workflow("generate_code", preferred_agent_name="coder") == "coder"
    assert config.resolve_agent_name_for_workflow("generate_code", preferred_agent_name="reviewer") == "coder"


def test_config_model_raises_for_unknown_workflow() -> None:
    config = _build_config()

    with pytest.raises(ValueError, match="No configured agent found"):
        config.resolve_agent_name_for_workflow("planning")


def test_config_model_rejects_non_positive_concurrency() -> None:
    payload = _build_config().model_dump()
    payload["runtime"]["max_concurrent_runs"] = 0

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