from pathlib import Path

from mergemate.config.loader import load_runtime_settings, resolve_config_path


def test_load_runtime_settings_uses_project_config() -> None:
    settings = load_runtime_settings(Path("config/config.yaml"))

    assert settings.default_agent == "coder"
    assert settings.default_provider == "openai_coder"
    assert settings.telegram.mode == "polling"
    assert settings.storage.workspace_root == "./workspace"
    assert settings.storage.database_path == ".state/mergemate.db"
    assert settings.workflow_control.max_review_iterations == 5
    assert settings.workflow_control.architect_agent_name == "architect"
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


def test_resolve_config_path_returns_explicit_path() -> None:
    explicit_path = Path("~/custom-config.yaml")

    resolved = resolve_config_path(explicit_path)

    assert resolved == explicit_path.expanduser().resolve()


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