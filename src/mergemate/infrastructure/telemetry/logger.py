"""Logging configuration."""

import logging
from pathlib import Path


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


def log_startup_configuration(settings, *, config_path: Path, database_path: Path) -> None:
    telegram_settings = settings.telegram
    webhook_enabled = telegram_settings.mode == "webhook"
    webhook_url = settings.resolve_telegram_webhook_url() if webhook_enabled else "disabled"
    secret_validation_enabled = bool(
        webhook_enabled and telegram_settings.webhook_secret_token_env
    )
    readiness_enabled = bool(
        webhook_enabled and telegram_settings.webhook_healthcheck_enabled
    )
    readiness_bind = (
        f"{telegram_settings.webhook_healthcheck_listen_host}:"
        f"{telegram_settings.webhook_healthcheck_listen_port}"
        f"{telegram_settings.webhook_healthcheck_path}"
        if readiness_enabled
        else "disabled"
    )

    logging.getLogger(__name__).info(
        "MergeMate startup config_path=%s database_path=%s telegram_mode=%s webhook_url=%s webhook_secret_token_validation=%s readiness_endpoint=%s",
        config_path,
        database_path,
        telegram_settings.mode,
        webhook_url,
        secret_validation_enabled,
        readiness_bind,
    )