"""v0.7.169 — Pagination completion: `get_chat_sessions` + podcast SELECTs.

Two remaining unbounded queries from prior audits:

(1) `Notebook.get_chat_sessions()` — the inner SELECT that fetches
    every chat session attached to a notebook. v0.7.161 made the
    per-session LangGraph checkpoint reads concurrent (read-side
    fan-out), but the underlying session list itself was still
    unbounded. A power user with hundreds of chat sessions per
    notebook paid for the full table scan before the parallel
    checkpoint reads even started. Now accepts optional `limit` /
    `offset`; the /chat/sessions router caps at 100 (max 1000).

(2) `commands/podcast_commands.py` loaded EVERY episode_profile +
    speaker_profile row to feed podcast-creator's validation. Small
    tables (<20 entries typically) so not a current crisis, but the
    same shape bug as /notes had pre-v0.7.159 — a script-generated
    or migration-artifact population could blow up the memory
    footprint of every podcast-generate job. Now LIMIT 1000 on each;
    a warning log fires if we ever hit the cap so operators see the
    canary.

These tests pin both contracts at the AST/text level + the actual
router-level pagination behavior.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (1) Notebook.get_chat_sessions pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_chat_sessions_accepts_limit_and_offset():
    """v0.7.169: `get_chat_sessions(limit=N, offset=M)` must thread
    both into the SurrealQL query. Mock repo_query and read back the
    `LIMIT … START …` tail."""
    from deeper_notebook.domain.notebook import Notebook

    captured: dict = {"query": None}

    async def fake_repo_query(query, params=None):
        captured["query"] = query
        return []

    nb = Notebook(name="test-nb", description="t")
    nb.id = "notebook:abc"

    with patch("deeper_notebook.domain.notebook.repo_query", new=fake_repo_query):
        await nb.get_chat_sessions(limit=50, offset=25)

    q = captured["query"] or ""
    assert "LIMIT 50" in q
    assert "START 25" in q
    # SurrealQL requires LIMIT before START.
    assert q.index("LIMIT") < q.index("START"), (
        f"LIMIT must precede START in SurrealQL, got:\n{q}"
    )


@pytest.mark.asyncio
async def test_get_chat_sessions_without_args_is_unbounded():
    """v0.7.169: back-compat. Callers that don't pass limit/offset
    keep the pre-v0.7.169 unbounded behavior."""
    from deeper_notebook.domain.notebook import Notebook

    captured: dict = {"query": None}

    async def fake_repo_query(query, params=None):
        captured["query"] = query
        return []

    nb = Notebook(name="test-nb", description="t")
    nb.id = "notebook:abc"

    with patch("deeper_notebook.domain.notebook.repo_query", new=fake_repo_query):
        await nb.get_chat_sessions()

    q = captured["query"] or ""
    assert "LIMIT" not in q
    assert "START" not in q


@pytest.mark.asyncio
async def test_get_chat_sessions_rejects_invalid_limit():
    """v0.7.169: same defensive validation as ObjectModel.get_all in
    v0.7.159 — limit must be a positive int, offset non-negative.
    InvalidInputError propagates to the global handler (HTTP 400)
    instead of getting clobbered to 500."""
    from deeper_notebook.domain.notebook import Notebook
    from deeper_notebook.exceptions import InvalidInputError

    nb = Notebook(name="test-nb", description="t")
    nb.id = "notebook:abc"

    with pytest.raises(InvalidInputError):
        await nb.get_chat_sessions(limit=-1)
    with pytest.raises(InvalidInputError):
        await nb.get_chat_sessions(limit=0)
    with pytest.raises(InvalidInputError):
        await nb.get_chat_sessions(offset=-5)
    with pytest.raises(InvalidInputError):
        # bool is a subclass of int in Python; reject it explicitly
        # so `limit=True` doesn't silently become `LIMIT 1`.
        await nb.get_chat_sessions(limit=True)  # type: ignore[arg-type]


def test_chat_sessions_router_threads_pagination():
    """v0.7.169: the /api/chat/sessions route must accept `limit` /
    `offset` query args and pass them to `notebook.get_chat_sessions`.
    AST-level pin — the Query(...) defaults and the call site must
    both be present.
    """
    # v0.8.99 — whitespace-tolerant. These pinned exact newlines and
    # indentation, so any reflow broke a guard that is about tokens, not
    # layout. The invariant is unchanged.
    src = re.sub(r"\s+", " ", _read_source("api/routers/chat.py"))
    # The Query() declarations.
    assert "limit: int = Query( 100, ge=1, le=1000," in src, (
        "v0.7.169 regression: /chat/sessions no longer declares "
        "`limit: int = Query(100, ge=1, le=1000)` for pagination."
    )
    assert "offset: int = Query( 0, ge=0," in src
    # The call site must thread both through.
    assert "notebook.get_chat_sessions( limit=limit, offset=offset," in src


# ---------------------------------------------------------------------------
# (2) podcast_commands LIMIT 1000 on the two unbounded SELECTs
# ---------------------------------------------------------------------------


def test_podcast_commands_episode_profile_select_is_bounded():
    """v0.7.169: `SELECT * FROM episode_profile` must include
    `LIMIT 1000`. Catches a future refactor that drops the cap."""
    src = _read_source("commands/podcast_commands.py")
    assert "SELECT * FROM episode_profile LIMIT 1000" in src, (
        "v0.7.169 regression: episode_profile SELECT lost its LIMIT 1000 "
        "defensive cap. Restore so the podcast-generate path can't blow "
        "up its memory footprint on a profile table that grew unexpectedly."
    )


def test_podcast_commands_speaker_profile_select_is_bounded():
    """v0.7.169: same for `SELECT * FROM speaker_profile`."""
    src = _read_source("commands/podcast_commands.py")
    assert "SELECT * FROM speaker_profile LIMIT 1000" in src


def test_podcast_commands_warns_when_limit_hit():
    """v0.7.169: the LIMIT-bite warning log lets operators see if the
    cap is ever reached (canary for "actually needs raising"). Must
    log at WARNING (not info/debug) so it surfaces in api.log filters."""
    src = _read_source("commands/podcast_commands.py")
    assert "Hit LIMIT 1000 on podcast profile load" in src
    # Must be a warning-level log — buried at debug would defeat the canary.
    assert "logger.warning" in src
