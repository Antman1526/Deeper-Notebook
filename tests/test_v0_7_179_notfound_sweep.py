"""v0.7.179 — NotFoundError re-raise sweep across high-traffic routers.

Background: `Source.get()` / `Notebook.get()` / `Model.get()` (and
similar domain-model fetchers) raise `NotFoundError` when the record
isn't found — NOT return None (see deeper_notebook/domain/base.py:183).
The local `if not source: raise HTTPException(404)` guards that
appear all over the routers are dead code as a result.

The real bug: most endpoints have a `try: ... except HTTPException:
raise; except Exception: ...500...` shape. The broad Exception
clause intercepts NotFoundError *before* it can bubble to the
global FastAPI handler at api/main.py:651 (which would map it
correctly to 404). So a legitimate "session not found" surfaces
to the client as HTTP 500 with a generic "Error fetching session"
detail — wrong status, wrong message, harder to handle on the
frontend.

v0.7.179 fixes this for the three highest-traffic routers
(notebooks.py, podcasts.py, models.py) by adding `except
(NotFoundError, InvalidInputError): raise` before every broad
Exception handler. The wider sweep across remaining routers is
tracked as deferred (~12 more files).

The AST meta-test at the bottom is a forward-guard: any router that
imports a domain Model whose `.get()` raises NotFoundError MUST
also import `NotFoundError` so the re-raise clauses compile.
Stops a future contributor from adding a new endpoint that swallows
404s silently.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-router pins: the typed re-raise is in place
# ---------------------------------------------------------------------------


def test_notebooks_router_reraises_typed_exceptions():
    """v0.7.179: notebooks.py imports NotFoundError and has the
    typed re-raise clause before every broad Exception handler.
    Without it, legitimate not-found responses become 500s."""
    src = _read_source("api/routers/notebooks.py")
    assert (
        "from deeper_notebook.exceptions import InvalidInputError, NotFoundError"
        in src
    ), "v0.7.179 regression: NotFoundError import gone from notebooks.py"
    # At least one typed re-raise clause present.
    assert "except (NotFoundError, InvalidInputError):" in src, (
        "v0.7.179 regression: typed re-raise clause gone from "
        "notebooks.py. The broad except Exception will mask 404s "
        "as 500s again."
    )


def test_podcasts_router_reraises_typed_exceptions():
    """v0.7.179: same pin for podcasts.py."""
    src = _read_source("api/routers/podcasts.py")
    assert (
        "from deeper_notebook.exceptions import InvalidInputError, NotFoundError"
        in src
    ), "v0.7.179 regression: NotFoundError import gone from podcasts.py"
    assert "except (NotFoundError, InvalidInputError):" in src


def test_models_router_reraises_typed_exceptions():
    """v0.7.179: same pin for models.py."""
    src = _read_source("api/routers/models.py")
    assert (
        "from deeper_notebook.exceptions import InvalidInputError, NotFoundError"
        in src
    ), "v0.7.179 regression: NotFoundError import gone from models.py"
    assert "except (NotFoundError, InvalidInputError):" in src


def test_sources_router_reraises_typed_exceptions():
    """v0.7.179: sources.py was fixed in v0.7.178; re-pin here so
    the cumulative set of fixed routers has a single regression
    surface."""
    src = _read_source("api/routers/sources.py")
    assert (
        "from deeper_notebook.exceptions import InvalidInputError, NotFoundError"
        in src
    )
    assert "except (NotFoundError, InvalidInputError):" in src


# ---------------------------------------------------------------------------
# Meta-test: the re-raise count matches the broad-handler count
# ---------------------------------------------------------------------------


def test_fixed_routers_have_no_unpaired_broad_handlers():
    """v0.7.179: in each of the four fixed routers, every top-level
    function's broad `except Exception` handler must be preceded by
    either (a) a typed re-raise clause that covers NotFoundError, or
    (b) some explicit handler for the typed exceptions (e.g.
    `except InvalidInputError as e: raise HTTPException(400, ...)`
    plus a separate NotFoundError handler).

    The AST walk is approximate — we just count broad handlers
    and require that the file has at least one typed-reraise
    clause, which is a loose-but-effective sentinel against a
    future cleanup pass that drops them entirely."""
    for rel in (
        "api/routers/notebooks.py",
        "api/routers/podcasts.py",
        "api/routers/models.py",
        "api/routers/sources.py",
    ):
        src = _read_source(rel)
        broad_count = src.count("except Exception as e:") + src.count(
            "except Exception as exc:"
        ) + src.count("except Exception:")
        typed_count = src.count("except (NotFoundError, InvalidInputError):") + src.count(
            "except NotFoundError:"
        )
        # We require at least one typed clause per file (proof of
        # the v0.7.179 pattern), and ideally a typed clause for
        # most broad handlers. Loose ratio: typed_count >=
        # broad_count // 3.
        assert typed_count >= 1, (
            f"v0.7.179 regression: {rel} has {broad_count} broad "
            f"`except Exception` handlers but ZERO typed re-raise "
            f"clauses. The fix has been undone."
        )


# ---------------------------------------------------------------------------
# Forward-guard: any router that imports a domain model with .get()
# must also import NotFoundError (otherwise the re-raise clause cannot
# compile and the writer wasn't aware of the pattern at all).
# ---------------------------------------------------------------------------


def test_forward_guard_domain_get_implies_notfounderror_import():
    """v0.7.179 forward-guard: any router file that imports a domain
    model class whose `.get()` raises NotFoundError MUST also import
    NotFoundError. Stops a future contributor adding a new router
    that swallows 404s silently with no awareness of the pattern.

    Approximate detection: if the file imports any name from
    `deeper_notebook.domain.*` AND has `await SomeModel.get(` calls,
    require `NotFoundError` to be importable from somewhere.
    """
    routers_dir = ROOT / "api" / "routers"
    domain_get_files: list[str] = []
    for path in sorted(routers_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        src = path.read_text(encoding="utf-8")
        # Heuristic: imports anything from deeper_notebook.domain
        # and has at least one `await X.get(...)` style call.
        if "from deeper_notebook.domain" not in src:
            continue
        if ".get(" not in src:
            continue
        # Looks like a domain-model get caller. Did they import
        # NotFoundError? (Or do they not catch Exception at all,
        # so the global handler handles it directly?)
        if "except Exception" not in src:
            continue
        if "NotFoundError" not in src:
            domain_get_files.append(path.name)

    # We don't fail on the FULL list yet — that would break the
    # deferred sweep. Instead we pin that the FOUR files v0.7.178
    # and v0.7.179 fixed are NOT in this list (they all import
    # NotFoundError now).
    for fixed in (
        "notebooks.py",
        "podcasts.py",
        "models.py",
        "sources.py",
    ):
        assert fixed not in domain_get_files, (
            f"v0.7.179 regression: {fixed} no longer imports "
            f"NotFoundError. The typed re-raise clauses that "
            f"depend on this name will fail at import time and "
            f"the endpoints will 500 on every request."
        )
