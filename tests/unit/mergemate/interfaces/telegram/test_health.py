import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from mergemate.interfaces.telegram.health import WebhookHealthServer, WebhookReadinessState


def _request(method: str, url: str):
    request = Request(url, method=method)
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


@pytest.fixture
def health_server():
    state = WebhookReadinessState()
    server = WebhookHealthServer(
        listen_host="127.0.0.1",
        listen_port=0,
        path="/healthz",
        state=state,
    )
    server.start()
    yield state, server
    server.stop()


def test_health_server_reports_starting_then_ready(health_server) -> None:
    state, server = health_server
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


def test_mark_failed_changes_status_and_sets_detail() -> None:
    state = WebhookReadinessState()
    assert state.snapshot() == {"status": "starting"}

    state.mark_failed("Connection refused")
    assert state.snapshot() == {"status": "failed", "detail": "Connection refused"}

    state.mark_failed("")
    assert state.snapshot() == {"status": "failed", "detail": ""}


def test_health_server_returns_not_found_for_other_paths(health_server) -> None:
    _, server = health_server
    status, _ = _request("GET", f"http://127.0.0.1:{server.listen_port}/wrong")
    assert status == 404


def test_health_head_returns_service_unavailable_when_not_ready(health_server) -> None:
    _, server = health_server
    url = f"http://127.0.0.1:{server.listen_port}/healthz"
    status, body = _request("HEAD", url)
    assert status == 503
    assert body == b""


def test_health_head_returns_not_found_for_other_paths(health_server) -> None:
    _, server = health_server
    status, _ = _request("HEAD", f"http://127.0.0.1:{server.listen_port}/wrong")
    assert status == 404
