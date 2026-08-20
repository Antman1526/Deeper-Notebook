"""v0.7.208 — Two fixes from the end-to-end source/local-model audit.

1. **`/api/sources` upload `embed` default flipped false → true.**
   The frontend's AddSourceDialog defaults `embed=true` (when the
   user's `default_embedding_option` is "always" or "ask", which
   is the user-facing default), but the backend Form default was
   `"false"`. API consumers using curl / scripts got the surprise
   default of "upload but DON'T embed" — the source completed with
   `embedded=false`, `embedded_chunks=0`, status="completed". Looked
   successful but was invisible to vector search. Symmetry fix.

2. **Orphan `llama.cpp (local)` credential pruning at launcher
   startup.** v0.7.194 stopped the duplicate-credential creation
   going forward, but pre-existing installs still carry an orphan
   row from before the fix (modern name with 0 models linked, the
   legacy `Local GGUF (llama.cpp)` row also present). Every
   credentials listing showed users a permanently-broken row.

   The prune helper is conservatively safe — it requires ALL THREE:
     (a) name matches `llama.cpp (local)` (the v0.6.x rename),
     (b) a legacy `Local GGUF (llama.cpp)` row ALSO exists,
     (c) the candidate has ZERO models linked.
   Together these eliminate any chance of a false-positive delete.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix 1: embed Form default
# ---------------------------------------------------------------------------


def test_sources_upload_embed_default_is_true():
    """v0.7.208 — the /api/sources upload-form `embed` field must
    default to "true". Frontend defaults to embed-on-upload (when
    user setting allows); backend should match for API parity."""
    src = _src("api/routers/sources.py")
    # The bug pattern (`embed: str = Form("false")`) must NOT be
    # in the active source. Strip Python comments first so the
    # historical-rationale block doesn't false-positive.
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert 'embed: str = Form("false")' not in code_only, (
        "v0.7.208 regression: sources upload `embed` default "
        "reverted to 'false'. API consumers will upload sources "
        "that silently skip vector search."
    )
    assert 'embed: str = Form("true")' in code_only


# ---------------------------------------------------------------------------
# Fix 2: orphan credential pruning
# ---------------------------------------------------------------------------


def test_prune_orphan_legacy_credentials_deletes_only_safe_targets():
    """v0.7.208 — `_prune_orphan_legacy_credentials` must DELETE
    the modern-name row when ALL THREE constraints hold:
      (a) name matches `llama.cpp (local)`
      (b) legacy `Local GGUF (llama.cpp)` row also exists
      (c) candidate has 0 linked models
    """
    from desktop.auto_register import _prune_orphan_legacy_credentials

    creds = [
        {"id": "credential:legacy", "name": "Local GGUF (llama.cpp)"},
        {"id": "credential:orphan", "name": "llama.cpp (local)"},
    ]
    client = MagicMock()
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [],  # No models linked to anything
    )
    client.delete.return_value = MagicMock(status_code=204, text="")

    _prune_orphan_legacy_credentials(client, creds)

    # The orphan must have been DELETEd.
    client.delete.assert_called_once_with(
        "/api/credentials/credential:orphan",
    )


def test_prune_does_nothing_when_no_legacy_row():
    """v0.7.208 — If the legacy `Local GGUF (llama.cpp)` row is
    ABSENT, the modern-name row IS the canonical one (clean
    install). Must NOT delete it."""
    from desktop.auto_register import _prune_orphan_legacy_credentials

    creds = [
        {"id": "credential:modern-only", "name": "llama.cpp (local)"},
    ]
    client = MagicMock()
    _prune_orphan_legacy_credentials(client, creds)

    client.delete.assert_not_called()


def test_prune_does_nothing_when_modern_has_linked_models():
    """v0.7.208 — A `llama.cpp (local)` row that has models linked
    is NEVER an orphan (deleting it would orphan the models).
    Must skip."""
    from desktop.auto_register import _prune_orphan_legacy_credentials

    creds = [
        {"id": "credential:legacy", "name": "Local GGUF (llama.cpp)"},
        {"id": "credential:modern-with-models", "name": "llama.cpp (local)"},
    ]
    client = MagicMock()
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        # ONE model linked to the modern row.
        json=lambda: [
            {"id": "model:x", "credential": "credential:modern-with-models"},
        ],
    )

    _prune_orphan_legacy_credentials(client, creds)

    client.delete.assert_not_called()


def test_prune_handles_models_fetch_failure():
    """v0.7.208 — If `/api/models` fetch fails for any reason
    (DB blip, network), the prune helper must NOT proceed with
    a DELETE — better to leave the orphan than risk deleting a
    row that actually has models we couldn't enumerate."""
    from desktop.auto_register import _prune_orphan_legacy_credentials

    creds = [
        {"id": "credential:legacy", "name": "Local GGUF (llama.cpp)"},
        {"id": "credential:orphan", "name": "llama.cpp (local)"},
    ]
    client = MagicMock()
    client.get.side_effect = RuntimeError("DB unreachable")

    _prune_orphan_legacy_credentials(client, creds)

    client.delete.assert_not_called()
