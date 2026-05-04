import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mergemate.interfaces.telegram.health import WebhookHealthServer, WebhookReadinessState


def _request(method: str, url: str):
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def test_health_server_reports_starting_then_ready() -> None:
    state = WebhookReadinessState()
    server = WebhookHealthServer(
        listen_host="127.0.0.1",
        listen_port=0,
        path="/healthz",
        state=state,
    )
    server.start()

    try:
        url = f"http://127.0.0.1:{server.listen_port}/healthz"
        status, body = _request("GET", url)
        assert status == 503
        assert json.loads(body) == {"status": "starting"}

        state.mark_ready()
        status, body = _request("GET", url)
        assert status == 200
        assert json.loads(body) == {"status": "ready"}

        status, body = _request("HEAD", url)
        assert status == 200
        assert body == b""
    finally:
        server.stop()


def test_mark_failed_changes_status_and_sets_detail() -> None:
    state = WebhookReadinessState()
    assert state.snapshot() == {"status": "starting"}

    state.mark_failed("Connection refused")
    assert state.snapshot() == {"status": "failed", "detail": "Connection refused"}

    state.mark_failed("")
    assert state.snapshot() == {"status": "failed", "detail": ""}


def test_health_server_returns_not_found_for_other_paths() -> None:
    state = WebhookReadinessState()
    server = WebhookHealthServer(
        listen_host="127.0.0.1",
        listen_port=0,
        path="/healthz",
        state=state,
    )
    server.start()

    try:
        status, _ = _request("GET", f"http://127.0.0.1:{server.listen_port}/wrong")
        assert status == 404
    finally:
        server.stop()