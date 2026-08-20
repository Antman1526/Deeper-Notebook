"""v0.7.119 — regression test for v0.7.95's /transformations/execute timeout.

v0.7.95 wrapped `transformation_graph.ainvoke()` in `asyncio.wait_for(
timeout=DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC)` (default 180s). This test
verifies:

  * The timeout fires when the graph hangs past the budget.
  * The HTTP response is 504 (not 500) — which only became correct
    after v0.7.109's `except HTTPException: raise` guard was added.
  * The detail message names the env knob so the user knows how to
    raise it.

Mocks `transformation_graph.ainvoke`, `Transformation.get`, and
`Model.get` so the test doesn't need a database or LangGraph runtime.
Companion to `tests/test_chat_execute_timeout.py`.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import transformations as xform_router


@pytest.fixture()
def app():
    a = FastAPI()
    a.include_router(xform_router.router, prefix="/api")
    return a


@pytest.fixture()
def client(app):
    return TestClient(app)


@pytest.fixture()
def stub_domain(monkeypatch):
    """Stub Transformation.get + Model.get so the endpoint can locate
    both records without hitting SurrealDB."""
    fake_transformation = SimpleNamespace(
        id="transformation:test",
        name="Test",
        title="Test",
        prompt="Summarize this",
        apply_default=False,
        description="test",
    )
    fake_model = SimpleNamespace(id="model:test", name="gpt-test")

    async def _get_xform(_id):
        return fake_transformation if _id == "transformation:test" else None

    async def _get_model(_id):
        return fake_model if _id == "model:test" else None

    monkeypatch.setattr(
        xform_router.Transformation,
        "get",
        staticmethod(_get_xform),
    )
    monkeypatch.setattr(xform_router.Model, "get", staticmethod(_get_model))


def test_transformation_execute_timeout_returns_504_with_env_knob_hint(
    client,
    stub_domain,
    monkeypatch,
):
    """v0.7.119 — A hung graph past DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC
    returns 504 (NOT 500, post v0.7.109 fix) with the env-knob name
    in the detail."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC", "1")

    async def _hanging_ainvoke(state, config=None):
        await asyncio.sleep(60)
        return {"output": "never"}

    monkeypatch.setattr(
        xform_router,
        "transformation_graph",
        SimpleNamespace(ainvoke=_hanging_ainvoke),
    )

    r = client.post(
        "/api/transformations/execute",
        json={
            "transformation_id": "transformation:test",
            "model_id": "model:test",
            "input_text": "Hello world.",
        },
    )
    assert r.status_code == 504, r.text
    detail = r.json()["detail"]
    assert "DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC" in detail
    assert "timed out" in detail.lower()


def test_transformation_execute_returns_200_when_graph_returns_in_time(
    client,
    stub_domain,
    monkeypatch,
):
    """v0.7.119 — Negative-space check: a fast graph response is NOT
    spuriously timeout-killed."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC", "5")

    async def _fast_ainvoke(state, config=None):
        return {"output": "transformed text"}

    monkeypatch.setattr(
        xform_router,
        "transformation_graph",
        SimpleNamespace(ainvoke=_fast_ainvoke),
    )

    r = client.post(
        "/api/transformations/execute",
        json={
            "transformation_id": "transformation:test",
            "model_id": "model:test",
            "input_text": "Hello world.",
        },
    )
    assert r.status_code != 504, r.text


def test_transformation_execute_404_when_transformation_missing(
    client,
    stub_domain,
):
    """v0.7.119 — Pre-existing 404 path: typed HTTPException(404) must
    survive the `except Exception` block (v0.7.109 fix). Before that
    fix, this would have been a 500."""
    r = client.post(
        "/api/transformations/execute",
        json={
            "transformation_id": "transformation:does-not-exist",
            "model_id": "model:test",
            "input_text": "Hello world.",
        },
    )
    assert r.status_code == 404, r.text
    assert "Transformation not found" in r.json()["detail"]


def test_transformation_execute_404_when_model_missing(
    client,
    stub_domain,
):
    """v0.7.119 — Same v0.7.109 fix coverage for the model-not-found
    branch."""
    r = client.post(
        "/api/transformations/execute",
        json={
            "transformation_id": "transformation:test",
            "model_id": "model:does-not-exist",
            "input_text": "Hello world.",
        },
    )
    assert r.status_code == 404, r.text
    assert "Model not found" in r.json()["detail"]
