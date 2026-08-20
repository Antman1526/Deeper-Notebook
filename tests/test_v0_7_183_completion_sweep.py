"""v0.7.183 — Final completion sweep tests.

Locks in five separate improvements:

1.  source_chat.py redundant-handler cleanup — 5 endpoints with an
    explicit `except NotFoundError: raise HTTPException(404,
    "Source not found")` had a downstream `except (NotFoundError,
    InvalidInputError): raise` clause added by the v0.7.182 bulk
    sweep that was unreachable for NotFoundError. Narrowed to
    `except InvalidInputError:` only at those 5 sites; preserved
    the tuple form at 2 sites (stream_source_chat_response,
    send_message_to_source_chat) that lack an upstream NotFoundError
    handler.

2.  NotFoundError reraise final sweep — context.py (1 endpoint),
    plus the bulk script's run on chat.py, search.py, embedding.py
    (covered in v0.7.182 prep). Audited-no-fix: gmail.py (singleton
    .get()), exports.py (no outer wrapper on export_note), commands.py
    / config.py / embedding_rebuild.py (no Model.get calls).

3.  iso() helper final coverage — transformations.py (8 sites),
    podcast_service.py (2), credentials_service.py (2),
    command_service.py (2). The forward-guard test now scans the
    entire api/ tree for any remaining `str(X.created)` /
    `str(X.updated)`.

4.  Cross-suite test pollution FIXED. v0.7.183 renamed
    `desktop/scripts/` → `desktop/dl_scripts/` to eliminate the
    namespace collision with the top-level `scripts/` package,
    AND removed the empty `desktop/tests/__init__.py` to fix a
    similar collision with the top-level `tests/` directory.
    The combined `pytest tests/ desktop/tests/` run is now green
    end-to-end (was: 17 failures).

5.  Frontend visual polish — markdown h1/h2 in SourceDetailContent
    promoted from `font-bold` to `font-semibold` (matches v0.7.180
    H1 standard), and the Advanced dashboard page outer padding
    upgraded from bare `p-6` to the `px-6 py-10 sm:px-8` standard
    (matches Settings/Podcasts/Search/Models).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# source_chat.py redundant handler cleanup
# ---------------------------------------------------------------------------


def test_source_chat_narrowed_handlers_where_notfounderror_already_caught():
    """v0.7.183: at the 5 source_chat endpoints that already have an
    explicit `except NotFoundError: raise HTTPException(404, ...)`,
    the downstream typed-reraise clause was narrowed from
    `except (NotFoundError, InvalidInputError):` to
    `except InvalidInputError:` only — because NotFoundError was
    already caught above and the tuple form's NotFoundError leg
    was unreachable.

    But the 2 endpoints that DON'T have the upstream NotFoundError
    handler (stream_source_chat_response, send_message_to_source_chat)
    must KEEP the tuple form."""
    src = _read_source("api/routers/source_chat.py")
    # The narrow form must be present at least 5 times.
    narrow_count = src.count("except InvalidInputError:")
    assert narrow_count >= 5, (
        f"v0.7.183 regression: source_chat.py has only {narrow_count} "
        f"`except InvalidInputError:` clauses, expected ≥5 (the "
        f"five v0.7.183-narrowed endpoints)."
    )
    # The tuple form must still be present at least twice (the two
    # streaming endpoints that lack upstream NotFoundError handlers).
    tuple_count = src.count("except (NotFoundError, InvalidInputError):")
    assert tuple_count >= 2, (
        f"v0.7.183 regression: source_chat.py has only {tuple_count} "
        f"tuple-form clauses, expected ≥2. Without them, NotFoundError "
        f"from the streaming endpoints (which lack an upstream "
        f"explicit handler) will be masked as 500s."
    )


# ---------------------------------------------------------------------------
# iso() helper complete coverage — every str(X.created/updated) gone
# ---------------------------------------------------------------------------


def test_no_unsafe_str_dt_calls_anywhere_in_api():
    """v0.7.183 cumulative forward-guard: NO `str(X.created)` /
    `str(X.updated)` should exist in any api/ source file. This
    is the canonical pin for the Safari new Date() fix (v0.7.181
    introduced the iso() helper; v0.7.182/183 swept all sites)."""
    api_dir = ROOT / "api"
    offenders: list[tuple[str, int, str]] = []
    for path in api_dir.rglob("*.py"):
        if "iso.py" in str(path):
            continue  # docstring talks about str() — false positive
        if "__pycache__" in str(path):
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "str(" in stripped and (
                ".created)" in stripped or ".updated)" in stripped
            ):
                rel = path.relative_to(ROOT).as_posix()
                offenders.append((rel, i, stripped))
    assert not offenders, (
        "v0.7.183 regression: api/ tree contains `str(X.created)` / "
        "`str(X.updated)` calls. Safari new Date() will fail. "
        "Use `iso()` from api.utils.iso instead.\n"
        + "\n".join(f"  {r}:{ln} → {t}" for r, ln, t in offenders)
    )


# ---------------------------------------------------------------------------
# context.py NotFoundError reraise pin
# ---------------------------------------------------------------------------


def test_context_router_has_typed_reraise():
    """v0.7.183: context.py was the lone surviving function-level
    handler that swallowed NotFoundError. Fixed in v0.7.183."""
    src = _read_source("api/routers/context.py")
    assert "except NotFoundError:" in src, (
        "v0.7.183 regression: context.py no longer re-raises "
        "NotFoundError. The notebook-context endpoint will mask "
        "404s as 500s when the notebook_id doesn't exist."
    )


# ---------------------------------------------------------------------------
# Cross-suite pollution fix — namespace collisions resolved
# ---------------------------------------------------------------------------


def test_desktop_scripts_renamed_to_dl_scripts():
    """v0.7.183: desktop/scripts/ → desktop/dl_scripts/ to remove
    the namespace collision with the top-level scripts/ package
    that was breaking 17 tests in the combined-suite run.

    A future contributor who tries to rename it back would
    re-introduce the pollution bug; this test pins the resolution."""
    assert (ROOT / "desktop" / "dl_scripts").is_dir(), (
        "v0.7.183 regression: desktop/dl_scripts/ no longer exists. "
        "If it was renamed back to desktop/scripts/, the combined "
        "`pytest tests/ desktop/tests/` run will fail with 17 "
        "ModuleNotFoundError failures in test_v0_7_139.py."
    )
    assert not (ROOT / "desktop" / "scripts").exists(), (
        "v0.7.183 regression: desktop/scripts/ resurfaced. This "
        "shadows the root scripts/ package whenever desktop is on "
        "sys.path (shim tests do `sys.path.insert(0, parents[1])`). "
        "Rename it again — desktop/dl_scripts/ is the v0.7.183 fix."
    )


def test_desktop_tests_is_not_a_python_package():
    """v0.7.183: removed the empty desktop/tests/__init__.py to fix
    the OTHER half of the cross-suite pollution. `desktop/tests/`
    being a package shadowed the root `tests/` directory the same
    way desktop/scripts/ shadowed scripts/. Together these two
    renames eliminated all 17 cross-suite pollution failures."""
    assert not (ROOT / "desktop" / "tests" / "__init__.py").exists(), (
        "v0.7.183 regression: desktop/tests/__init__.py is back. "
        "Pytest will treat desktop/tests/ as a Python package called "
        "`tests`, shadowing the root tests/ directory. "
        "`from tests.integration.conftest import ...` in "
        "test_v0_7_131.py will ModuleNotFoundError. Delete the "
        "__init__.py again."
    )


# ---------------------------------------------------------------------------
# Frontend visual polish pins
# ---------------------------------------------------------------------------


def test_source_detail_markdown_headers_use_font_semibold():
    """v0.7.183: SourceDetailContent's markdown h1/h2 renderers
    use font-semibold (matching v0.7.180 H1 standard) instead of
    the legacy font-bold. Without this pin, a future contributor
    pulling in fresh shadcn typography utilities could revert it."""
    src = _read_source("frontend/src/components/source/SourceDetailContent.tsx")
    assert "text-2xl font-bold mt-6 mb-4" not in src, (
        "v0.7.183 regression: markdown h1 reverted to font-bold."
    )
    assert "text-xl font-bold mt-5 mb-3" not in src, (
        "v0.7.183 regression: markdown h2 reverted to font-bold."
    )
    assert "text-2xl font-semibold mt-6 mb-4" in src
    assert "text-xl font-semibold mt-5 mb-3" in src


def test_advanced_page_uses_standard_dashboard_padding():
    """v0.7.183: Advanced page upgraded from bare `p-6` to the
    v0.7.180 dashboard-page padding standard `px-6 py-10 sm:px-8`.
    The page now matches Settings/Podcasts/Search/Models breathing
    room."""
    src = _read_source("frontend/src/app/(dashboard)/advanced/page.tsx")
    assert "px-6 py-10 sm:px-8" in src, (
        "v0.7.183 regression: Advanced page no longer uses the "
        "standard dashboard padding. Content will hug the rail "
        "and the page will feel cramped compared to siblings."
    )
