"""v0.7.209 — Five fixes from a fresh audit of source upload, auth
middleware, CORS, and memory shim.

1. **memory_shim missing `/models` endpoint.** Same root cause as
   v0.7.207's whisper/piper fix — the connection_tester probes
   `{base_url}/models` and 404s. Memory's base_url is registered
   WITHOUT a `/v1` prefix (see desktop/auto_register/memory.py),
   so the endpoint is `/models` (not `/v1/models`).

2. **HIGH — `content_process` ignored user ContentSettings.**
   `deeper_notebook/graphs/source.py:34-51` constructed a fresh
   `ContentSettings(...)` with hardcoded literals every time,
   silently overriding the singleton record the user toggled in
   Settings. Auto-delete-files, processing engine choices, YouTube
   language preferences — all ignored.

3. **MED — orphan "Processing..." source rows on extract failure.**
   `commands/source_commands.py:141-150` caught ValueError (extract
   failed on corrupted PDF / unreadable file / empty content) but
   left the placeholder source row created by the API in the DB
   forever. User saw a phantom source they couldn't make sense of.

4. **MED — `PasswordAuthMiddleware` class default `excluded_paths`
   omitted health probes.** main.py passes the full list explicitly
   in production, but any test fixture or future re-wiring without
   the explicit kwarg returned 401 on `/livez`, `/readyz`,
   `/healthz/deep`, `/metrics`. Footgun.

5. **MED — CORS `allow_credentials=True` with wildcard origins.**
   Combination silently dropped by browser (Fetch spec); the
   response then asserted both `*` and `credentials: true` which
   Chromium/Firefox refuse. Now `allow_credentials` follows the
   "is wildcard?" check.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1: memory_shim /models
# ---------------------------------------------------------------------------


def test_memory_shim_exposes_models_endpoint():
    """v0.7.209 — memory_shim must expose `GET /models` (no /v1
    prefix; the memory credential's base_url is registered
    without /v1)."""
    src = _src("desktop/desktop_shims/memory_shim.py")
    assert '@app.get("/models")' in src
    assert '"object": "list"' in src
    # No /v1 prefix here — distinct from whisper/piper.
    assert '@app.get("/v1/models")' not in src


def test_memory_shim_models_runtime():
    """v0.7.209 — runtime smoke: build the shim's FastAPI app and
    actually hit /models. Mocks the mem_client so import side-
    effects don't matter."""
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from desktop.desktop_shims.memory_shim import build_app

    app = build_app(mem_client=MagicMock())
    with TestClient(app) as client:
        resp = client.get("/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        assert len(body["data"]) >= 1
        assert body["data"][0]["id"] == "memory-local"


# ---------------------------------------------------------------------------
# Fix 2: content_process reads ContentSettings singleton
# ---------------------------------------------------------------------------


def test_content_process_reads_content_settings_singleton():
    """v0.7.209 — content_process must call
    `ContentSettings.get_instance()` instead of constructing a
    fresh ContentSettings with hardcoded literals."""
    src = _src("deeper_notebook/graphs/source.py")
    assert "await ContentSettings.get_instance()" in src
    # The defensive-fallback construction still exists (for cold
    # cache / fresh install) but it's inside an except branch.
    # Pin the v0.7.209 marker so a careless refactor that swaps
    # the singleton load back to a hardcoded literal is caught.
    assert "v0.7.209 — HIGH: previously this node constructed" in src


# ---------------------------------------------------------------------------
# Fix 3: orphan "Processing..." cleanup on permanent extract failure
# ---------------------------------------------------------------------------


def test_source_command_deletes_orphan_on_permanent_failure():
    """v0.7.209 — process_source_command's `except ValueError`
    branch must attempt to delete the placeholder source row
    when title is still 'Processing...' and full_text is empty.
    Otherwise an unsalvageable orphan stays in the DB forever."""
    src = _src("commands/source_commands.py")
    assert "v0.7.209 — Orphan-row cleanup" in src
    assert '(orphan.title or "") == "Processing..."' in src
    assert 'not (orphan.full_text or "").strip()' in src
    assert "await orphan.delete()" in src
    # Cleanup wrapped in try/except so a delete failure doesn't
    # mask the original ValueError.
    assert "except Exception as cleanup_exc:" in src


# ---------------------------------------------------------------------------
# Fix 4: auth.py default excluded_paths includes health probes
# ---------------------------------------------------------------------------


def test_auth_middleware_default_excluded_paths_includes_probes():
    """v0.7.209 — PasswordAuthMiddleware's class-default
    `excluded_paths` must include /livez, /readyz, /healthz/deep,
    and /metrics. Otherwise instantiation without the explicit
    kwarg returns 401 on every K8s/Docker probe."""
    from unittest.mock import MagicMock

    from api.auth import PasswordAuthMiddleware

    mw = PasswordAuthMiddleware(app=MagicMock())
    for required in ("/livez", "/readyz", "/healthz/deep", "/metrics"):
        assert required in mw.excluded_paths, (
            f"v0.7.209 regression: default excluded_paths missing "
            f"{required}. Probes will return 401 in any deployment "
            f"that doesn't override the kwarg."
        )


# ---------------------------------------------------------------------------
# Fix 5: CORS allow_credentials follows wildcard check
# ---------------------------------------------------------------------------


def test_cors_allow_credentials_false_when_wildcard():
    """v0.7.209 — `allow_credentials` must be False when
    `CORS_IS_DEFAULT_WILDCARD` is True. The opposite (True+wildcard)
    is silently dropped by browsers per the Fetch spec — runtime
    asserting both is an honest-contract violation."""
    src = _src("api/main.py")
    assert "allow_credentials=not CORS_IS_DEFAULT_WILDCARD" in src
    # The bug pattern (`allow_credentials=True`) must be gone from
    # the active CORSMiddleware call. Strip comment lines so the
    # historical-rationale block doesn't false-positive.
    code_only_lines: list[str] = []
    in_block = False
    for ln in src.splitlines():
        stripped = ln.lstrip()
        if stripped.startswith('"""'):
            in_block = not in_block
        if in_block or stripped.startswith("#"):
            continue
        code_only_lines.append(ln)
    code_only = "\n".join(code_only_lines)
    assert "allow_credentials=True," not in code_only
