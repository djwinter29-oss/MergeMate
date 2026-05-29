"""Local readiness endpoint for webhook deployments."""

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock, Thread


class WebhookReadinessState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._status = "starting"
        self._detail = ""

    def mark_ready(self) -> None:
        with self._lock:
            self._status = "ready"

    def mark_stopping(self) -> None:
        with self._lock:
            self._status = "stopping"

    def mark_failed(self, detail: str) -> None:
        with self._lock:
            self._status = "failed"
            self._detail = detail

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            payload = {"status": self._status}
            if self._status == "failed":
                payload["detail"] = self._detail
            return payload


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class WebhookHealthServer:
    def __init__(
        self, *, listen_host: str, listen_port: int, path: str, state: WebhookReadinessState
    ) -> None:
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._path = path
        self._state = state
        self._server: _ReusableThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    @property
    def listen_port(self) -> int:
        return self._listen_port

    def start(self) -> None:
        if self._server is not None:
            return
        handler = self._build_handler()
        self._server = _ReusableThreadingHTTPServer((self._listen_host, self._listen_port), handler)
        self._listen_port = self._server.server_address[1]
        self._thread = Thread(
            target=self._server.serve_forever,
            name="mergemate-webhook-health",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        expected_path = self._path
        state = self._state

        class Handler(BaseHTTPRequestHandler):
            def _resolve_status(self) -> tuple[int | None, dict[str, str] | None]:
                if self.path != expected_path:
                    return None, None
                payload = state.snapshot()
                status_code = (
                    HTTPStatus.OK
                    if payload["status"] == "ready"
                    else HTTPStatus.SERVICE_UNAVAILABLE
                )
                return status_code, payload

            def _send_json_response(self, status_code: int, *, body: bytes | None = None) -> None:
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                if body is not None:
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body is not None:
                    self.wfile.write(body)

            def do_GET(self) -> None:
                status, payload = self._resolve_status()
                if status is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                body = json.dumps(payload).encode("utf-8")
                self._send_json_response(status, body=body)

            def do_HEAD(self) -> None:
                status, _ = self._resolve_status()
                if status is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json_response(status)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler
