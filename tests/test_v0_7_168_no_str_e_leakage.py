"""v0.7.168 — AST/text-level guard against HTTPException detail leakage.

The audit found 66 sites raising `HTTPException(status_code=500,
detail=f"...: {str(e)}")` across 11 routers. `str(e)` for an
arbitrary exception leaks:
  - SurrealDB driver internals + class names
  - File paths from loguru-formatted exception strings
  - Database connection details on connection errors
  - Occasionally API keys (when an error message echoes them)

v0.7.168 stripped `: {str(e)}` from every `detail=` argument. The
preceding `logger.error(f"...: {str(e)}")` line still captures the
full exception text for operators tailing the api.log; only the
user-facing response detail is sanitized.

This test guards the contract: future PRs adding new endpoints
can't re-introduce the pattern. Fails at collection time if any
router file in `api/routers/` contains `detail=f"...: {str(e)}"`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROUTERS = (ROOT / "api" / "routers").glob("*.py")


# Match `detail=f"<anything>: {str(e)}"` — the exact leakage pattern
# v0.7.168 swept. Includes multi-line variants where the f-string
# spans the same line.
_LEAKAGE_PATTERN = re.compile(r'detail=f"[^"]*?: \{str\(e\)\}"')


@pytest.mark.parametrize(
    "router_path",
    sorted(p for p in ROUTERS if p.is_file()),
    ids=lambda p: p.name,
)
def test_router_does_not_leak_str_e_to_http_detail(router_path: Path):
    """v0.7.168: no `detail=f"...: {str(e)}"` in any router.

    The full traceback still belongs in the api.log via
    `logger.error()` / `logger.exception()`, but it MUST NOT echo to
    the HTTP response — the frontend's user-facing toast resolves
    the generic prefix via i18n; the raw exception text would leak
    internals and be untranslatable.

    If you're adding a new endpoint and need to surface a richer
    error message, raise a typed `DeeperNotebookError` subclass
    (NotFoundError, InvalidInputError, etc.) — those have explicit,
    safe message contracts and are mapped to the right HTTP status
    by the global exception handlers in api/main.py:567-616.
    """
    src = router_path.read_text(encoding="utf-8")
    matches = _LEAKAGE_PATTERN.findall(src)
    assert not matches, (
        f"v0.7.168 regression in {router_path.name}: "
        f"{len(matches)} HTTPException(detail=f'...: {{str(e)}}') "
        f"pattern(s) re-introduced. Strip the `: {{str(e)}}` from the "
        f"detail; the preceding logger.error/exception captures the "
        f"full text. Offenders:\n  " + "\n  ".join(matches)
    )


def test_v0_7_168_sweep_left_zero_leakages():
    """Aggregate check: across all routers combined, ZERO sites use
    the leakage pattern. Catches even routers we add in the future
    without the parametrized per-file check above."""
    total = 0
    for router_path in (ROOT / "api" / "routers").glob("*.py"):
        src = router_path.read_text(encoding="utf-8")
        total += len(_LEAKAGE_PATTERN.findall(src))
    assert total == 0, (
        f"v0.7.168 regression: {total} HTTPException detail-leakage "
        f"sites found across api/routers/. The mechanical sweep in "
        f"v0.7.168 brought this to 0 — a new occurrence means a PR "
        f"reintroduced the anti-pattern."
    )
