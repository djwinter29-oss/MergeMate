from pathlib import Path

from mergemate.application.services.config_service import ConfigService
from mergemate.application.services import config_service as config_service_module


def test_config_service_load_delegates_to_get_settings(monkeypatch) -> None:
    observed = {}

    def fake_get_settings(config_path: Path | None = None):
        observed["config_path"] = config_path
        return {"loaded": True}

    monkeypatch.setattr(config_service_module, "get_settings", fake_get_settings)

    result = ConfigService().load(Path("config.yaml"))

    assert result == {"loaded": True}
    assert observed["config_path"] == Path("config.yaml")