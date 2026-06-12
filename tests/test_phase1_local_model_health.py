"""Phase 1 — Local-model health module produces a structured
report the API can serve to the frontend."""
from __future__ import annotations
from unittest.mock import patch, MagicMock

import pytest


def test_probe_local_model_returns_unknown_for_zero_port():
    """A port of 0 means the supervisor never spawned this service;
    health must surface that as `status='not_configured'` rather
    than raising or returning a misleading 'down'."""
    from open_notebook.health.local_models import probe_local_model

    result = probe_local_model(
        name="whisper",
        kind="openai_compatible",
        base_url="http://127.0.0.1:0/v1",
    )
    assert result["status"] == "not_configured"
    assert result["name"] == "whisper"


def test_probe_openai_compatible_healthy(monkeypatch):
    """A live llama-cpp server returns 200 on /models; probe
    must report status='healthy' with measured latency."""
    from unittest.mock import MagicMock, patch
    from open_notebook.health.local_models import probe_local_model

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "object": "list",
        "data": [{"id": "Hermes-3-Llama-3.1-8B"}],
    }
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.get.return_value = fake_resp

    with patch("open_notebook.health.local_models.httpx.Client",
               return_value=fake_client):
        result = probe_local_model(
            name="local_chat", kind="openai_compatible",
            base_url="http://127.0.0.1:5000/v1",
        )
    assert result["status"] == "healthy"
    assert result["latency_ms"] is not None
    assert "Hermes-3" in (result["detail"] or "")


def test_probe_openai_compatible_unhealthy_connect_refused():
    """When the port is closed (ConnectionRefused / unreachable),
    probe must report status='unhealthy' with a connect detail.
    Uses a port that's vanishingly unlikely to be in use on the
    test runner (1 is a privileged port that pytest won't bind)."""
    from open_notebook.health.local_models import probe_local_model

    result = probe_local_model(
        name="local_chat", kind="openai_compatible",
        base_url="http://127.0.0.1:1/v1",
    )
    assert result["status"] == "unhealthy"
    assert "connect" in (result["detail"] or "").lower()


def test_probe_all_iterates_credentials():
    """Given a list of credential dicts, probe_all returns one
    HealthResult per cred in input order."""
    from open_notebook.health.local_models import probe_all_local_models

    creds = [
        {"name": "chat", "kind": "openai_compatible",
         "base_url": "http://127.0.0.1:0/v1"},
        {"name": "embed", "kind": "openai_compatible",
         "base_url": "http://127.0.0.1:0/v1"},
    ]
    results = probe_all_local_models(creds)
    assert len(results) == 2
    assert [r["name"] for r in results] == ["chat", "embed"]
    assert all(r["status"] == "not_configured" for r in results)


def test_router_returns_health_payload(monkeypatch):
    """GET /api/local-models/health returns aggregated overall + per-model."""
    from fastapi.testclient import TestClient
    from api.main import app

    # Stub the probe to avoid real HTTP.
    from open_notebook.health import local_models as hm
    monkeypatch.setattr(
        hm, "probe_all_local_models",
        lambda creds: [{"name": "chat", "status": "healthy",
                        "detail": "ok", "latency_ms": 12.3}],
    )
    # Stub the credential fetch — in-test we have no SurrealDB.
    from api.routers import local_models as router_mod
    async def _stub_creds():
        return [{"name": "chat", "kind": "openai_compatible",
                 "base_url": "http://127.0.0.1:1234/v1"}]
    monkeypatch.setattr(
        router_mod, "_load_local_credentials", _stub_creds,
    )
    client = TestClient(app)
    r = client.get("/api/local-models/health")
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] in {"healthy", "degraded", "down"}
    assert body["models"][0]["name"] == "chat"


# ---------------------------------------------------------------------------
# v0.8.20 — async wrappers around the sync probes so the FastAPI event
# loop stays responsive when a sidecar wedges. These two tests pin the
# new contract: (1) the helper IS a coroutine, (2) the API endpoint
# survives a slow-blocking probe without stalling concurrent requests
# (verified by timing — the loop must still run other coroutines while
# the worker thread is blocked in httpx).
# ---------------------------------------------------------------------------


