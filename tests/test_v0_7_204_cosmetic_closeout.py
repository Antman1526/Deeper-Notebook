"""v0.7.204 — Cosmetic / low-priority closeout from the running
deferred list. Five small fixes consolidating the items the user
explicitly asked to clean up:

1. `find_free_ports` socket-release race — added SO_REUSEADDR on
   probe sockets + bounded re-probe on duplicate-port detection.
   Doesn't eliminate the race (would require socket-FD handoff to
   children) but defeats the most common manifestation.

2. `search/page.tsx` auto-trigger useEffect deps brittle — narrowed
   the effect's deps to just the URL-driven trigger inputs;
   handleSearch/handleAsk stashed in refs so they don't tangle the
   effect with half the page state.

3. `podcast_service.get_episode` masked errors as 404 — every
   exception (DB drop, decryption error, timeout) became "Episode
   not found". Restructured to raise NotFoundError only on the
   actual None return; everything else propagates as its real
   type for the global classifier.

4. `command_service` typed-exception passthrough — the outer
   `except Exception: raise` re-raised untyped exceptions that
   FastAPI's framework rendered as "Internal Server Error" with
   no detail. Now wraps untyped exceptions as DeeperNotebookError
   so the global classifier emits a structured 500.

5. `notes.py` title `[:80]` magic number — parameterized via
   DEEPER_NOTEBOOK_NOTE_TITLE_FALLBACK_LEN env (clamped to 20-500). Operators
   with CJK-heavy content can raise the cap; the default stays at
   80 for English content.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_find_free_ports_sets_so_reuseaddr_and_dedupes():
    """v0.7.204 — `find_free_ports` must set SO_REUSEADDR on probe
    sockets and verify the returned set has no duplicates before
    returning. Without SO_REUSEADDR a child binding the port after
    we close the probe socket may collide with a stray TIME_WAIT."""
    src = _src("desktop/ports.py")
    assert "SO_REUSEADDR" in src, (
        "v0.7.204 regression: find_free_ports probe sockets no "
        "longer set SO_REUSEADDR. Increases collision window."
    )
    assert "_MAX_REPROBE_ATTEMPTS" in src
    assert "if len(set(ports)) == n:" in src, (
        "v0.7.204 regression: find_free_ports no longer dedupes "
        "the returned port set. Rare OS allocator quirk can return "
        "the same port to two probe sockets."
    )


def test_find_free_ports_returns_distinct_ports():
    """v0.7.204 — runtime smoke that find_free_ports returns n
    distinct ports for a small n. Catches the case where the
    SO_REUSEADDR / dedupe logic accidentally returns the same
    port repeatedly."""
    from desktop.ports import find_free_ports

    ports = find_free_ports(5)
    assert len(ports) == 5
    assert len(set(ports)) == 5, (
        f"v0.7.204: find_free_ports returned duplicates: {ports!r}"
    )
    for p in ports:
        assert 1024 < p < 65536, f"port out of ephemeral range: {p}"


def test_search_page_uses_ref_pattern_for_auto_trigger():
    """v0.7.204 — search page's auto-trigger useEffect must stash
    handleSearch/handleAsk in refs and narrow the effect deps to
    JUST the URL-driven trigger inputs. Otherwise the effect re-
    runs every time the user types in the search box."""
    src = _src("frontend/src/app/(dashboard)/search/page.tsx")
    assert "handleSearchRef" in src and "handleAskRef" in src, (
        "v0.7.204 regression: ref-stash pattern for handleSearch/"
        "handleAsk is gone. Auto-trigger effect deps are tangled "
        "again with searchQuery / askQuestion / modelDefaults."
    )
    assert "handleSearchRef.current()" in src
    assert "handleAskRef.current()" in src


def test_podcast_get_episode_does_not_mask_all_errors_as_404():
    """v0.7.204 — `get_episode` must NOT have a bare `try/except
    Exception: raise HTTPException(404)`. That pattern collapsed
    DB drops, timeouts, decryption errors all to 404 'Episode
    not found' — operators looking at logs saw the real backend
    issue but the API client got a misleading 404."""
    src = _src("api/podcast_service.py")
    # The whole try/except wrapper for get_episode must be gone.
    # Pin the v0.7.204 marker so a refactor that re-adds the
    # try/except is caught.
    assert "v0.7.204 — was a bare `try/except Exception` that turned" in src
    # The new code raises NotFoundError on None return.
    assert 'raise NotFoundError(f"Episode {episode_id} not found")' in src


def test_command_service_wraps_untyped_exceptions():
    """v0.7.204 — `command_service.submit_command_job` outer
    handler must wrap untyped Exception subclasses as
    DeeperNotebookError so the global classifier emits a structured
    500. Typed exceptions (ValueError, asyncio.TimeoutError,
    DeeperNotebookError subclasses) pass through unchanged."""
    src = _src("api/command_service.py")
    assert (
        "if isinstance(e, (DeeperNotebookError, ValueError, asyncio.TimeoutError)):"
        in src
    )
    assert "raise DeeperNotebookError(" in src


def test_notes_title_fallback_len_is_parameterized():
    """v0.7.204 — the `first_line[:80]` magic number in notes.py
    title-fallback must be parameterized via
    DEEPER_NOTEBOOK_NOTE_TITLE_FALLBACK_LEN env, clamped to a sane range so
    a misconfigured value can't break note creation entirely."""
    src = _src("api/routers/notes.py")
    assert re.search(
        r'resolve_env\(\s*"DEEPER_NOTEBOOK_NOTE_TITLE_FALLBACK_LEN"',
        src,
    )
    # Pin the clamp range so a careless refactor that drops it
    # doesn't let an operator set it to 0 / negative.
    # v0.8.99 — the clamp BOUNDS are the invariant; whitespace is not.
    assert re.search(
        r"max\(\s*20,\s*min\(\s*int\(_max_title_len_raw\),\s*500\s*\)\s*\)",
        src,
    ), "v0.7.204 regression: note title fallback clamp [20, 500] removed."
    # And the fallback default-on-bad-int must still be the
    # original 80.
    assert "_max_title_len = 80" in src
