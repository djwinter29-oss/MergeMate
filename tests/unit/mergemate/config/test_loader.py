from pathlib import Path

import pytest

from mergemate.config import loader as loader_module
from mergemate.config.loader import _deep_merge, _read_yaml, load_runtime_settings, resolve_config_path


def test_load_runtime_settings_uses_project_config() -> None:
    settings = load_runtime_settings(Path("config/config.yaml"))

    assert settings.default_agent == "coder"
    assert settings.default_provider == "openai_coder"
    assert settings.telegram.mode == "polling"
    assert settings.storage.workspace_root == "./workspace"
    assert settings.storage.database_path == ".state/mergemate.db"
    assert settings.workflow_control.max_review_iterations == 5
    assert settings.resolve_agent_name_for_workflow("design") == "architect"
    assert settings.providers["openai_planner"].api_key_header == "Authorization"
    assert settings.providers["openai_planner"].api_key_prefix == "Bearer"


def test_load_runtime_settings_explicit_config_overrides_local_config(tmp_path) -> None:
    config_path = tmp_path / "override.yaml"
    config_path.write_text(
        """
default_agent: reviewer
telegram:
  mode: polling
workflow_control:
  max_review_iterations: 2
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_runtime_settings(config_path)

    assert settings.default_agent == "reviewer"
    assert settings.workflow_control.max_review_iterations == 2
    assert settings.default_provider == "openai_coder"


def test_resolve_config_path_returns_explicit_path(tmp_path) -> None:
    explicit_path = tmp_path / "custom-config.yaml"
    explicit_path.write_text("default_agent: coder\n", encoding="utf-8")

    resolved = resolve_config_path(explicit_path)

    assert resolved == explicit_path.resolve()


def test_resolve_config_path_rejects_missing_explicit_path(tmp_path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        resolve_config_path(missing_path)


def test_resolve_config_path_defaults_to_local_config(monkeypatch) -> None:
    monkeypatch.setattr(loader_module, "_discover_default_local_config_path", lambda: Path("/tmp/default-config.yaml"))

    assert resolve_config_path() == Path("/tmp/default-config.yaml").resolve()


def test_resolve_config_path_prefers_project_root_over_current_directory(tmp_path, monkeypatch) -> None:
    project_root = tmp_path / "project"
    config_path = project_root / "config" / "config.yaml"
    defaults_path = project_root / "src" / "mergemate" / "config" / "defaults.yaml"
    defaults_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\nname='mergemate'\n", encoding="utf-8")
    defaults_path.write_text("default_agent: coder\n", encoding="utf-8")
    config_path.write_text("default_agent: reviewer\n", encoding="utf-8")
    other_root = tmp_path / "elsewhere"
    other_root.mkdir()
    monkeypatch.chdir(other_root)
    monkeypatch.setattr(loader_module, "PACKAGE_DEFAULTS_PATH", defaults_path)

    assert resolve_config_path() == config_path.resolve()


def test_workspace_root_scopes_database_docs_and_working_directory(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
storage:
  workspace_root: workspace
  database_path: .state/runtime.db
source_control:
  working_directory: repo
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_runtime_settings(config_path)

    assert settings.resolve_workspace_root(config_path) == (tmp_path / "workspace").resolve()
    assert settings.resolve_database_path(config_path) == (tmp_path / "workspace" / ".state" / "runtime.db").resolve()
    assert settings.resolve_docs_root(config_path) == (tmp_path / "workspace" / "docs").resolve()
    assert settings.resolve_working_directory(config_path) == (tmp_path / "workspace" / "repo").resolve()


def test_resolve_workspace_root_creates_missing_directory(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("storage:\n  workspace_root: ./workspace\n", encoding="utf-8")

    settings = load_runtime_settings(config_path)

    workspace_root = settings.resolve_workspace_root(config_path)

    assert workspace_root == (tmp_path / "workspace").resolve()
    assert workspace_root.exists() is True
    assert workspace_root.is_dir() is True


def test_read_yaml_and_deep_merge_cover_empty_and_nested_cases(tmp_path) -> None:
    empty_path = tmp_path / "empty.yaml"
    empty_path.write_text("", encoding="utf-8")

    assert _read_yaml(tmp_path / "missing.yaml") == {}
    assert _read_yaml(empty_path) == {}
    assert _deep_merge({"a": {"b": 1}, "c": 1}, {"a": {"d": 2}, "c": 3}) == {
        "a": {"b": 1, "d": 2},
        "c": 3,
    }


def test_load_runtime_settings_ignores_explicit_path_when_it_matches_default(monkeypatch) -> None:
    default_path = Path("config/config.yaml").resolve()
    monkeypatch.setattr(loader_module, "PACKAGE_DEFAULTS_PATH", default_path)
    monkeypatch.setattr(loader_module, "_discover_default_local_config_path", lambda: default_path)

    settings = load_runtime_settings(default_path)

    assert settings.default_agent == "coder"


def test_load_runtime_settings_rejects_missing_explicit_path(tmp_path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        load_runtime_settings(missing_path)