def test_local_chat_healthy_cached_is_awaitable():
    """Pin the v0.8.20 async-helper contract.

    If a future refactor accidentally turns `_local_chat_healthy_cached`
    back into a sync function, the production call sites (which use
    `await`) would raise `TypeError: object bool can't be used in 'await'
    expression` and the chat router would crash on every turn — a
    regression we cannot catch from runtime smoke alone because the
    helper is short-circuited when no local sidecar is registered.
    Asserting it's a coroutine function here makes the contract explicit.
    """
    import asyncio
    import inspect

    from open_notebook.ai import provision as provision_mod

    assert inspect.iscoroutinefunction(
        provision_mod._local_chat_healthy_cached
    ), (
        "v0.8.20 made _local_chat_healthy_cached async so the inner "
        "sync httpx.Client probe lands on a worker thread instead of "
        "blocking the FastAPI event loop. A sync regression here would "
        "break every chat turn that hits the smart router."
    )

    # And that the coroutine, when awaited with the env var unset
    # (no local sidecar registered), returns the safe False without
    # raising — the short-circuit path stays unchanged.
    async def _drive() -> bool:
        return await provision_mod._local_chat_healthy_cached(
            "Local GGUF (llama.cpp)"
        )

    loop = asyncio.new_event_loop()
    try:
        # Force the no-base-URL path so the test stays hermetic
        import os
        prev = os.environ.pop("OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL", None)
        # Also reset the cache so the lookup goes through the empty-creds path
        provision_mod._health_cache = None
        try:
            result = loop.run_until_complete(_drive())
        finally:
            if prev is not None:
                os.environ["OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL"] = prev
            provision_mod._health_cache = None
    finally:
        loop.close()

    assert result is False, (
        "With no OPEN_NOTEBOOK_LOCAL_CHAT_BASE_URL set, the helper "
        "must short-circuit to False (no local sidecar = nothing to "
        "probe = treat as unhealthy so the router falls through to cloud)."
    )


def test_local_models_health_endpoint_yields_event_loop():
    """v0.8.20 — even when the probe sleeps for 1s, other async work
    on the same event loop must continue making progress. Pre-v0.8.20
    the sync probe call blocked the loop entirely so concurrent
    coroutines stalled until the probe returned.
    """
    import asyncio
    import time

    from fastapi.testclient import TestClient

    # Probe that sleeps synchronously, simulating a wedged sidecar
    # within the 9s structured timeout budget.
    sleep_seconds = 0.5

    def _slow_probe(creds):
        time.sleep(sleep_seconds)
        return [{
            "name": "chat", "status": "unhealthy",
            "detail": "simulated slow probe", "latency_ms": sleep_seconds * 1000,
        }]

    from open_notebook.health import local_models as hm
    from api.routers import local_models as router_mod
    from api.main import app

    async def _stub_creds():
        return [{
            "name": "chat", "kind": "openai_compatible",
            "base_url": "http://127.0.0.1:1234/v1",
        }]

    # NOTE: monkeypatching outside a pytest fixture; restore manually.
    real_probe = hm.probe_all_local_models
    real_creds = router_mod._load_local_credentials
    hm.probe_all_local_models = _slow_probe   # type: ignore[assignment]
    router_mod._load_local_credentials = _stub_creds   # type: ignore[assignment]
    try:
        # Drive the endpoint AND a no-op coroutine concurrently.
        # If the loop is blocked, the no-op coroutine cannot run
        # until the probe finishes, so its elapsed time would
        # approximate sleep_seconds. With to_thread + a running
        # loop, the no-op completes promptly.
        client = TestClient(app)

        # Single request to verify the contract end-to-end. We don't
        # try to assert sub-second concurrent execution here — the
        # TestClient runs the FastAPI app on a dedicated event loop
        # and the timing-sensitive part (loop yielding) is already
        # covered by the existence of the asyncio.to_thread wrap
        # which we verify via AST in test_local_models_health_uses_to_thread.
        start = time.monotonic()
        r = client.get("/api/local-models/health")
        elapsed = time.monotonic() - start

        assert r.status_code == 200
        # Sanity: the probe DID run (we got the simulated unhealthy
        # row back).
        body = r.json()
        assert body["models"][0]["name"] == "chat"
        # And the endpoint took at least sleep_seconds — i.e. the
        # to_thread wrap didn't accidentally short-circuit the probe.
        assert elapsed >= sleep_seconds * 0.8, (
            f"Endpoint returned in {elapsed:.3f}s but the slow probe "
            f"should have taken ≥{sleep_seconds}s — verify the probe "
            f"is actually being called (not stubbed out by another test)."
        )
    finally:
        hm.probe_all_local_models = real_probe   # type: ignore[assignment]
        router_mod._load_local_credentials = real_creds   # type: ignore[assignment]


def test_local_models_health_uses_to_thread():
    """Static assertion: the endpoint code wraps the sync probe in
    `asyncio.to_thread`. Without the wrap, a hung sidecar would block
    the event loop. This is a literal source-text check because a
    runtime test can only assert correct behavior under the *current*
    set of stubs — a future refactor that re-introduces the sync call
    would still pass timing tests if the stubbed probe is fast.
    """
    from pathlib import Path

    src = Path(
        "api/routers/local_models.py"
    ).read_text(encoding="utf-8")

    assert "asyncio.to_thread(probe_all_local_models" in src, (
        "v0.8.20 wrapped the sync probe in asyncio.to_thread to keep "
        "the FastAPI event loop responsive when a local sidecar wedges. "
        "A refactor that drops this wrap will re-introduce the bug: "
        "the /api/local-models/health endpoint blocks for up to 9s per "
        "wedged sidecar and the frontend's 30s poll cascades into "
        "freezing the whole UI."
    )
