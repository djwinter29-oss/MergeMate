"""Config discovery and loading utilities."""

from pathlib import Path
from typing import Any

import yaml

from mergemate.config.models import AppConfig

PACKAGE_DEFAULTS_PATH = Path(__file__).with_name("defaults.yaml")
DEFAULT_LOCAL_CONFIG_PATH = Path.cwd() / "config" / "config.yaml"


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
    return DEFAULT_LOCAL_CONFIG_PATH.resolve()


def load_runtime_settings(explicit_path: Path | None = None) -> AppConfig:
    defaults = _read_yaml(PACKAGE_DEFAULTS_PATH)
    effective = _deep_merge(defaults, _read_yaml(DEFAULT_LOCAL_CONFIG_PATH.resolve()))
    if explicit_path is not None:
        resolved_explicit_path = explicit_path.expanduser().resolve()
        if resolved_explicit_path != DEFAULT_LOCAL_CONFIG_PATH.resolve():
            effective = _deep_merge(effective, _read_yaml(resolved_explicit_path))
    return AppConfig.model_validate(effective)