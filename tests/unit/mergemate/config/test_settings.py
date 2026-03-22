from pathlib import Path

from mergemate.config import settings as settings_module


def test_get_settings_delegates_to_loader(monkeypatch) -> None:
    observed = {}

    def fake_load_runtime_settings(config_path: Path | None = None):
        observed["config_path"] = config_path
        return {"ok": True}

    monkeypatch.setattr(settings_module, "load_runtime_settings", fake_load_runtime_settings)

    result = settings_module.get_settings(Path("override.yaml"))

    assert result == {"ok": True}
    assert observed["config_path"] == Path("override.yaml")