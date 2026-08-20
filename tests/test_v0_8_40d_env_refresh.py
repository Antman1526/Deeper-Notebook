"""v0.8.40d — /api/system/env-refresh endpoint tests.

The launcher posts to this after a successful hot_swap_chat so the
running API's smart router sees the new GGUF's n_ctx without app
relaunch. Closes the v0.8.40b "stale n_ctx" limitation.

Tests:
  - 503 when DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN not in env (API
    running outside the desktop launcher).
  - 401 when token header missing / malformed / mismatched.
  - 200 + os.environ mutated for whitelisted vars.
  - 200 with rejected list populated for non-whitelisted var names
    (defense — never blindly mutate os.environ).
  - Mixed whitelist + reject in a single payload returns both lists.
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import system as system_router


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(system_router.router)
    return a


@pytest.fixture
def token_env(monkeypatch):
    """Configure the API with a known control token."""
    token = "test-token-abcdefghij"
    monkeypatch.setenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", token)
    return token


def test_endpoint_503_when_no_token_configured(app, monkeypatch):
    """API running outside the launcher → no control token in env →
    503 with a clear hint. Without this, the launcher's best-effort
    push would retry-loop against a 401 forever."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", raising=False)
    with TestClient(app) as client:
        resp = client.post(
            "/api/system/env-refresh",
            json={"vars": {"DEEPER_NOTEBOOK_LOCAL_N_CTX": "65536"}},
            headers={"Authorization": "Bearer anything"},
        )
    assert resp.status_code == 503
    assert (
        "control plane" in resp.json()["detail"].lower()
        or "control_token" in resp.json()["detail"].lower()
    )


def test_endpoint_401_when_authorization_header_missing(app, token_env):
    with TestClient(app) as client:
        resp = client.post(
            "/api/system/env-refresh",
            json={"vars": {"DEEPER_NOTEBOOK_LOCAL_N_CTX": "65536"}},
        )
    assert resp.status_code == 401


def test_endpoint_401_when_authorization_header_malformed(app, token_env):
    with TestClient(app) as client:
        resp = client.post(
            "/api/system/env-refresh",
            json={"vars": {"DEEPER_NOTEBOOK_LOCAL_N_CTX": "65536"}},
            headers={"Authorization": "WrongScheme token"},
        )
    assert resp.status_code == 401


def test_endpoint_401_when_token_mismatched(app, token_env):
    with TestClient(app) as client:
        resp = client.post(
            "/api/system/env-refresh",
            json={"vars": {"DEEPER_NOTEBOOK_LOCAL_N_CTX": "65536"}},
            headers={"Authorization": "Bearer wrong-token-xyz"},
        )
    assert resp.status_code == 401


def test_endpoint_updates_whitelisted_var(app, token_env, monkeypatch):
    """Happy path — env var actually mutated in os.environ."""
    # Start with a known different value so the assertion proves the
    # mutation, not coincidence.
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_N_CTX", "8192")

    with TestClient(app) as client:
        resp = client.post(
            "/api/system/env-refresh",
            json={"vars": {"DEEPER_NOTEBOOK_LOCAL_N_CTX": "65536"}},
            headers={"Authorization": f"Bearer {token_env}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == ["DEEPER_NOTEBOOK_LOCAL_N_CTX"]
    assert body["rejected"] == []
    # The mutation actually happened — provision.py would see this.
    assert os.environ["DEEPER_NOTEBOOK_LOCAL_N_CTX"] == "65536"


def test_endpoint_rejects_non_whitelisted_var(app, token_env, monkeypatch):
    """Defense — a compromised process must NOT be able to overwrite
    arbitrary env vars (PATH, PYTHONPATH, etc) and execute code on
    the next subprocess spawn. The whitelist is explicit."""
    # PATH is the canonical example of "do not let anyone overwrite this".
    original_path = os.environ.get("PATH", "")

    with TestClient(app) as client:
        resp = client.post(
            "/api/system/env-refresh",
            json={"vars": {"PATH": "/tmp/evil"}},
            headers={"Authorization": f"Bearer {token_env}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["updated"] == []
    assert body["rejected"] == ["PATH"]
    # PATH must be untouched.
    assert os.environ.get("PATH", "") == original_path


def test_endpoint_mixed_updates_and_rejects(app, token_env, monkeypatch):
    """A single payload with both whitelisted + non-whitelisted vars
    applies the whitelisted ones and reports the others as rejected.
    Lets the launcher submit best-effort batches without needing to
    pre-filter."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_LOCAL_N_CTX", "8192")
    original_path = os.environ.get("PATH", "")

    with TestClient(app) as client:
        resp = client.post(
            "/api/system/env-refresh",
            json={
                "vars": {
                    "DEEPER_NOTEBOOK_LOCAL_N_CTX": "32768",
                    "PATH": "/tmp/evil",
                    "DEEPER_NOTEBOOK_NONEXISTENT": "foo",
                },
            },
            headers={"Authorization": f"Bearer {token_env}"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "DEEPER_NOTEBOOK_LOCAL_N_CTX" in body["updated"]
    assert set(body["rejected"]) == {"PATH", "DEEPER_NOTEBOOK_NONEXISTENT"}
    assert os.environ["DEEPER_NOTEBOOK_LOCAL_N_CTX"] == "32768"
    assert os.environ.get("PATH", "") == original_path
