import logging
from pathlib import Path
from types import SimpleNamespace

from mergemate.config.logging import configure_logging, log_startup_configuration


def test_configure_logging_is_reexported() -> None:
    assert callable(configure_logging)
    assert "configure_logging" in __import__("mergemate.config.logging", fromlist=["__all__"]).__all__
    assert "log_startup_configuration" in __import__("mergemate.config.logging", fromlist=["__all__"]).__all__


def test_configure_logging_defaults_unknown_level_to_info(monkeypatch) -> None:
    captured = {}

    def fake_basicConfig(*, level):
        captured["level"] = level

    monkeypatch.setattr(logging, "basicConfig", fake_basicConfig)

    configure_logging("unknown")

    assert captured["level"] == logging.INFO


def test_log_startup_configuration_reports_polling_without_webhook_details(caplog) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="polling",
            webhook_secret_token_env=None,
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        ),
        resolve_telegram_webhook_url=lambda: (_ for _ in ()).throw(AssertionError("should not resolve webhook url")),
    )

    with caplog.at_level(logging.INFO):
        log_startup_configuration(
            settings,
            config_path=Path("/tmp/config.yaml"),
            database_path=Path("/tmp/runtime.db"),
        )

    assert "telegram_mode=polling" in caplog.text
    assert "webhook_url=disabled" in caplog.text
    assert "webhook_secret_token_validation=False" in caplog.text
    assert "readiness_endpoint=disabled" in caplog.text


def test_log_startup_configuration_reports_webhook_details_without_secret_value(caplog) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_secret_token_env="TELEGRAM_WEBHOOK_SECRET",
            webhook_healthcheck_enabled=True,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        ),
        resolve_telegram_webhook_url=lambda: "https://bot.example.com/telegram/webhook",
    )

    with caplog.at_level(logging.INFO):
        log_startup_configuration(
            settings,
            config_path=Path("/tmp/config.yaml"),
            database_path=Path("/tmp/runtime.db"),
        )

    assert "telegram_mode=webhook" in caplog.text
    assert "webhook_url=https://bot.example.com/telegram/webhook" in caplog.text
    assert "webhook_secret_token_validation=True" in caplog.text
    assert "readiness_endpoint=127.0.0.1:8081/healthz" in caplog.text
    assert "TELEGRAM_WEBHOOK_SECRET" not in caplog.text


def test_log_startup_configuration_reports_disabled_readiness_for_webhook_mode(caplog) -> None:
    settings = SimpleNamespace(
        telegram=SimpleNamespace(
            mode="webhook",
            webhook_secret_token_env="TELEGRAM_WEBHOOK_SECRET",
            webhook_healthcheck_enabled=False,
            webhook_healthcheck_listen_host="127.0.0.1",
            webhook_healthcheck_listen_port=8081,
            webhook_healthcheck_path="/healthz",
        ),
        resolve_telegram_webhook_url=lambda: "https://bot.example.com/telegram/webhook",
    )

    with caplog.at_level(logging.INFO):
        log_startup_configuration(
            settings,
            config_path=Path("/tmp/config.yaml"),
            database_path=Path("/tmp/runtime.db"),
        )

    assert "telegram_mode=webhook" in caplog.text
    assert "readiness_endpoint=disabled" in caplog.text
