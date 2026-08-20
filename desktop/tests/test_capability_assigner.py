"""Table-driven tests for the v0.5 capability scorer + assigner.

Add a row to EXPECTED_PICKS to lock in a new model→slot expectation.
"""

from __future__ import annotations

import pytest

from desktop.auto_register.assigner import SLOTS, assign_all, pick_for_slot
from desktop.auto_register.capability import ModelDescriptor, score_model

# ---------------------------------------------------------- capability.py
# Each row: (model_name, expected_kind, expected_source, expected_min_score_axis)
# expected_min_score_axis is a (axis, min_value) tuple — None to skip score check.


@pytest.mark.parametrize(
    "name,expected_kind,expected_source,axis_check",
    [
        # ----- Exact-prefix registry hits -----
        ("Hermes-3-Llama-3.1-8B-Q4_K_M.gguf", "chat", "registry", ("tools", 0.90)),
        (
            "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M",
            "reasoning",
            "registry",
            ("reasoning", 0.90),
        ),
        ("Qwen2.5-Coder-7B-Instruct", "chat", "registry", ("code", 0.90)),
        ("nomic-embed-text-v1.5", "embed", "registry", None),
        ("whisper-base-en", "stt", "registry", None),
        ("piper-amy-en", "tts", "registry", None),
        # ----- Fallback patterns (HF-style) -----
        ("MyNew-Coder-9B-Instruct", "chat", "fallback", ("code", 0.80)),
        ("Some-R1-Reasoning-Distill", "reasoning", "fallback", ("reasoning", 0.80)),
        ("ImaginaryEmbed-2", "embed", "fallback", None),
        ("whisper-medium-multilingual", "stt", "fallback", None),
        # ----- Fallback patterns (Ollama `<family>:<tag>` style) -----
        # P1-CRIT-01 fix: was returning kind=chat source=default with neutral
        # 0.5 scores, leaving Tools / Large Context / Reasoning slots empty
        # for Ollama-only users. Now scores via family-name regex.
        ("llama3.1:latest", "chat", "fallback", ("tools", 0.55)),
        ("qwen2.5:14b", "chat", "fallback", ("speed", 0.70)),
        ("mistral:7b-instruct", "chat", "fallback", ("tools", 0.55)),
        ("phi3.5:latest", "chat", "fallback", ("chat", 0.70)),
        ("gemma2:9b", "chat", "fallback", ("chat", 0.70)),
        ("deepseek-r1:14b", "reasoning", "fallback", ("reasoning", 0.80)),
        ("qwen2.5-coder:32b", "chat", "fallback", ("code", 0.80)),
        ("nomic-embed-text:latest", "embed", "fallback", None),
        # ----- Last-resort default (truly unrecognizable name) -----
        ("xyz-9000-something", "chat", "default", None),
    ],
)
def test_score_model_classifies_correctly(
    name, expected_kind, expected_source, axis_check
):
    desc = score_model(name)
    assert desc.kind == expected_kind, f"{name}: kind={desc.kind!r}"
    assert desc.source == expected_source, f"{name}: source={desc.source!r}"
    if axis_check is not None:
        axis, lo = axis_check
        assert desc.score(axis) >= lo, (
            f"{name}: score({axis})={desc.score(axis)} < {lo}"
        )


def test_score_model_unknown_falls_back_to_neutral():
    """Defaults score 0.5 across all axes."""
    desc = score_model("Totally-Unknown-Model-XYZ")
    for axis in ("chat", "reasoning", "tools", "code", "speed"):
        assert desc.score(axis) == 0.5


# ---------------------------------------------------------- assigner.py


def _pool() -> list[ModelDescriptor]:
    """A realistic mix from the user's downloaded models."""
    return [
        score_model(n)
        for n in (
            "Hermes-3-Llama-3.1-8B-Q4_K_M",
            "Qwen3.6-27B-Q4_K_M",
            "Qwen2.5-14B-Instruct-Q4_K_M",
            "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M",
            "Llama-3.2-3B-Instruct-Q4_K_M",
            "Phi-3.5-mini-instruct-Q4_K_M",
            "gemma-4-E2B-it-Q4_K_M",  # NEW: small chat winner under 4 GB ceiling
            "nomic-embed-text-v1.5",
            "whisper-base-en",
            "piper-amy-en",
            "piper-ryan-en",
        )
    ]


