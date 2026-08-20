"""v0.8.66 (audit S-4) — env-gated in-memory rate limiter.

Default OFF (no env) so the single-user desktop path is unchanged; when
DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN is set, excess requests per IP get 429.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.rate_limit import RateLimitMiddleware, _limit_per_min


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/api/thing")
    async def thing():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    return app


@pytest.mark.parametrize(
    "val,expected",
    [
        (None, 0),
        ("", 0),
        ("0", 0),
        ("-3", 0),
        ("abc", 0),
        ("5", 5),
    ],
)
def test_limit_parsing(monkeypatch, val, expected):
    if val is None:
        monkeypatch.delenv("DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN", raising=False)
    else:
        monkeypatch.setenv("DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN", val)
    assert _limit_per_min() == expected


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN", raising=False)
    client = TestClient(_app())
    # Way more than any sane limit — all 200 because the limiter is OFF.
    for _ in range(50):
        assert client.get("/api/thing").status_code == 200


def test_limits_excess_requests(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN", "3")
    client = TestClient(_app())
    codes = [client.get("/api/thing").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429 and codes[4] == 429
    # 429 carries a Retry-After header.
    r = client.get("/api/thing")
    assert r.status_code == 429
    assert "retry-after" in {k.lower() for k in r.headers}


def test_health_is_exempt(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_RATE_LIMIT_PER_MIN", "1")
    client = TestClient(_app())
    # /health is exempt — never limited even past the limit.
    for _ in range(10):
        assert client.get("/health").status_code == 200
