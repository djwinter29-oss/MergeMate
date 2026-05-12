"""Tests for bootstrap plugin loading coverage (discover_workflow_plugins + _load_workflow_config_plugins).

Target: bootstrap.py lines 42-104, currently 84% uncovered -> 95%+.
"""

from types import SimpleNamespace

from mergemate import bootstrap as bootstrap_module


# ── discover_workflow_plugins ─────────────────────────────────────────────────


def test_discover_workflow_plugins_no_entries(monkeypatch) -> None:
    """discover_workflow_plugins no-ops gracefully when no entry points exist."""
    monkeypatch.setattr("importlib.metadata.entry_points", lambda *, group: [])
    bootstrap_module.discover_workflow_plugins()


def test_discover_workflow_plugins_success(monkeypatch) -> None:
    """discover_workflow_plugins calls each entry point's registration function."""
    calls: list[str] = []

    def _make_entry_point(name: str):
        def _load(_self):
            return lambda: calls.append(name)

        return type("EntryPoint", (), {"name": name, "load": _load})()

    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda *, group: [_make_entry_point("plugin_a"), _make_entry_point("plugin_b")],
    )
    bootstrap_module.discover_workflow_plugins()
    assert calls == ["plugin_a", "plugin_b"]


def test_discover_workflow_plugins_failure_logs_warning(monkeypatch, caplog) -> None:
    """discover_workflow_plugins logs a warning when a plugin raises."""
    import logging

    def _good_plugin():
        pass

    def _failing_plugin():
        raise RuntimeError("plugin oops")

    monkeypatch.setattr(
        "importlib.metadata.entry_points",
        lambda *, group: iter(
            [
                type("EntryPoint", (), {"name": "good", "load": lambda s: _good_plugin})(),
                type("EntryPoint", (), {"name": "bad", "load": lambda s: _failing_plugin})(),
            ]
        ),
    )
    caplog.set_level(logging.WARNING)
    bootstrap_module.discover_workflow_plugins()
    assert "Failed to load workflow plugin: bad" in caplog.text


# ── _load_workflow_config_plugins ──────────────────────────────────────────────


def test_load_workflow_config_plugins_empty_list() -> None:
    """_load_workflow_config_plugins no-ops when workflow_plugins is empty."""
    settings = SimpleNamespace(workflow_plugins=[])
    bootstrap_module._load_workflow_config_plugins(settings)


def test_load_workflow_config_plugins_string_entry(tmp_path) -> None:
    """_load_workflow_config_plugins imports a string entry and calls register()."""
    import importlib
    import sys

    pkg_dir = tmp_path / "pkg_a"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "workflows.py").write_text(
        "register_called = False\n"
        "def register(config=None):\n"
        "    global register_called\n"
        "    register_called = True\n"
    )
    sys.path.insert(0, str(tmp_path))
    try:
        settings = SimpleNamespace(workflow_plugins=["pkg_a.workflows"])
        bootstrap_module._load_workflow_config_plugins(settings)
        mod = importlib.import_module("pkg_a.workflows")
        assert getattr(mod, "register_called", False)
    finally:
        sys.path.pop(0)


def test_load_workflow_config_plugins_dict_entry(monkeypatch) -> None:
    """_load_workflow_config_plugins handles dict entries with config kwargs."""
    import sys

    module_path = "fakemodule_dict_entry_test"

    def fake_register(config=None):
        fake_register.received = config

    module = type(sys)(module_path)
    module.register = fake_register
    monkeypatch.setitem(sys.modules, module_path, module)

    settings = SimpleNamespace(
        workflow_plugins=[{"module": module_path, "timeout": 30, "retries": 3}]
    )
    bootstrap_module._load_workflow_config_plugins(settings)
    assert fake_register.received == {"timeout": 30, "retries": 3}


def test_load_workflow_config_plugins_string_entry_no_register(monkeypatch) -> None:
    """_load_workflow_config_plugins tolerates a module without register()."""
    import sys

    module_path = "fakemodule_no_register"
    module = type(sys)(module_path)
    monkeypatch.setitem(sys.modules, module_path, module)

    settings = SimpleNamespace(workflow_plugins=[module_path])
    bootstrap_module._load_workflow_config_plugins(settings)


def test_load_workflow_config_plugins_import_error_logs_warning(monkeypatch, caplog) -> None:
    """_load_workflow_config_plugins logs a warning when module doesn't exist."""
    import logging

    settings = SimpleNamespace(workflow_plugins=["nonexistent.module.path"])
    caplog.set_level(logging.WARNING)
    bootstrap_module._load_workflow_config_plugins(settings)
    assert "Failed to load config workflow plugin: nonexistent.module.path" in caplog.text


def test_load_workflow_config_plugins_dict_missing_module_key(monkeypatch, caplog) -> None:
    """_load_workflow_config_plugins logs a warning when dict has no 'module' key."""
    import logging

    settings = SimpleNamespace(workflow_plugins=[{"timeout": 30}])
    caplog.set_level(logging.WARNING)
    bootstrap_module._load_workflow_config_plugins(settings)
    assert "Failed to load config workflow plugin" in caplog.text
