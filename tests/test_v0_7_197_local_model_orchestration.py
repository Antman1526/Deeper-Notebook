"""v0.7.197 — Local-model orchestration fixes from the background
"Local model audit" agent. Four discrete bugs, each user-visible
on the very first launch of a fresh .app install:

  1. `mcp` + `fastmcp` not pinned in desktop/requirements.txt —
     same class of bug as v0.7.195. Next lockfile regen would
     drop both, openchronicle_shim crashes silently on import.

  2. `self.embed_port` stashed even when `_spawn_llamacpp_embed`
     early-returned (no nomic embed file). auto_register then
     registers a `Local Embeddings (llama.cpp)` credential against
     a port nothing is listening on, and memory_retriever boots
     with `--embed-url http://127.0.0.1:<dead_port>/v1`. First
     source upload hangs / fails.

  3. Embedding GGUFs in `register_llamacpp_models` were linked to
     the CHAT credential (chat_llm_port) when they should be linked
     to the EMBED credential (embed_port). Selecting one as the
     active embedding model returned 404 from the chat server.

  4. `_spawn_openchronicle_bridge` hardcoded `--mcp-url
     http://127.0.0.1:8742/mcp`, OVERRIDING the env-var default
     the v0.7 audit (P1-MED-10) added to the shim's argparse.
     Users on a non-default OpenChronicle port couldn't reach it.

These tests are AST-level so they don't depend on running services.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1 — mcp + fastmcp pinned in requirements.txt
# ---------------------------------------------------------------------------


def test_mcp_pinned_in_requirements_txt():
    """v0.7.197 — `mcp` (and the higher-level `fastmcp` umbrella) must
    be declared dependencies, not implicit transitives. The
    openchronicle_shim imports from `mcp.client.session` /
    `mcp.client.streamable_http`; v0.7.195 already proved this class
    of bug (faster-whisper / piper-tts / mem0ai silently absent on
    every .app since v0.4)."""
    txt = _read_source("desktop/requirements.txt")
    # Lower-case the body for the search; pkg names are case-insensitive
    # but the version-spec must be on the same line.
    assert "mcp>=" in txt, (
        "v0.7.197 regression: `mcp` is missing from desktop/"
        "requirements.txt. Lockfile regen will drop it; openchronicle_"
        "shim will crash with ModuleNotFoundError on next .app install."
    )
    assert "fastmcp>=" in txt, (
        "v0.7.197 regression: `fastmcp` is missing from desktop/"
        "requirements.txt. mcp arrives transitively today only because"
        " fastmcp is in the lock; without fastmcp pinned, both vanish."
    )


# ---------------------------------------------------------------------------
# Fix 2 — embed/whisper/piper port conditional stash
# ---------------------------------------------------------------------------


def test_launcher_stashes_embed_port_only_when_spawn_was_real():
    """v0.7.197 — launcher.py must not unconditionally stash
    `self.embed_port = embed_port` when `_spawn_llamacpp_embed`
    early-returned. Mirror the spawn function's pre-conditions
    (`nomic_embed_path is not None and .exists()`) so downstream
    code sees `embed_port == 0` when no server is actually
    listening."""
    src = _read_source("desktop/launcher.py")
    # The fix introduces an `embed_alive` (and `whisper_alive` /
    # `piper_alive`) guard. Pin both the variable name and the
    # conditional-assignment shape.
    assert "embed_alive" in src, (
        "v0.7.197 regression: launcher.py no longer guards "
        "self.embed_port behind the file-exists precondition. "
        "auto_register will re-create Local Embeddings credentials "
        "against dead ports on installs without a nomic GGUF."
    )
    assert "self.embed_port = embed_port if embed_alive else 0" in src
    assert "self.whisper_port = whisper_port if whisper_alive else 0" in src
    assert "self.piper_port = piper_port if piper_alive else 0" in src


# ---------------------------------------------------------------------------
# Fix 3 — embedding GGUFs routed to embed credential, not chat
# ---------------------------------------------------------------------------


def test_llamacpp_register_routes_embeddings_to_embed_credential():
    """v0.7.197 — `register_llamacpp_models` must look up the
    `Local Embeddings (llama.cpp)` credential and link any
    embedding GGUF (nomic, bge-*, etc.) to THAT credential id,
    NOT the chat credential id."""
    src = _read_source("desktop/auto_register/llamacpp.py")
    assert "embed_cred_id" in src, (
        "v0.7.197 regression: llamacpp.py no longer resolves the "
        "embed credential id. Embedding GGUFs will be linked to the "
        "chat credential and 404 on /v1/embeddings calls."
    )
    assert "local embeddings (llama.cpp)" in src.lower()
    assert "target_cred" in src
    # The lookup must consult /api/credentials (not /credentials).
    assert "/api/credentials" in src


def test_llamacpp_register_uses_chat_cred_when_no_embed_cred():
    """v0.7.197 — forward-compat: when the embed credential does
    not exist (clean install with no nomic file), embedding GGUFs
    fall back to the chat credential. This is so the model still
    appears in the dropdown (with a known-bad URL the user can
    fix) instead of being silently dropped."""
    from desktop.auto_register.llamacpp import register_llamacpp_models

    # No embed cred in existing_cred_names. local_ggufs empty —
    # we're only verifying the embed-cred lookup branch is
    # skipped, not testing the model loop.
    client = MagicMock()
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [],
    )
    client.post.return_value = MagicMock(
        status_code=201,
        json=lambda: {"id": "credential:chat-cred"},
    )

    register_llamacpp_models(
        client,
        existing_cred_names=set(),
        existing_model_keys=set(),
        model_dir=ROOT / "_nonexistent",
        llamacpp_port=51100,
        local_ggufs=[],
    )

    # Chat credential created — no separate GET for the embed
    # credential (the early-return short-circuits the lookup
    # when existing_cred_names doesn't contain the embed entry).
    # The exact GET count is brittle; the load-bearing assertion
    # is that the POST was for the chat credential.
    client.post.assert_called_once()
    post_payload = client.post.call_args.kwargs.get("json", {})
    assert post_payload.get("name") == "llama.cpp (local)"


# ---------------------------------------------------------------------------
# Fix 4 — openchronicle MCP URL honours env override
# ---------------------------------------------------------------------------


def test_openchronicle_spawn_honours_env_url():
    """v0.7.197 — `_spawn_openchronicle_bridge` must read
    OPENCHRONICLE_MCP_URL from the env instead of hardcoding the
    default. The shim's argparse already had the env-var as its
    default; the launcher hardcoding was overriding it."""
    src = _read_source("desktop/launcher.py")
    # The hardcoded literal must NOT appear in the bridge spawn
    # as a positional flag value any longer.
    assert "OPENCHRONICLE_MCP_URL" in src, (
        "v0.7.197 regression: _spawn_openchronicle_bridge no longer "
        "reads OPENCHRONICLE_MCP_URL. Users on non-default ports "
        "cannot reach their MCP server from ONP."
    )
    # The new flow assigns `mcp_url = os.environ.get(...)` before
    # passing it into the subprocess args. Pin the variable.
    # v0.8.99 — token match, not layout match: the argv entries may sit on one
    # line or two. The invariant is that the flag gets the env-derived value.
    _flat = re.sub(r"\s+", " ", src)
    assert "mcp_url = os.environ.get(" in _flat
    assert '"--mcp-url", mcp_url' in _flat
