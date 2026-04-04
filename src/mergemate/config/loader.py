"""Config discovery and loading utilities."""

from pathlib import Path
from typing import Any

import yaml

from mergemate.config.models import AppConfig

PACKAGE_DEFAULTS_PATH = Path(__file__).with_name("defaults.yaml")


def _discover_default_local_config_path() -> Path:
    package_path = PACKAGE_DEFAULTS_PATH.resolve()
    for candidate in package_path.parents:
        if (candidate / "pyproject.toml").exists():
            return candidate / "config" / "config.yaml"
    return Path.cwd() / "config" / "config.yaml"


DEFAULT_LOCAL_CONFIG_PATH = _discover_default_local_config_path()


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
            continue
        merged[key] = value
    return merged


def resolve_config_path(explicit_path: Path | None = None) -> Path:
    if explicit_path is not None:
        return explicit_path.expanduser().resolve()
    return _discover_default_local_config_path().resolve()


def load_runtime_settings(explicit_path: Path | None = None) -> AppConfig:
    defaults = _read_yaml(PACKAGE_DEFAULTS_PATH)
    local_config_path = _discover_default_local_config_path().resolve()
    effective = _deep_merge(defaults, _read_yaml(local_config_path))
    if explicit_path is not None:
        resolved_explicit_path = explicit_path.expanduser().resolve()
        if resolved_explicit_path != local_config_path:
            effective = _deep_merge(effective, _read_yaml(resolved_explicit_path))
    return AppConfig.model_validate(effective)