# Each row: (slot, expected_model_substring_in_name)
EXPECTED_PICKS = [
    # v0.5.2: chat is RAM-bounded by an adaptive ceiling (~40% of system
    # RAM, clamped to [3, 32] GB). Tests pin the ceiling explicitly via
    # DEEPER_NOTEBOOK_CHAT_RAM_GB_CEILING fixture below — at 4 GB, gemma-4-E2B wins.
    ("chat", "gemma-4-E2B"),
    # Hermes-3 is the tool specialist — should win Tools regardless of size
    ("tools", "Hermes-3"),
    # Embedding / TTS / STT are kind-filtered — only one eligible each
    ("embedding", "nomic-embed-text-v1.5"),
    ("stt", "whisper-base-en"),
    # large_context requires >= 32k — Phi/Hermes/Qwen2.5/Qwen3 all qualify;
    # weights favor chat depth + log10(ctx) so Qwen3.6-27B or 2.5-14B wins
    ("large_context", "Qwen"),
    # Transformation favors reasoning + chat — Qwen3.6-27B should win
    ("transformation", "Qwen3.6-27B"),
    # ONP v0.5 — Reasoning slot picks the purpose-built reasoner
    # (DeepSeek-R1-Distill is the only model in the test pool with
    # reasoning >= 0.75)
    ("reasoning", "R1-Distill"),
]


