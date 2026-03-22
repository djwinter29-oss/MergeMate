"""Public settings accessors."""

from pathlib import Path

from mergemate.config.loader import load_runtime_settings
from mergemate.config.models import AppConfig


def get_settings(config_path: Path | None = None) -> AppConfig:
    return load_runtime_settings(config_path)