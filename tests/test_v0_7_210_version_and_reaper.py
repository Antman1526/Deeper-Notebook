"""v0.7.210 — Version-display rollout + periodic stale-command reaper.

User asked: "Make the startup window for each new rebuild or
iteration of the application." A deep audit by background agent
surfaced the root cause — `desktop/__init__.py:__version__` had
been "0.1.0" since project start while CHANGELOG was at v0.7.x.
Nothing in the UI told the user which build they were running.

Fixes:

  1. `desktop/__init__.py:__version__` synced to v0.7.210.
  2. `api/main.py` exposes `GET /api/version` (auth-excluded).
  3. `desktop/window.py` injects its compatibility version global so the
     frontend can render it.
  4. `frontend/src/components/layout/AppSidebar.tsx` adds a
     tiny version badge in the sidebar footer.
  5. `api/main.py` adds a 5-minute periodic stale-command reaper
     so worker crashes mid-day don't leave "running" rows that
     the frontend polls forever (previously the reaper only ran
     at API startup).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_api_version_endpoint_defined():
    """v0.7.210 — `api/main.py` must declare `GET /api/version`
    returning the bundled ONP version + name."""
    src = _src("api/main.py")
    assert '@app.get("/api/version")' in src
    assert "from desktop import __version__ as desktop_version" in src
    assert '"name": PRODUCT_NAME' in src
    assert '"description": DESCRIPTION' in src


def test_api_version_excluded_from_auth():
    """v0.7.210 — /api/version must be in PasswordAuthMiddleware
    excluded_paths so the launch splash / login page can hit it
    before the user enters credentials."""
    src = _src("api/main.py")
    assert '"/api/version",' in src
    # Right next to the v0.7.124 metrics-auth-exclusion entry.
    assert "v0.7.210 — launch splash polls before auth" in src


def test_version_matches_latest_changelog_release():
    """v0.8.70 — drift guard.

    The v0.7.210 doc comment in ``desktop/__init__.py`` promised that
    ``__version__`` is kept "in step with the latest ``## vN`` header in
    desktop/CHANGELOG.md so future bumps can't drift" — but no test actually
    enforced it, which is exactly how the string sat stale before. This pins
    it: ``__version__`` must equal the newest *released* ``## vX.Y.Z`` header.

    Note the model: in-progress work accumulates under the ``## Unreleased``
    section as ``**... vN ...**`` bullets; ``__version__`` only advances when a
    real release header is cut. So this asserts against ``## v`` headers, NOT
    the Unreleased bullets.
    """
    import re

    init_src = _src("desktop/__init__.py")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init_src)
    assert m, "could not find __version__ in desktop/__init__.py"
    version = m.group(1)

    changelog = _src("desktop/CHANGELOG.md")
    # First markdown header of the form `## vX.Y.Z[suffix] — ...`.
    header = re.search(r"(?m)^##\s+v(\d+\.\d+\.\d+[a-z]*)\b", changelog)
    assert header, "no released `## vX.Y.Z` header found in desktop/CHANGELOG.md"
    latest_release = header.group(1)

    assert version == latest_release, (
        f"desktop/__init__.py __version__={version!r} but the latest released "
        f"CHANGELOG header is v{latest_release}. Bump __version__ when you cut "
        f"a new `## v` release (or fix the header)."
    )


def test_pyinstaller_spec_uses_real_version():
    """v0.8.70 — the macOS bundle version must derive from __version__, not the
    old hardcoded "0.1.0" that made every built .app report 0.1.0 in Finder."""
    src = _src("desktop/build/pyinstaller.spec")
    assert '"CFBundleShortVersionString": "0.1.0"' not in src
    assert "APP_VERSION = _read_app_version()" in src
    assert '"CFBundleShortVersionString": APP_VERSION' in src
    assert '"CFBundleVersion": APP_VERSION' in src


def test_window_injects_onp_version_global():
    """v0.7.210 — desktop/window.py must inject window.ONP_VERSION
    alongside the existing theme / memory / voice globals so the
    frontend's AppSidebar footer can render the version badge."""
    src = _src("desktop/window.py")
    assert "from desktop import __version__ as _onp_version" in src
    assert "window.ONP_VERSION = " in src


def test_sidebar_renders_version_badge():
    """v0.7.210 — AppSidebar renders the normalized desktop version bridge."""
    src = _src("frontend/src/components/layout/AppSidebar.tsx")
    bridge = _src("frontend/src/lib/desktop-version.ts")
    assert "readDesktopVersion(window)" in src
    assert "return bridge.DEEPER_NOTEBOOK_VERSION || bridge.ONP_VERSION" in bridge
    assert "v0.7.210 — Version badge" in src
    # The badge is hidden when collapsed (matches the existing
    # sidebar pattern for footer chrome).
    assert "{!isCollapsed && (" in src


def test_periodic_reaper_loop_defined():
    """v0.7.210 — `api/main.py` must define a `_reaper_loop` async
    function (5-min sleep + same query as the startup pass) and
    anchor the task via `_track_task` so the GC can't reap it."""
    src = _src("api/main.py")
    from task_lifecycle_assertions import assert_lifespan_tracked_task

    assert "async def _reaper_loop()" in src
    # The 5-minute interval is load-bearing (any shorter would
    # spam the DB; any longer and the orphan-row UX regresses).
    assert "await asyncio.sleep(300)" in src
    # The loop must use the SAME (30m) staleness filter as the
    # startup reaper — divergence would cause weird timing
    # discrepancies between the two paths.
    assert "AND updated < (time::now() - 30m)" in src
    assert_lifespan_tracked_task(
        src,
        task_name="reaper_task",
        coroutine_name="_reaper_loop",
    )


def test_periodic_reaper_cancelled_on_shutdown():
    """v0.7.210 — the reaper task must be cancelled during the
    lifespan shutdown teardown. Otherwise it survives past the
    FastAPI shutdown and the process refuses to exit until the
    next 5-min wakeup."""
    src = _src("api/main.py")
    assert "v0.7.210 — Stop the periodic stale-command reaper" in src
    assert "if reaper_task is not None and not reaper_task.done():" in src
    assert "reaper_task.cancel()" in src


def test_periodic_reaper_swallows_iteration_failures():
    """v0.7.210 — a single failed DB query MUST NOT kill the loop.
    The loop must log + sleep + try again next tick. Otherwise
    one transient pool blip silently disables stale-row reaping
    for the rest of the API's lifetime."""
    src = _src("api/main.py")
    assert "except asyncio.CancelledError:" in src
    assert "except Exception as exc:" in src
    assert "Periodic reaper iteration failed" in src
