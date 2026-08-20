"""v0.8.41 — curated MCP server recommendations tests.

Shape parity with the v0.8.39b GGUF recommendations endpoint so the
frontend can drop in the same one-click pattern. Covers:

  - RECOMMENDATIONS table shape (required fields, unique IDs, valid
    URL prefixes).
  - GET /api/mcp/recommendations response shape.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import mcp as mcp_router
from deeper_notebook.mcp import recommendations as recs_mod

# ---------------------------------------------------------------------------
# RECOMMENDATIONS table shape
# ---------------------------------------------------------------------------


def test_recommendations_have_required_fields():
    """Frontend card rendering would crash on undefined keys; lock the
    schema here."""
    required = {
        "id",
        "label",
        "description",
        "default_url",
        "install_url",
        "tags",
        "replaces",
    }
    for entry in recs_mod.RECOMMENDATIONS:
        missing = required - entry.keys()
        assert not missing, (
            f"Recommendation {entry.get('id', '?')!r} missing: {missing}"
        )
        # Sanity on types.
        assert isinstance(entry["tags"], list)
        assert entry["label"]
        assert entry["description"]
        # URLs must look like URLs — no relative paths, no garbage.
        assert entry["default_url"].startswith(("http://", "https://"))
        assert entry["install_url"].startswith(("http://", "https://"))


def test_recommendation_ids_unique():
    """No duplicate IDs — they're React keys."""
    ids = [r["id"] for r in recs_mod.RECOMMENDATIONS]
    assert len(ids) == len(set(ids))


def test_recommendations_default_url_is_localhost():
    """Recommendations are LOCAL-running services — default URL must
    point at 127.0.0.1 / localhost. A LAN/Internet URL would mean we
    accidentally curated a remote SaaS, defeating the local-first
    purpose."""
    for entry in recs_mod.RECOMMENDATIONS:
        url = entry["default_url"]
        assert "127.0.0.1" in url or "localhost" in url, (
            f"{entry['id']}: default_url {url!r} not localhost — local "
            f"recommendations only"
        )


def test_at_least_one_recommended_tag():
    """The frontend can render "Recommended" badge boosting for the
    most-broadly-useful pick (per the v0.8.39b GGUF pattern). Make
    sure at least one entry actually carries that tag."""
    has_recommended = any(
        "recommended" in r.get("tags", []) for r in recs_mod.RECOMMENDATIONS
    )
    assert has_recommended, (
        "At least one recommendation should carry the 'recommended' tag"
    )


# ---------------------------------------------------------------------------
# GET /api/mcp/recommendations endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(mcp_router.router)
    return a


def test_recommendations_endpoint_returns_list(app):
    """Smoke test the wire format. Reuses the same `{recommendations: [...]}`
    envelope as the GGUF endpoint so frontend code can share the shape."""
    with TestClient(app) as client:
        resp = client.get("/api/mcp/recommendations")
    assert resp.status_code == 200
    body = resp.json()
    assert "recommendations" in body
    assert len(body["recommendations"]) >= 1
    # First entry has the expected fields.
    first = body["recommendations"][0]
    assert "label" in first
    assert "default_url" in first
    assert "install_url" in first
    assert "tags" in first