@pytest.fixture(autouse=True)
def _pin_chat_ram_ceiling(monkeypatch):
    """Lock the chat-slot RAM ceiling so tests are deterministic across
    machines (a 64 GB Mac would otherwise pick a different chat model than
    a 16 GB Mac on the same test pool). 4.0 GB matches what the standard
    EXPECTED_PICKS row asserts."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_CHAT_RAM_GB_CEILING", "4.0")


@pytest.mark.parametrize("slot,name_contains", EXPECTED_PICKS)
def test_pick_for_slot_matches_expected(slot, name_contains):
    pick = pick_for_slot(slot, _pool())
    assert pick.model is not None, f"{slot}: no model picked. reason={pick.reason}"
    assert name_contains in pick.model.name, (
        f"{slot}: picked {pick.model.name!r}, expected substring {name_contains!r}. "
        f"reason={pick.reason}"
    )


def test_tts_picks_first_piper_deterministically():
    """Both piper-amy and piper-ryan are eligible; tie-break is alphabetical."""
    pick = pick_for_slot("tts", _pool())
    assert pick.model is not None
    assert pick.model.name == "piper-amy-en"  # amy < ryan alphabetically


def test_no_eligible_models_returns_pick_with_none():
    """A pool with no embedders → embedding slot has model=None."""
    pool = [score_model("Hermes-3-Llama-3.1-8B-Q4_K_M")]
    pick = pick_for_slot("embedding", pool)
    assert pick.model is None
    assert "no eligible" in pick.reason


def test_assign_all_returns_pick_for_every_slot():
    picks = assign_all(_pool())
    assert set(picks.keys()) == set(SLOTS)
    # Slots we expect to have a model in our pool
    for slot in (
        "chat",
        "tools",
        "transformation",
        "large_context",
        "embedding",
        "tts",
        "stt",
    ):
        assert picks[slot].model is not None, f"slot={slot} reason={picks[slot].reason}"


def test_reasoning_model_does_not_win_chat_slot():
    """R1-Distill has reasoning=0.95 but speed=0.35 + the chat recipe penalizes
    reasoning. The fast chat models should win."""
    picks = assign_all(_pool())
    chat_pick = picks["chat"].model
    assert chat_pick is not None
    assert "R1" not in chat_pick.name and "Distill" not in chat_pick.name


def test_deterministic_across_runs():
    """Same input pool → identical output (idempotent re-assignment on relaunch)."""
    pool = _pool()
    a = assign_all(pool)
    b = assign_all(pool)
    for slot in SLOTS:
        if a[slot].model is None:
            assert b[slot].model is None
        else:
            assert a[slot].model.name == b[slot].model.name


# ---------------------------------------------------------- pick_chat_llm_file


def test_pick_chat_llm_file_respects_ram_ceiling(tmp_path):
    """The launcher uses this to decide which GGUF to load into the chat
    server. With ceiling=4, gemma-4-E2B (3 GB) should win over Hermes-3 (5 GB)
    despite Hermes scoring higher on tools."""
    from desktop.auto_register.assigner import pick_chat_llm_file

    # Make non-tiny dummy files so the size filter (skip < 1 MB) passes
    big = b"x" * 2_000_000
    (tmp_path / "Hermes-3-Llama-3.1-8B-Q4_K_M.gguf").write_bytes(big)
    (tmp_path / "Qwen3.6-27B-Q4_K_M.gguf").write_bytes(big)
    (tmp_path / "gemma-4-E2B-it-Q4_K_M.gguf").write_bytes(big)
    (tmp_path / "Phi-3.5-mini-instruct-Q4_K_M.gguf").write_bytes(big)

    chosen = pick_chat_llm_file(tmp_path, ram_ceiling_gb=4.0)
    assert chosen is not None
    assert "gemma-4-E2B" in chosen.name

    # Higher ceiling: Hermes-3 wins (its tools=0.95 + chat=0.85 still trumps gemma)
    chosen_big = pick_chat_llm_file(tmp_path, ram_ceiling_gb=16.0)
    assert chosen_big is not None
    assert "Hermes-3" in chosen_big.name


def test_pick_chat_llm_file_skips_stub_files(tmp_path):
    """29-byte stub GGUFs (from failed downloads — we deleted some of those
    earlier in the session) should not be selectable. The 1 MB threshold
    catches them."""
    from desktop.auto_register.assigner import pick_chat_llm_file

    (tmp_path / "ministral-3-14b-fallback-Q4_K_M.gguf").write_bytes(b"x" * 29)
    (tmp_path / "gemma-4-E2B-it-Q4_K_M.gguf").write_bytes(b"x" * 2_000_000)
    chosen = pick_chat_llm_file(tmp_path, ram_ceiling_gb=4.0)
    assert chosen is not None
    assert "ministral" not in chosen.name


def test_pick_chat_llm_file_returns_none_for_empty_dir(tmp_path):
    """No GGUFs → None. Caller (app.py) handles by skipping the chat-server
    spawn."""
    from desktop.auto_register.assigner import pick_chat_llm_file

    assert pick_chat_llm_file(tmp_path) is None
    missing = tmp_path / "does-not-exist"
    assert pick_chat_llm_file(missing) is None


def test_pick_chat_llm_file_falls_back_when_no_models_fit_ceiling(tmp_path):
    """If every model is too big for the ceiling, the function falls back to
    the highest-scoring chat-kind model (instead of returning None and
    leaving the user without a chat server)."""
    from desktop.auto_register.assigner import pick_chat_llm_file

    big = b"x" * 2_000_000
    (tmp_path / "Qwen3.6-27B-Q4_K_M.gguf").write_bytes(big)  # 16 GB
    (tmp_path / "Qwen2.5-14B-Instruct-Q4_K_M.gguf").write_bytes(big)  # 9 GB
    chosen = pick_chat_llm_file(tmp_path, ram_ceiling_gb=4.0)
    assert chosen is not None
    # Fell back to a larger model rather than returning None
    assert chosen.name.endswith(".gguf")


# v0.6.11 — Cross-platform RAM probe regression tests
def test_ram_probe_prefers_psutil_when_available(monkeypatch):
    """psutil works on Windows where os.sysconf raises AttributeError. We
    must use it when present so Windows users don't get the 4 GB fallback."""
    from desktop.auto_register import assigner

    class _FakeVmem:
        total = 64 * 1024**3  # 64 GB

    fake_psutil = type(
        "psutil", (), {"virtual_memory": staticmethod(lambda: _FakeVmem())}
    )
    monkeypatch.setitem(__import__("sys").modules, "psutil", fake_psutil)
    assert assigner._probe_total_ram_gb() == 64.0


def test_ram_probe_falls_back_to_sysconf_when_psutil_missing(monkeypatch):
    """If psutil isn't importable (super-minimal env), the sysconf path
    still works on Mac/Linux."""
    import sys

    from desktop.auto_register import assigner

    # Hide psutil from the lookup
    monkeypatch.setitem(sys.modules, "psutil", None)
    # Skip on Windows where os.sysconf doesn't exist regardless of psutil
    if not hasattr(__import__("os"), "sysconf"):
        import pytest

        pytest.skip("os.sysconf unavailable (Windows)")
    val = assigner._probe_total_ram_gb()
    # Should produce SOMETHING positive
    assert val is None or val > 0


def test_ram_probe_returns_none_when_everything_fails(monkeypatch):
    """Caller (_get_chat_ram_ceiling_gb) relies on None → 4.0 fallback."""
    import os
    import sys

    from desktop.auto_register import assigner

    monkeypatch.setitem(sys.modules, "psutil", None)
    monkeypatch.delattr(os, "sysconf", raising=False)
    assert not hasattr(os, "sysconf")  # Windows condition this test covers
    assert assigner._probe_total_ram_gb() is None
