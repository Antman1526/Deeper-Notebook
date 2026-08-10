"""v0.8.40 — Launcher↔API control plane tests.

Two layers:
  1. `desktop/launcher_control.py:ControlServer` — bind, auth, restart
     callback dispatch, error handling. Real HTTP socket, real
     threading; tests bring it up on 127.0.0.1 + tear it down.
  2. `api/routers/local_models.py:sidecar_restart` — endpoint validation
     + httpx proxy to the launcher. Launcher is mocked via env vars +
     a stub server.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from desktop.launcher_control import ControlServer

# ---------------------------------------------------------------------------
# ControlServer tests
# ---------------------------------------------------------------------------


@pytest.fixture
def server():
    """A running ControlServer bound to a random port. Each test gets
    a fresh server + token so test isolation is real."""
    srv = ControlServer()
    srv.start()
    yield srv
    srv.stop()


def _http_request(
    method: str,
    url: str,
    body: dict | None = None,
    token: str | None = None,
) -> tuple[int, dict]:
    """Tiny stdlib HTTP client — avoids dragging httpx in for the
    server-side tests. Returns (status_code, parsed_body)."""
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        # Read the response body even on 4xx/5xx so the test can
        # assert on the error detail.
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            body = {}
        return e.code, body


def test_server_starts_and_health_check(server):
    """Basic liveness — /health is unauthenticated by design so the
    API can verify the server is up before calling privileged paths."""
    code, body = _http_request("GET", f"{server.url}/health")
    assert code == HTTPStatus.OK
    assert body == {"ok": True}


def test_server_assigns_random_port(server):
    """OS-assigned port should be > 1024 (non-privileged) and != 0
    (the placeholder we set before start)."""
    assert server.port > 1024
    assert server.port < 65536


def test_token_required_for_protected_endpoints(server):
    code, body = _http_request(
        "POST", f"{server.url}/restart_sidecar",
        body={"kind": "chat"},
        # No token!
    )
    assert code == HTTPStatus.UNAUTHORIZED
    assert "Authorization" in (body.get("error") or "")


def test_token_must_match(server):
    code, body = _http_request(
        "POST", f"{server.url}/restart_sidecar",
        body={"kind": "chat"},
        token="completely-wrong-token-xyz",
    )
    assert code == HTTPStatus.UNAUTHORIZED


def test_restart_invokes_registered_callback(server):
    """Happy path: register a callback, POST with the token, assert
    the callback received the kind."""
    calls: list[str] = []

    def _cb(kind: str) -> tuple[bool, str]:
        calls.append(kind)
        return True, f"restarted {kind} (pid=1234)"

    server.register_callback("restart_sidecar", _cb)

    code, body = _http_request(
        "POST", f"{server.url}/restart_sidecar",
        body={"kind": "chat"},
        token=server.token,
    )
    assert code == HTTPStatus.OK
    assert body["ok"] is True
    assert body["kind"] == "chat"
    assert "restarted chat" in body["detail"]
    assert calls == ["chat"]


def test_restart_failure_returns_400(server):
    """Callback returns (False, detail) → 400 + detail surfaced."""
    def _cb(kind: str) -> tuple[bool, str]:
        return False, f"Sidecar {kind!r} was never spawned"

    server.register_callback("restart_sidecar", _cb)
    code, body = _http_request(
        "POST", f"{server.url}/restart_sidecar",
        body={"kind": "memory"},
        token=server.token,
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert body["ok"] is False
    assert "never spawned" in body["detail"]


def test_restart_callback_exception_returns_500(server):
    """Callback raising → 500 + readable error, never crashes server."""
    def _cb(kind: str) -> tuple[bool, str]:
        raise ValueError("simulated bad state")

    server.register_callback("restart_sidecar", _cb)
    code, body = _http_request(
        "POST", f"{server.url}/restart_sidecar",
        body={"kind": "chat"},
        token=server.token,
    )
    assert code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert "ValueError" in body["error"]
    assert "simulated bad state" in body["error"]


def test_restart_rejects_missing_kind(server):
    server.register_callback("restart_sidecar", lambda _k: (True, ""))
    code, body = _http_request(
        "POST", f"{server.url}/restart_sidecar",
        body={},
        token=server.token,
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "kind" in body["error"]


def test_restart_no_callback_returns_503(server):
    """No callback registered → 503 (rather than 500 — the request
    shape is fine, the server just isn't configured)."""
    code, body = _http_request(
        "POST", f"{server.url}/restart_sidecar",
        body={"kind": "chat"},
        token=server.token,
    )
    assert code == HTTPStatus.SERVICE_UNAVAILABLE


def test_unknown_path_returns_404(server):
    code, body = _http_request(
        "POST", f"{server.url}/some/unknown/path",
        body={"kind": "chat"},
        token=server.token,
    )
    assert code == HTTPStatus.NOT_FOUND


def test_stop_is_idempotent():
    """Calling stop() twice / before start() must not raise."""
    srv = ControlServer()
    srv.stop()  # never started
    srv.start()
    srv.stop()
    srv.stop()  # second stop after start


# ---------------------------------------------------------------------------
# /api/healthz/sidecars/{kind}/restart — endpoint proxy tests
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(local_models_router.router)
    return a


def test_restart_endpoint_unknown_kind_returns_404(app):
    with TestClient(app) as client:
        resp = client.post("/api/healthz/sidecars/badkind/restart")
    assert resp.status_code == 404


def test_restart_endpoint_503_when_control_url_missing(app, monkeypatch):
    """API running outside the launcher → no control URL → 503 with a
    user-friendly hint."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", raising=False)
    with TestClient(app) as client:
        resp = client.post("/api/healthz/sidecars/chat/restart")
    assert resp.status_code == 503
    assert "control plane" in resp.json()["detail"].lower()


def test_restart_endpoint_proxies_to_launcher_happy_path(app, monkeypatch):
    """Stand up a real ControlServer with a happy-path callback;
    point the env vars at it; verify the API endpoint round-trips."""
    srv = ControlServer()
    srv.start()
    try:
        calls: list[str] = []

        def _cb(kind: str) -> tuple[bool, str]:
            calls.append(kind)
            return True, f"restarted {kind}"

        srv.register_callback("restart_sidecar", _cb)

        monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL", srv.url)
        monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", srv.token)

        with TestClient(app) as client:
            resp = client.post("/api/healthz/sidecars/chat/restart")

        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["kind"] == "chat"
        assert "restarted chat" in body["detail"]
        assert calls == ["chat"]
    finally:
        srv.stop()


def test_restart_endpoint_502_when_launcher_unreachable(app, monkeypatch):
    """Set a control URL pointing at a dead port → connect-refused →
    502 from the API (NOT 500 — we know the network failed, not us)."""
    # Pick a port that's almost certainly not bound.
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL", "http://127.0.0.1:1",
    )
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", "dummy")
    with TestClient(app) as client:
        resp = client.post("/api/healthz/sidecars/chat/restart")
    assert resp.status_code == 502


def test_restart_endpoint_400_when_launcher_rejects(app, monkeypatch):
    """Launcher returns a 400 (e.g. "sidecar never spawned") — the API
    surfaces the detail with 400 rather than swallowing as 500."""
    srv = ControlServer()
    srv.start()
    try:
        def _cb(_k: str) -> tuple[bool, str]:
            return False, "Sidecar 'memory' was never spawned this session"

        srv.register_callback("restart_sidecar", _cb)
        monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_URL", srv.url)
        monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", srv.token)

        with TestClient(app) as client:
            resp = client.post("/api/healthz/sidecars/memory/restart")
        assert resp.status_code == 400
        assert "never spawned" in resp.json()["detail"]
    finally:
        srv.stop()
