import logging

from mergemate.config.logging import configure_logging


def test_configure_logging_is_reexported() -> None:
    assert callable(configure_logging)
    assert "configure_logging" in __import__("mergemate.config.logging", fromlist=["__all__"]).__all__


def test_configure_logging_defaults_unknown_level_to_info(monkeypatch) -> None:
    captured = {}

    def fake_basicConfig(*, level):
        captured["level"] = level

    monkeypatch.setattr(logging, "basicConfig", fake_basicConfig)

    configure_logging("unknown")

    assert captured["level"] == logging.INFO
