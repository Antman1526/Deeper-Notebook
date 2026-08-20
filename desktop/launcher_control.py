"""v0.8.40 — Launcher↔API control plane.

A tiny stdlib HTTP server running INSIDE the launcher process that the
API can call to trigger launcher-side operations (sidecar restart,
chat-GGUF hot-swap, etc). Foundation for v0.8.38b and v0.8.39c which
were deferred from earlier phases because there was no bidirectional
IPC channel between the API process and the launcher process.

Design choices:
  - **stdlib only** — `http.server.ThreadingHTTPServer`, no aiohttp /
    uvicorn dep added to the launcher. Avoids dragging async machinery
    into a launcher that's overwhelmingly sync (Supervisor + Popen).
  - **Bind to 127.0.0.1 only** — never expose this to the network.
  - **Random port** — discovered at start-up, exported to the API via
    `DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL`. No clash on multiple-launch
    machines.
  - **Bearer-token auth** — random 32-byte token generated per session,
    exported via `DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN`. Both env vars
    are scoped to the API subprocess via session_env. Any other
    process on 127.0.0.1 that lacks the token (browser tab, local
    web server, etc.) gets a 401 even if it guesses the port.
  - **Callback table** — the server holds a dict of {operation_name:
    sync_callable}. The Supervisor populates it at start-up. No
    import-cycle between launcher.py and this module.

Out of scope this iteration:
  - Long-poll / SSE for progress streaming during restart. Restart is
    fast enough (<5s typically) that synchronous request-response is
    fine. The API can poll /healthz/sidecars/{kind}/log afterwards
    for the new sidecar's startup log.
"""

from __future__ import annotations

import json
import logging
import secrets
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

log = logging.getLogger(__name__)


# Type alias for callbacks the Supervisor registers. Each takes a
# `kind` string (matching the API's allowlist: chat / embed / whisper
# / piper / memory) and returns (success: bool, detail: str).
RestartCallback = Callable[[str], tuple[bool, str]]


