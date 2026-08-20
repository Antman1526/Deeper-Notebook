"""v0.7.206 — Local chat was failing with 400 context_length_exceeded.

User report: "Local models are failing in the chat."

Symptom: chat with 2-3 selected sources returned a 400 from the
llama-cpp chat server:
  "This model's maximum context length is 16384 tokens. However,
   you requested 21016 tokens..."

Root cause: the launcher hardcoded a 16384-token n_ctx default
for llama_cpp.server, set when gemma-2-9b / codellama-13b were
the common local models (8k/16k native contexts). The actual
install base now runs Hermes-3 (131k native), Qwen2.5 (32k-128k),
Llama-3.2 (131k) — all artificially capped at 16k.

Two fixes:

  1. Default n_ctx bumped 16384 → 32768. Doubles KV-cache RAM
     for an 8B model (~2 GB → ~4 GB) but gives 11k of headroom
     over the v0.7.205-era failure case.

  2. Auto-detect from GGUF metadata when DEEPER_NOTEBOOK_CHAT_LLM_CTX is
     not explicitly set. The GGUF file's `<arch>.context_length`
     field tells us the native max; cap at DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX
     (default 32768) for RAM safety. Capable users can raise
     the cap via env or override per-spawn with DEEPER_NOTEBOOK_CHAT_LLM_CTX.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_launcher_default_n_ctx_floor_is_32768():
    """v0.7.206 / v0.8.67i — the default cap for llama_cpp chat n_ctx must keep
    32768 as its FLOOR (was a flat 32768 literal; v0.8.67i made it RAM-aware via
    _default_ctx_max(), scaling UP on big-RAM Macs but never below 32768 on
    small / non-darwin / sysconf-failure hosts). Below 32768 the v0.7.205-era
    400 context_length_exceeded returns for 2-3 selected sources."""
    src = _src("desktop/launcher.py")
    assert "def _default_ctx_max(" in src, (
        "v0.8.67i regression: RAM-aware default n_ctx cap helper removed."
    )
    assert "default = 32768" in src, (
        "v0.7.206/v0.8.67i regression: 32768 is no longer the n_ctx cap floor. "
        "Users with 2-3 selected sources could see 400 context_length_exceeded."
    )


def test_launcher_supports_gguf_context_autodetect():
    """v0.7.206 — when DEEPER_NOTEBOOK_CHAT_LLM_CTX is NOT explicitly set,
    the launcher must call `_detect_gguf_context_length()` to
    read the model's native context window from GGUF metadata."""
    src = _src("desktop/launcher.py")
    assert "def _detect_gguf_context_length(" in src
    # The helper must be invoked from the chat-spawn n_ctx branch.
    assert "n_ctx_int = self._detect_gguf_context_length(" in src
    # And capped by the user-configurable max.
    assert "n_ctx_int = min(n_ctx_int, ctx_max)" in src


def test_gguf_context_detect_handles_missing_gguf_lib():
    """v0.7.206 — `_detect_gguf_context_length` must NEVER raise.
    The launcher cannot block startup on a metadata-parse failure
    (could be a corrupt GGUF, an exotic quant, or the `gguf`
    library missing from the bundled venv on some builds). Always
    return the fallback."""
    import sys
    from pathlib import Path as P

    # Stash any existing `gguf` import out so the function takes
    # the ImportError path deterministically.
    gguf_stashed = sys.modules.pop("gguf", None)
    try:
        from desktop.launcher import Supervisor

        result = Supervisor._detect_gguf_context_length(
            P("/nonexistent/path.gguf"),
            fallback=12345,
        )
        assert result == 12345, (
            f"expected fallback 12345 on missing GGUF, got {result!r}"
        )
    finally:
        if gguf_stashed is not None:
            sys.modules["gguf"] = gguf_stashed


def test_gguf_context_detect_handles_corrupt_path():
    """v0.7.206 — passing a path that exists but isn't a valid GGUF
    must also return the fallback (not raise). Covers the corrupt-
    file / wrong-format path."""
    from desktop.launcher import Supervisor

    # tmp_path-equivalent — pick a definitely-not-a-GGUF file.
    # Using this very test file as bait.
    bad_path = Path(__file__)
    result = Supervisor._detect_gguf_context_length(
        bad_path,
        fallback=99999,
    )
    assert result == 99999, f"expected fallback 99999 for non-GGUF file, got {result!r}"


def test_explicit_env_var_still_wins():
    """v0.7.206 — when DEEPER_NOTEBOOK_CHAT_LLM_CTX or an alias is explicit,
    the user's choice must win over auto-detection. (Tested via the
    desktop launcher fixture in test_launcher.py:
    test_chat_llm_n_ctx_respects_env_var — pin the source-level
    branch here too so a careless refactor that drops the explicit-
    env branch is caught by the cheap AST test.)"""
    src = _src("desktop/launcher.py")
    assert 'env_n_ctx = resolve_env("DEEPER_NOTEBOOK_CHAT_LLM_CTX")' in src
    assert "if env_n_ctx:" in src, (
        "v0.7.206 regression: explicit chat n_ctx environment setting "
        "branch removed from chat n_ctx resolution. Users would "
        "lose the ability to override the auto-detected cap."
    )
