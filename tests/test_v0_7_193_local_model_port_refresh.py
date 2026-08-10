"""v0.7.193 — Local-model credentials now refresh their base_url when
the desktop launcher assigns a different port across launches.

Two bugs, one symptom:

  1. **`_phase_auto_register` ignored the supervisor's dynamic
     `chat_llm_port`.** The launcher spawns its own llama-cpp-python
     chat server on a port allocated by `find_free_ports()` each
     launch (e.g. 56918 today, 57204 tomorrow). But
     `desktop/app.py::_phase_auto_register` resolved `llamacpp_port`
     ONLY by parsing the user's `OPENAI_COMPATIBLE_BASE_URL` env var
     — never by reading `sv.chat_llm_port`. So auto_register would
     log "skipping local-GGUF credential registration: no llama-cpp
     server port supplied" and the chat model never got wired up.

     Fix: priority chain in app.py — `sv.chat_llm_port` first
     (always present in desktop mode), then env override (for users
     pointing at an external llama.cpp / LM Studio instance).

  2. **`_ensure_credential` never updated the saved `base_url` for
     an existing credential.** Even if the launcher passed the right
     port, the helper would just return the existing ID — leaving
     the credential's stored URL pointing at LAST launch's port. The
     /credentials/{id}/test call then hit a closed socket and the
     model dropdown showed it as "broken".

     Fix: on the "already exists" branch, compare the saved
     `base_url` against the one the caller passed; PUT the new one
     when they differ. Saves an unnecessary round-trip on the
     common case where the port happened to repeat across launches.

  This affects all 5 dynamically-ported local servers:
  llama.cpp (local), Memory retriever, Whisper STT, Piper TTS, and
  llama.cpp embedding. The fix lives in the shared `_ensure_credential`
  helper so every auto_register sub-module benefits without a sweep.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Bug 1: app.py reads sv.chat_llm_port
# ---------------------------------------------------------------------------


def test_phase_auto_register_reads_chat_llm_port_from_supervisor():
    """v0.7.193: _phase_auto_register must default `llamacpp_port` to
    `sv.chat_llm_port` (the launcher-allocated dynamic port). Without
    this, the credential never gets wired up for the chat model the
    user is going to select."""
    src = _read_source("desktop/app.py")
    # The supervisor attribute is read.
    assert 'getattr(sv, "chat_llm_port"' in src, (
        "v0.7.193 regression: app.py no longer reads "
        "sv.chat_llm_port. The launcher-allocated chat-LLM port "
        "will be ignored by auto_register and the local chat model "
        "will silently not get wired up."
    )


# ---------------------------------------------------------------------------
# Bug 2: _ensure_credential refreshes base_url
# ---------------------------------------------------------------------------


def test_ensure_credential_refreshes_base_url_on_port_change():
    """v0.7.193: when a credential by the given name already exists
    AND the caller passes a base_url that differs from the saved
    one, _ensure_credential must PUT the new URL. Pre-fix, the
    saved URL became stale on every port reshuffle."""
    from desktop.auto_register._http import _ensure_credential

    # Fake httpx client. GET returns a credential with an OLD url;
    # we then expect a PUT with the NEW url.
    client = MagicMock()
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [
            {
                "id": "credential:abc",
                "name": "llama.cpp (local)",
                "base_url": "http://127.0.0.1:50000/v1",
            }
        ],
    )
    client.put.return_value = MagicMock(status_code=200, text="ok")

    result = _ensure_credential(
        client=client,
        existing_names={"llama.cpp (local)"},  # advertise as existing
        name="llama.cpp (local)",
        provider="openai_compatible",
        modalities=["language"],
        base_url="http://127.0.0.1:60000/v1",  # NEW port
    )

    assert result == "credential:abc"
    # The PUT must have fired with the new URL.
    client.put.assert_called_once()
    put_call = client.put.call_args
    assert put_call.args[0] == "/api/credentials/credential:abc"
    assert put_call.kwargs["json"] == {"base_url": "http://127.0.0.1:60000/v1"}
    # And NO POST should have been issued.
    client.post.assert_not_called()


def test_ensure_credential_skips_put_when_url_unchanged():
    """v0.7.193: if the saved base_url equals the one the caller
    passes, the helper must NOT issue an unnecessary PUT — saves a
    round-trip on the common case where the port happened to
    repeat across launches."""
    from desktop.auto_register._http import _ensure_credential

    client = MagicMock()
    same_url = "http://127.0.0.1:55555/v1"
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [
            {
                "id": "credential:xyz",
                "name": "llama.cpp (local)",
                "base_url": same_url,
            }
        ],
    )

    result = _ensure_credential(
        client=client,
        existing_names={"llama.cpp (local)"},
        name="llama.cpp (local)",
        provider="openai_compatible",
        modalities=["language"],
        base_url=same_url,
    )

    assert result == "credential:xyz"
    client.put.assert_not_called()
    client.post.assert_not_called()


def test_ensure_credential_skips_put_when_caller_passes_no_url():
    """v0.7.193: if the caller doesn't pass a base_url at all (some
    credential providers don't have one), we never PUT. The existing
    behavior of returning the cached ID without modifying anything
    is preserved."""
    from desktop.auto_register._http import _ensure_credential

    client = MagicMock()
    client.get.return_value = MagicMock(
        raise_for_status=lambda: None,
        json=lambda: [
            {"id": "credential:noop", "name": "openai", "base_url": None}
        ],
    )

    result = _ensure_credential(
        client=client,
        existing_names={"openai"},
        name="openai",
        provider="openai",
        modalities=["language"],
        # No base_url — like an API-key credential.
    )

    assert result == "credential:noop"
    client.put.assert_not_called()
