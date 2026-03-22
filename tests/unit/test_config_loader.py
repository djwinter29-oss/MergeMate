from pathlib import Path

from mergemate.config.loader import load_runtime_settings


def test_load_runtime_settings_uses_project_config() -> None:
    settings = load_runtime_settings(Path("config/config.yaml"))
    assert settings.default_agent == "coder"
    assert settings.telegram.mode == "polling"