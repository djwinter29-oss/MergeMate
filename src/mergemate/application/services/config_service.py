"""Configuration service placeholder."""

from pathlib import Path

from mergemate.config.settings import get_settings


class ConfigService:
    def load(self, config_path: Path | None = None):
        return get_settings(config_path)