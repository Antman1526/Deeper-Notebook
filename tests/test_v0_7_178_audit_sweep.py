"""v0.7.178 — Round-5 deferred sweep.

Four independent fixes bundled under one version tag:

1.  commands/embedding_commands.py — per-source chunk count had no
    ceiling. A 500MB text upload chunks to ~333k entries, each
    holding (chunk_text + 768-dim float32 embedding + record dict)
    simultaneously in memory before the bulk insert. Worker OOMs.
    v0.7.178 adds MAX_CHUNKS_PER_SOURCE = 10000 (~50MB peak,
    covers any legitimate document at 1500-char chunk size).
    Raised as ValueError so surreal_commands' `stop_on: [ValueError]`
    retry config does NOT spin in a retry loop.

2.  api/routers/sources.py::create_source_insight — the bare
    `except Exception` handler swallowed NotFoundError /
    InvalidInputError from `Source.get()` / `Transformation.get()`,
    returning 500 instead of letting the global FastAPI handlers
    in api/main.py map them to 404 / 400. The local
    `if not source: raise HTTPException(404)` guards are dead code
    because Source.get raises NotFoundError instead of returning
    None (deeper_notebook/domain/base.py:183).

3.  api/routers/studio.py — two more HTTPException(detail=f"...{exc}")
    leaks (lines 547, 1342) the v0.7.168/v0.7.177 sweeps missed.
    Sanitized; logger.exception still captures the full traceback.

4.  No code change but a meta-test that the embedding chunk cap
    constant exists and remains a ValueError-class raise (so future
    refactors don't accidentally demote it to a retry-eligible
    exception, undoing the OOM protection).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    path = ROOT / rel
    if path.is_file():
        return path.read_text(encoding="utf-8")

    package = path.with_suffix("")
    if package.is_dir():
        return "\n".join(
            child.read_text(encoding="utf-8") for child in sorted(package.rglob("*.py"))
        )

    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Embedding chunk cap
# ---------------------------------------------------------------------------


def test_embedding_commands_caps_chunk_count():
    """v0.7.178: MAX_CHUNKS_PER_SOURCE must be defined and the
    embed_source command must raise ValueError above the cap.
    Without the cap, pathological inputs OOM the worker."""
    src = _read_source("commands/embedding_commands.py")
    assert "MAX_CHUNKS_PER_SOURCE = " in src, (
        "v0.7.178 regression: MAX_CHUNKS_PER_SOURCE constant is gone. "
        "Without a per-source chunk-count cap, a 500MB text upload "
        "OOMs the embedding worker. Restore the constant + raise."
    )
    # The cap should be a reasonable integer.
    tree = ast.parse(src)
    cap = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "MAX_CHUNKS_PER_SOURCE":
                if isinstance(node.value, ast.Constant):
                    cap = node.value.value
    assert cap is not None, "MAX_CHUNKS_PER_SOURCE has no integer literal value"
    assert 1000 <= cap <= 100000, (
        f"v0.7.178: MAX_CHUNKS_PER_SOURCE={cap} is outside the sensible "
        f"range [1000, 100000]. <1000 rejects legitimate large PDFs; "
        f">100000 doesn't prevent the OOM scenario this guard exists "
        f"for. Re-examine if you're sure."
    )


def test_embedding_chunk_cap_raises_value_error_not_exception():
    """v0.7.178: the cap must raise `ValueError`, not bare Exception.
    surreal_commands' retry config has `stop_on: [ValueError]`, so
    ValueError is the canonical 'permanent error, do not retry'
    signal. Raising a different exception class would spin the
    worker in a retry loop blowing up the same way each time."""
    src = _read_source("commands/embedding_commands.py")
    # Find the MAX_CHUNKS_PER_SOURCE check region and confirm the
    # raise is ValueError, not bare Exception / RuntimeError.
    idx = src.find("if total_chunks > MAX_CHUNKS_PER_SOURCE")
    assert idx != -1, "v0.7.178: chunk-cap if-statement missing"
    region = src[idx : idx + 600]
    assert "raise ValueError(" in region, (
        "v0.7.178 regression: the chunk-cap raise is no longer "
        "ValueError. surreal_commands' stop_on=[ValueError] retry "
        "config means a different exception class will spin the "
        "worker indefinitely. Restore `raise ValueError(...)`."
    )


# ---------------------------------------------------------------------------
# sources.py NotFoundError re-raise
# ---------------------------------------------------------------------------


def test_create_source_insight_reraises_typed_exceptions():
    """v0.7.178: NotFoundError / InvalidInputError must bubble to the
    global FastAPI handlers in api/main.py (→ 404 / 400). Without
    the explicit `except (NotFoundError, InvalidInputError): raise`,
    the broad `except Exception` clause intercepts them and returns
    a generic 500 — wrong status for a legitimate not-found."""
    src = _read_source("api/routers/sources.py")

    # Import must be present.
    assert (
        "from deeper_notebook.exceptions import InvalidInputError, NotFoundError" in src
    ), (
        "v0.7.178 regression: NotFoundError import in sources.py is "
        "gone. Without it, the re-raise below references an undefined "
        "name and the endpoint will crash."
    )

    # Find the create_source_insight endpoint and verify the typed
    # re-raise is in place.
    idx = src.find("async def create_source_insight")
    assert idx != -1
    region = src[idx : idx + 5000]
    assert "except (NotFoundError, InvalidInputError):" in region, (
        "v0.7.178 regression: create_source_insight no longer "
        "re-raises typed exceptions before the broad `except "
        "Exception`. NotFoundError from Source.get() will be "
        "masked as a 500 instead of the proper 404."
    )


# ---------------------------------------------------------------------------
# studio.py str(exc) leak sweep
# ---------------------------------------------------------------------------


def test_studio_does_not_leak_exception_in_500_details():
    """v0.7.178: studio.py had two more `detail=f"...{exc}"` leaks
    (notebook-create failure + single-note fallback) that the
    earlier sweeps missed. logger.exception above still captures
    the full traceback for ops."""
    src = _read_source("api/routers/studio.py")
    bad_patterns = [
        'detail=f"Could not create notebook: {exc}"',
        'detail=f"Generated content but could not save it: {exc}"',
    ]
    for pat in bad_patterns:
        assert pat not in src, (
            f"v0.7.178 regression: studio.py leaking exc str again. "
            f"Offending pattern: {pat}"
        )
    # And the sanitized strings are present.
    assert 'detail="Could not create notebook"' in src
    assert 'detail="Generated content but could not save it"' in src


# ---------------------------------------------------------------------------
# Forward-looking: drain-thread join is preserved
# ---------------------------------------------------------------------------


def test_launcher_joins_drain_threads_before_closing_log_files():
    """v0.7.178 forward-guard: the v0.7.58 race fix (join drain
    threads BEFORE closing log files in stop_all) must remain.
    If the join is dropped or moved after the close, daemon
    drain threads can be mid-`log_file.write` when the handle
    closes, causing 'I/O operation on closed file' tracebacks
    on every shutdown. This is the kind of regression a
    well-meaning cleanup pass would easily introduce."""
    src = _read_source("desktop/launcher.py")

    idx_join = src.find("self._drain_threads")
    idx_close = src.find("f.close()")
    # The drain-thread join loop must come BEFORE the log-file
    # close loop in stop_all.
    # We can't just compare positions globally — the field is
    # declared near the top. Find the second occurrence (inside
    # stop_all) by searching from after the first.
    assert idx_join != -1 and idx_close != -1
    # Find a join() call near the drain_threads reference.
    join_idx = src.find("t.join(timeout=")
    assert join_idx != -1, (
        "v0.7.178 forward-guard: drain-thread t.join() is gone. "
        "Without it, daemon drains race against log-file close "
        "in stop_all and you'll see 'I/O on closed file' "
        "tracebacks on every desktop shutdown."
    )
    assert join_idx < idx_close, (
        "v0.7.178 forward-guard: drain-thread join is no longer "
        "BEFORE log-file close in stop_all. Order matters — "
        "join must run first so the threads exit before the "
        "files they're writing to are closed."
    )
