from mergemate import main as main_module


def test_main_calls_cli_app(monkeypatch) -> None:
    observed = {"called": False}

    def fake_app() -> None:
        observed["called"] = True

    monkeypatch.setattr(main_module, "app", fake_app)

    main_module.main()

    assert observed["called"] is True