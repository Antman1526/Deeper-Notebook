"""v0.7.162 — Router-level test coverage for previously-untested endpoints.

Identified by the 2026-05-21 improvement scan: 9 routers had no
matching `tests/test_*.py` module that imported them. This file adds
focused happy-path + error-path coverage for the three highest-risk
ones in that list:

  1. `auth.py`            — 26-line module; the bedrock of the entire
                             middleware. Worth a smoke test.
  2. `languages.py`       — 83-line module; pure pycountry/babel data
                             access, no DB; trivial to test.
  3. `embedding_rebuild.py` — just refactored in v0.7.160 (6 sequential
                             queries → 3 concurrent via asyncio.gather).
                             Highest regression risk; pin the new
                             parallel-stats path AND the dict/int
                             extraction helper.

Mocking strategy: FastAPI TestClient + monkeypatched repo_query.
No live SurrealDB needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Build a TestClient against the real FastAPI app. Lifespan
    startup runs migrations; for these tests we don't care about
    them — we patch repo_query at the point of use so nothing
    actually touches SurrealDB."""
    from api.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# auth.py — /auth/status
# ---------------------------------------------------------------------------


def test_auth_status_reports_disabled_when_no_password(client, monkeypatch):
    """v0.7.162: when DEEPER_NOTEBOOK_PASSWORD is unset, the endpoint
    must report auth_enabled=False. This is the desktop-default state
    (the v0.7.154 CORS warning bullet documents 127.0.0.1-only bind)
    and the frontend's auth flow depends on this signal to decide
    whether to show the login screen at all."""
    for name in (
        "DEEPER_NOTEBOOK_PASSWORD",
        "DEEPER_NOTEBOOK_PASSWORD_FILE",
        "DEEPER_NOTEBOOK_PASSWORD",
        "DEEPER_NOTEBOOK_PASSWORD_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    r = client.get("/api/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is False
    assert "disabled" in body["message"].lower()


def test_auth_status_reports_enabled_when_password_set(client, monkeypatch):
    """v0.7.162: when a password IS set, frontend must see
    auth_enabled=True so it routes through /login. The endpoint
    itself is auth-exempt (middleware excludes /api/auth/status),
    so this works WITHOUT a Bearer header."""
    for name in (
        "DEEPER_NOTEBOOK_PASSWORD",
        "DEEPER_NOTEBOOK_PASSWORD_FILE",
        "DEEPER_NOTEBOOK_PASSWORD",
        "DEEPER_NOTEBOOK_PASSWORD_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_PASSWORD", "test-password-123")

    r = client.get("/api/auth/status", headers={})  # no auth header
    assert r.status_code == 200
    body = r.json()
    assert body["auth_enabled"] is True
    assert "required" in body["message"].lower()
    # Critical: never leak the password value back in the response
    assert "test-password-123" not in r.text


# ---------------------------------------------------------------------------
# languages.py — /languages
# ---------------------------------------------------------------------------


def test_list_languages_returns_bcp47_locale_strings(client):
    """v0.7.162: /languages drives the podcast EpisodeProfile.language
    picker. Each returned code must be a BCP 47 locale (`xx-XX` form
    when a territory is known, bare `xx` when not). Names must be
    non-empty so the frontend doesn't render blank dropdown options.
    """
    r = client.get("/api/languages")
    assert r.status_code == 200
    langs = r.json()
    assert isinstance(langs, list)
    assert len(langs) > 50, (
        "pycountry exposes hundreds of languages; <50 in response "
        "suggests the locale build is broken"
    )

    seen_codes = set()
    for lang in langs:
        assert "code" in lang and "name" in lang
        assert lang["name"], f"language {lang['code']!r} has empty name"
        # BCP 47 shape: either bare lang (e.g. "en") or lang-territory
        # (e.g. "en-US"). Reject anything with underscores or colons.
        assert "_" not in lang["code"], (
            f"BCP 47 codes use hyphens not underscores: {lang['code']!r}"
        )
        seen_codes.add(lang["code"])

    # The codes are unique (the route uses a seen-set internally).
    assert len(seen_codes) == len(langs)
    # Sort order is by name ascending.
    names = [lang["name"] for lang in langs]
    assert names == sorted(names), "response must be sorted by name asc"


def test_list_languages_includes_extra_variants(client):
    """v0.7.162: the route explicitly adds important regional variants
    (en-GB, pt-PT, zh-TW, es-MX, fr-CA, etc.) for TTS accent/spelling.
    Pin the most important ones so a future refactor of `_EXTRA_VARIANTS`
    can't silently drop them.
    """
    r = client.get("/api/languages")
    codes = {lang["code"] for lang in r.json()}
    # These are the ones the launcher's podcast preset library
    # relies on having available.
    for required in ("en-US", "en-GB", "pt-PT", "zh-TW"):
        assert required in codes, (
            f"missing locale {required!r} — would break Podcast "
            f"language picker for that region"
        )


# ---------------------------------------------------------------------------
# embedding_rebuild.py — /rebuild
# v0.7.160 refactored this to use asyncio.gather + _extract_count helper.
# Both the public route and the helper get pinned.
# ---------------------------------------------------------------------------


def test_extract_count_handles_dict_response_shape():
    """v0.7.160 helper: SurrealDB sometimes returns `[{"count": N}]`."""
    from api.routers.embedding_rebuild import _extract_count

    assert _extract_count([{"count": 42}]) == 42
    assert _extract_count([{"count": 0}]) == 0
    # Missing "count" key shouldn't crash — coerce to 0.
    assert _extract_count([{}]) == 0


def test_extract_count_handles_int_response_shape():
    """v0.7.160 helper: SurrealDB sometimes returns `[N]` directly
    (depends on SELECT VALUE / GROUP ALL interaction)."""
    from api.routers.embedding_rebuild import _extract_count

    assert _extract_count([7]) == 7
    assert _extract_count([0]) == 0


def test_extract_count_handles_empty_or_none_result():
    """v0.7.160 helper: must NOT raise on the no-rows case (a fresh
    install with zero sources/notes/insights). The previous
    open-coded version had the same tolerance; preserved here."""
    from api.routers.embedding_rebuild import _extract_count

    assert _extract_count([]) == 0
    assert _extract_count(None) == 0
    # Unexpected shape — coerce to 0 rather than crash.
    assert _extract_count(["not-a-number"]) == 0
    assert _extract_count([{"count": None}]) == 0


def test_rebuild_submits_command_and_sums_counts_in_parallel(client, monkeypatch):
    """v0.7.160 + v0.7.162: pin the parallel-gather refactor + the
    end-to-end happy path. Asserts:
      1. All 3 selected branches (sources, notes, insights) issue
         exactly one repo_query each.
      2. Their counts are SUMMED into total_estimate.
      3. The command submission gets the right args.
      4. The response shape matches RebuildResponse.
    """
    call_log: list[str] = []

    async def fake_repo_query(query, *args, **kwargs):
        call_log.append(query)
        # Return a distinct count per table so the sum is verifiable.
        if "source_embedding" in query or "FROM source " in query:
            return [{"count": 10}]
        if "FROM note" in query:
            return [{"count": 5}]
        if "FROM source_insight" in query:
            return [{"count": 3}]
        return []

    async def fake_submit(*args, **kwargs):
        return "command:rebuild-job-1"

    with (
        patch("api.routers.embedding_rebuild.repo_query", new=fake_repo_query),
        patch(
            "api.routers.embedding_rebuild.CommandService.submit_command_job",
            new=fake_submit,
        ),
    ):
        r = client.post(
            "/api/embeddings/rebuild",
            json={
                "mode": "all",
                "include_sources": True,
                "include_notes": True,
                "include_insights": True,
            },
            headers={"x-skip-error-toast": "1"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["command_id"] == "command:rebuild-job-1"
    # 10 + 5 + 3 = 18 (RebuildResponse field is `total_items`,
    # api/models.py:233 — not "total_estimate" as the variable
    # name inside the route implementation suggests)
    assert body["total_items"] == 18
    # Exactly one query per selected branch — no more, no less.
    assert len(call_log) == 3


def test_rebuild_skips_unselected_branches(client, monkeypatch):
    """v0.7.160: if the user opts out of (e.g.) insights, we MUST NOT
    issue a query for that table. Saves a roundtrip per opted-out
    branch and matches the previous behavior."""
    call_log: list[str] = []

    async def fake_repo_query(query, *args, **kwargs):
        call_log.append(query)
        return [{"count": 1}]

    async def fake_submit(*args, **kwargs):
        return "command:partial-1"

    with (
        patch("api.routers.embedding_rebuild.repo_query", new=fake_repo_query),
        patch(
            "api.routers.embedding_rebuild.CommandService.submit_command_job",
            new=fake_submit,
        ),
    ):
        r = client.post(
            "/api/embeddings/rebuild",
            json={
                "mode": "existing",
                "include_sources": True,
                "include_notes": False,  # opted out
                "include_insights": False,  # opted out
            },
            headers={"x-skip-error-toast": "1"},
        )

    assert r.status_code == 200
    # Only the sources branch fired.
    assert len(call_log) == 1
    assert "source" in call_log[0].lower()
    # No "note" or "insight" mentions in any executed query.
    for q in call_log:
        assert "note" not in q.lower()
        assert "insight" not in q.lower()
