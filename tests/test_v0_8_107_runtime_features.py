"""v0.8.107 — a packaged build can be told a feature was rolled back.

Frontend flags are `NEXT_PUBLIC_*`, which Next INLINES at build time, so a
packaged .app has its UI feature set frozen in the bundle. Turning a feature off
server-side left its controls rendered and dead — the client never learned the
backend had stopped supporting it. That is §4.3 of PROJECT-DEEP-DIVE, and it is
what produced the dead Refresh/Remove buttons in the source gallery (patched in
v0.8.86 for that one surface, without addressing the cause).

`GET /api/features` publishes the backend predicates that are the real
authority. These tests pin the two properties that make it safe to consume:
every advertised key is a real boolean, and the endpoint performs no I/O beyond
reading env — a feature check that can hang is worse than a stale flag.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app

# The frontend helper names these keys; drift here silently strands a flag on
# its inlined default, which is the exact failure this endpoint exists to end.
EXPECTED_KEYS = {
    "evidenceStudio",
    "visualRefresh",
    "modelFleet",
    "researchRuns",
    "studyWorkbench",
    "sourceVisuals",
}


@pytest.fixture
def client():
    # Bare TestClient, not `with TestClient(app)`: the context-manager form runs
    # the app lifespan, which runs DB migrations and fails without a live
    # SurrealDB. /api/features touches no database, so the house pattern (see
    # tests/test_config_source_upload_cap.py) is both correct and the point —
    # a feature check that needs the database is a feature check that can hang.
    return TestClient(app)


def test_features_endpoint_publishes_every_paired_flag(client):
    response = client.get("/api/features")
    assert response.status_code == 200
    features = response.json()["features"]
    assert set(features) == EXPECTED_KEYS


def test_every_value_is_a_real_boolean(client):
    """Not a truthy string.

    `applyRuntimeFeatures` adopts booleans only, so a string here would be
    silently discarded and the flag would stay on its inlined default — a
    rolled-back feature would keep rendering.
    """
    features = client.get("/api/features").json()["features"]
    for name, value in features.items():
        assert isinstance(value, bool), f"{name} is {type(value).__name__}"


def test_it_reflects_the_backend_predicate_not_a_constant(client, monkeypatch):
    """The endpoint must read the flag, not hardcode an answer."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", "1")
    assert client.get("/api/features").json()["features"]["sourceVisuals"] is True

    monkeypatch.setenv("DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED", "0")
    assert client.get("/api/features").json()["features"]["sourceVisuals"] is False


def test_the_keys_match_the_frontend_helper_names():
    """Guard the mapping that makes this endpoint usable at all.

    Reads the TypeScript rather than trusting a comment: if someone renames a
    helper's runtime key without updating the endpoint, the flag silently stops
    being overridable and the packaged build goes back to being unrollbackable.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "frontend/src/lib/features.ts"
    ).read_text(encoding="utf-8")
    for key in EXPECTED_KEYS:
        assert f"'{key}'" in source, f"frontend/src/lib/features.ts never uses {key}"
