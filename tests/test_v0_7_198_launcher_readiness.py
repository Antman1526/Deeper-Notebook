"""v0.7.198 — launcher.py now waits for the chat-llm server's port
to bind before spawning the memory retriever.

Background: `_spawn_memory_retriever` instantiates `mem0.Memory`,
whose startup validates the LLM endpoint. llama-cpp typically
takes 10–30 s to mmap a multi-GB GGUF; without a `_wait_tcp`
gate the memory child raised `ConnectionRefusedError` and exited
rc=1 silently (production DEVNULL). The user then saw "Memory
(local)" → Cannot connect to server in the credentials UI.

Fix: between the `_try_spawn` for llamacpp_chat and the
`_try_spawn` for memory, wait up to 60 s for the chat port. On
timeout we log and proceed (better degraded than frozen UI). The
proc=`self._procs[-1]` arg lets `_wait_tcp` short-circuit on a
crashed child instead of waiting the full minute.

This file pins the source contract; the runtime behaviour is
implicitly tested by the existing desktop test suite's start_all
mocks.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_wait_tcp_called_between_llamacpp_chat_and_memory():
    """v0.7.198 — the launcher must invoke `_wait_tcp` after the
    llamacpp_chat spawn but before the memory spawn, and the
    timeout must be generous enough for a cold-cache mmap (≥60 s)."""
    src = _src("desktop/launcher.py")
    # Anchor on the chat_alive flag introduced in the fix.
    assert "chat_alive = (" in src, (
        "v0.7.198 regression: chat_alive precondition flag removed. "
        "_wait_tcp will fire even when no chat GGUF is configured, "
        "wasting 60s on every launch with no chat model."
    )
    # The wait call itself must be present.
    assert "_wait_tcp(" in src
    # v0.8.67 — the chat-llm readiness probe timeout is now env-tunable
    # (DEEPER_NOTEBOOK_SIDECAR_TCP_TIMEOUT, with legacy aliases accepted) and
    # a generous default for cold mmaps; it was a hardcoded 60.0. Assert the
    # tunable AND a generous default (>=60s) so a refactor that lowers it —
    # regressing the original memory-retriever spawn race — is still caught.
    assert re.search(
        r'_startup_timeout\(\s*"DEEPER_NOTEBOOK_SIDECAR_TCP_TIMEOUT"',
        src,
    ), (
        "v0.7.198/v0.8.67 regression: chat-llm readiness probe no longer uses "
        "the env-tunable DEEPER_NOTEBOOK_SIDECAR_TCP_TIMEOUT."
    )
    _m = re.search(
        r'_startup_timeout\(\s*"DEEPER_NOTEBOOK_SIDECAR_TCP_TIMEOUT",\s*([0-9.]+)',
        src,
    )
    assert _m and float(_m.group(1)) >= 60.0, (
        "v0.7.198 regression: chat-llm readiness probe default timeout < 60s. "
        "Cold-cache mmap of large GGUFs can legitimately exceed it."
    )
    # The order assertion: chat_alive guard appears BEFORE memory spawn.
    idx_chat_alive = src.find("chat_alive = (")
    idx_memory_spawn = src.find(
        'self._try_spawn("supervisor.memory"'
    )
    assert idx_chat_alive != -1 and idx_memory_spawn != -1
    assert idx_chat_alive < idx_memory_spawn


def test_wait_tcp_failure_is_warned_not_raised():
    """v0.7.198 — readiness-probe failures must be logged and the
    launcher must keep going. Raising would freeze the whole .app on
    any disk-IO hiccup."""
    src = _src("desktop/launcher.py")
    assert "except (TimeoutError, RuntimeError) as exc:" in src
    # The except block must log a warning.
    assert "log.warning(" in src
    # Specifically the v0.7.198 message we wrote, so a refactor that
    # drops the warning silently is caught.
    assert "v0.7.198 llamacpp_chat readiness probe failed" in src


def test_chat_llm_port_stash_conditional_on_chat_alive():
    """v0.7.198 — `self.chat_llm_port = chat_llm_port if chat_alive
    else 0` (parallel to v0.7.197's embed/whisper/piper conditional
    stash). Previously stashed unconditionally — auto_register would
    have created a chat credential against a dead port if the chat
    GGUF was missing."""
    src = _src("desktop/launcher.py")
    assert "self.chat_llm_port = chat_llm_port if chat_alive else 0" in src
