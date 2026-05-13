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
        ("Hermes-3-Llama-3.1-8B-Q4_K_M.gguf", "chat",      "registry", ("tools",     0.90)),
        ("DeepSeek-R1-Distill-Qwen-14B-Q4_K_M", "reasoning","registry", ("reasoning", 0.90)),
        ("Qwen2.5-Coder-7B-Instruct",         "chat",      "registry", ("code",      0.90)),
        ("nomic-embed-text-v1.5",              "embed",     "registry", None),
        ("whisper-base-en",                    "stt",       "registry", None),
        ("piper-amy-en",                       "tts",       "registry", None),
        # ----- Fallback patterns -----
        ("MyNew-Coder-9B-Instruct",            "chat",      "fallback", ("code",      0.80)),
        ("Some-R1-Reasoning-Distill",          "reasoning", "fallback", ("reasoning", 0.80)),
        ("ImaginaryEmbed-2",                   "embed",     "fallback", None),
        ("whisper-medium-multilingual",        "stt",       "fallback", None),
        # ----- Last-resort default -----
        ("Totally-Unknown-Model-XYZ",          "chat",      "default",  None),
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
    return [score_model(n) for n in (
        "Hermes-3-Llama-3.1-8B-Q4_K_M",
        "Qwen3.6-27B-Q4_K_M",
        "Qwen2.5-14B-Instruct-Q4_K_M",
        "DeepSeek-R1-Distill-Qwen-14B-Q4_K_M",
        "Llama-3.2-3B-Instruct-Q4_K_M",
        "Phi-3.5-mini-instruct-Q4_K_M",
        "nomic-embed-text-v1.5",
        "whisper-base-en",
        "piper-amy-en",
        "piper-ryan-en",
    )]


# Each row: (slot, expected_model_substring_in_name)
EXPECTED_PICKS = [
    # Hermes-3 is the tool specialist — should win Tools regardless of size
    ("tools",          "Hermes-3"),
    # Embedding / TTS / STT are kind-filtered — only one eligible each
    ("embedding",      "nomic-embed-text-v1.5"),
    ("stt",            "whisper-base-en"),
    # large_context requires >= 32k — Phi/Hermes/Qwen2.5/Qwen3 all qualify;
    # weights favor chat depth + log10(ctx) so Qwen3.6-27B or 2.5-14B wins
    ("large_context",  "Qwen"),
    # Transformation favors reasoning + chat — Qwen3.6-27B should win
    ("transformation", "Qwen3.6-27B"),
    # ONP v0.5 — Reasoning slot picks the purpose-built reasoner
    # (DeepSeek-R1-Distill is the only model in the test pool with
    # reasoning >= 0.75)
    ("reasoning",      "R1-Distill"),
]


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
    for slot in ("chat", "tools", "transformation", "large_context",
                 "embedding", "tts", "stt"):
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