class _ControlHandler(BaseHTTPRequestHandler):
    """One per-request handler. Reads the registered callback off the
    server instance (`self.server.callbacks`) so a single ControlServer
    can drive multiple operations without a per-op subclass.

    Logs all errors at DEBUG to stderr (the launcher process's normal
    output channel); the access log noise is silenced because this
    server fires once per restart click — not a hot path.
    """

    # Silence BaseHTTPRequestHandler's noisy access log; we log
    # meaningful events ourselves via the `log` module-level logger.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        """Validate the Authorization: Bearer <token> header against
        the server's configured token. Constant-time compare so a
        timing-attack on the token isn't possible from a chatty
        localhost neighbor."""
        header = self.headers.get("Authorization", "")
        prefix = "Bearer "
        if not header.startswith(prefix):
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "Missing or malformed Authorization header",
                },
            )
            return False
        token = header[len(prefix) :].strip()
        expected = getattr(self.server, "token", "")
        if not expected or not secrets.compare_digest(token, expected):
            self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Invalid token"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802 — http.server convention
        # /health is unauthenticated so the API can verify the control
        # server is reachable before posting a privileged command.
        # Returns just a liveness signal — no sensitive info.
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown path"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._check_auth():
            return

        # v0.8.40b — multi-route dispatch. Each entry maps a URL path
        # to (required_body_field, callback_name). Keeping the table
        # narrow + flat is intentional — the launcher control plane
        # is a control surface, not a general HTTP framework.
        ROUTE_MAP = {
            "/restart_sidecar": ("kind", "restart_sidecar"),
            "/hot_swap_chat": ("path", "hot_swap_chat"),
        }
        if self.path not in ROUTE_MAP:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown path"})
            return
        required_field, callback_name = ROUTE_MAP[self.path]

        # Body: {<required_field>: "<value>"}
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 4096:
            # Defensive — a launcher-control request body should be
            # tiny; reject anything that looks malicious upfront.
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Body too large"}
            )
            return

        try:
            raw = self.rfile.read(length) if length > 0 else b""
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Body is not valid JSON"})
            return

        value = (body.get(required_field) or "").strip()
        if not value:
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"error": f"Missing {required_field!r} field"}
            )
            return

        cb: RestartCallback | None = getattr(self.server, "callbacks", {}).get(
            callback_name
        )
        if cb is None:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": f"{callback_name} callback not registered"},
            )
            return

        try:
            success, detail = cb(value)
        except Exception as exc:
            # Never let a callback exception kill the control server;
            # log + return a typed 500.
            log.exception("%s callback raised for value=%r", callback_name, value)
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error": f"Callback raised: {exc.__class__.__name__}: {exc}",
                },
            )
            return

        status = HTTPStatus.OK if success else HTTPStatus.BAD_REQUEST
        self._send_json(
            status,
            {
                "ok": success,
                # Echo the request field so callers can correlate. For
                # restart_sidecar this is 'kind'; for hot_swap_chat it's
                # 'path'.
                required_field: value,
                "detail": detail,
            },
        )


class ControlServer:
    """Threaded HTTP control server. Owns its own thread + socket; the
    Supervisor calls start() at boot and stop() at teardown.

    Usage:
        srv = ControlServer()
        srv.register_callback("restart_sidecar", supervisor.restart_sidecar)
        srv.start()  # → binds 127.0.0.1:<random>, exposes `.url` and `.token`

        # later
        srv.stop()
    """

    def __init__(self) -> None:
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._token: str = ""
        self._port: int = 0
        self._callbacks: dict[str, RestartCallback] = {}

    @property
    def token(self) -> str:
        return self._token

    @property
    def port(self) -> int:
        return self._port

    @property
    def url(self) -> str:
        """Base URL for the API to call. Empty when the server isn't
        running (start() failed or was never called)."""
        if self._port == 0:
            return ""
        return f"http://127.0.0.1:{self._port}"

    def register_callback(self, name: str, fn: RestartCallback) -> None:
        """Register a sync callback the HTTP handler will invoke for
        the matching operation. Pass the bound Supervisor method."""
        self._callbacks[name] = fn

    def start(self) -> None:
        """Bind to a random localhost port, generate a session token,
        and serve in a daemon thread.

        Idempotent — calling twice is a no-op (logs a warning)."""
        if self._server is not None:
            log.warning("ControlServer.start() called when already running")
            return

        # Generate a 32-byte URL-safe token. secrets.token_urlsafe(32)
        # gives ~43 chars of base64url — plenty for an auth bearer.
        self._token = secrets.token_urlsafe(32)

        # OS-assigned random port — pass 0 to socket; the kernel picks.
        # Use HTTPServer's address_family=AF_INET for explicit IPv4
        # binding (avoids dual-stack ambiguity on platforms that map
        # 127.0.0.1 differently to ::1).
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ControlHandler)
        # The handler reads these attributes off the server instance.
        server.token = self._token  # type: ignore[attr-defined]
        server.callbacks = self._callbacks  # type: ignore[attr-defined]

        # Discover the kernel-assigned port. `server_address[1]` is
        # set by socket.bind() inside HTTPServer.__init__.
        sockname = server.socket.getsockname()
        self._port = sockname[1]

        # Daemon thread so it doesn't block process exit; the Supervisor's
        # stop() is the clean teardown path.
        t = threading.Thread(
            target=server.serve_forever,
            name="launcher-control",
            daemon=True,
        )
        t.start()

        self._server = server
        self._thread = t
        log.info(
            "Launcher control server listening on %s (token redacted)",
            self.url,
        )

    def stop(self) -> None:
        """Shut down the HTTP server + join the thread. Safe to call
        multiple times / before start()."""
        if self._server is None:
            return
        try:
            self._server.shutdown()
            self._server.server_close()
        except Exception:
            # Best-effort teardown — log but never raise out of shutdown.
            log.debug("ControlServer.stop(): shutdown raised", exc_info=True)
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None
        self._port = 0
        self._token = ""


def _is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Test helper — check whether a localhost port is bindable.
    Module-public so test code can poll without re-implementing it."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        return False
