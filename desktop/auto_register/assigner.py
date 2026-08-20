"""Given a pool of ModelDescriptors, pick the best fit for each role slot.

Each slot has a *recipe*: weighted axes + a kind filter + optional minimum
constraints. Picks are deterministic — given the same input pool, the output
never changes — so re-running auto_register on relaunch is idempotent.

Every pick comes with a human-readable `reason` for logging, so users can run
`cat ~/.deeper-notebook/logs/auto_register.log` and see WHY each slot got
the model it got.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from deeper_notebook.environment import resolve_env
from desktop.auto_register.capability import ModelDescriptor, score_model


def _detect_total_ram_gb() -> float | None:
    """Memoize the system-RAM probe — total RAM is constant per process."""
    return _detect_total_ram_gb._cached  # type: ignore[attr-defined]


def _probe_total_ram_gb() -> float | None:
    """Cross-platform total-RAM probe in GB.

    v0.6.11 — previously os.sysconf-only, which only works on Mac/Linux. On
    Windows os.sysconf doesn't exist → AttributeError → `None`, which the
    caller fell back to hardcoded 4 GB. So every Windows user got the
    smallest chat model regardless of having 32 GB / 64 GB / 128 GB.

    Strategy:
      1. psutil if available (already in pyproject deps) — accurate on all
         platforms.
      2. os.sysconf — fast path on Mac/Linux when psutil somehow isn't
         importable (e.g. minimal frozen build).
      3. None — caller falls back to a sensible 4 GB.
    """
    try:
        import psutil  # type: ignore

        return psutil.virtual_memory().total / (1024**3)
    except Exception:
        pass
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / (1024**3)
    except (OSError, AttributeError, ValueError):
        return None


_detect_total_ram_gb._cached = _probe_total_ram_gb()  # type: ignore[attr-defined]


def _get_chat_ram_ceiling_gb() -> float:
    """Compute the chat-slot RAM ceiling in GB.

    Adaptive by default: ~40% of total system RAM, clamped to [3, 32] GB.
    Floor of 3 GB ensures gemma-4-E2B (3 GB) qualifies on small machines.
    Cap of 32 GB ensures the chat slot never tries to load a frontier model
    that would starve the rest of the supervisor process tree.

    Examples (clamped 40% rule):
      8 GB Mac  → ceiling = 3.0 GB  (Llama-3.2-3B / gemma-4-E2B fit)
      16 GB Mac → ceiling = 6.4 GB  (Hermes-3-8B / Qwen3.5-9B fit)
      32 GB Mac → ceiling = 12.8 GB (Qwen2.5-14B fits comfortably)
      64 GB Mac → ceiling = 25.6 GB (Qwen3.6-35B-A3B at 21 GB fits)
      128 GB+   → ceiling = 32.0 GB (Qwen3.6-35B-A3B still wins)

    Env var override:
      DEEPER_NOTEBOOK_CHAT_RAM_GB_CEILING=N    pins to N GB regardless of system RAM
    """
    env = resolve_env("DEEPER_NOTEBOOK_CHAT_RAM_GB_CEILING")
    if env:
        try:
            return max(0.5, float(env))
        except ValueError:
            pass
    total_gb = _detect_total_ram_gb()
    if total_gb is None:
        return 4.0  # sysconf unavailable (Windows fallback)
    return max(3.0, min(32.0, total_gb * 0.40))


@dataclass(frozen=True)
class Pick:
    slot: str
    model: ModelDescriptor | None
    score: float
    reason: str


# Recipes per slot. Each:
#   kinds:    set of acceptable `kind` values (filter)
#   weights:  axis → weight; final = sum(weight_i * model.score(axis_i))
#             penalties expressed as negative weights
#   require:  optional callable (ModelDescriptor) -> bool — disqualifies below threshold
#   ctx_bias: bonus per log10(context_len). Used for `large_context`.
_RECIPES: dict[str, dict] = {
    "chat": {
        # Casual conversational use. Reasoning models are excluded (the
        # `kinds: {"chat"}` filter — they live in the reasoning slot now).
        # RAM-ceiling-bound to the current system; bigger machines get bigger
        # / higher-quality chat models. See _get_chat_ram_ceiling_gb() above.
        "kinds": {"chat"},
        "weights": {"chat": 0.55, "speed": 0.25, "tools": 0.10, "reasoning": -0.10},
        "require": lambda d: d.ram_gb_q4 <= _get_chat_ram_ceiling_gb(),
    },
    "tools": {
        "kinds": {"chat"},
        "weights": {"tools": 0.65, "chat": 0.25, "speed": 0.10},
        "require": lambda d: d.score("tools") >= 0.55,
    },
    "reasoning": {
        # Slow-but-deep slot — used for hard questions, code review, multi-step
        # analysis. Accepts chat models too if they happen to score high on
        # reasoning (e.g. Qwen3.6-35B-A3B with reasoning=0.88), not just
        # purpose-built reasoning models.
        "kinds": {"chat", "reasoning"},
        "weights": {"reasoning": 0.70, "code": 0.15, "chat": 0.10, "speed": -0.05},
        "require": lambda d: d.score("reasoning") >= 0.75,
    },
    "transformation": {
        # Summaries / insights — depth matters, speed less critical
        "kinds": {"chat"},
        "weights": {"chat": 0.45, "reasoning": 0.35, "code": 0.10, "speed": 0.10},
        "require": None,
    },
    "large_context": {
        "kinds": {"chat"},
        "weights": {"chat": 0.35, "reasoning": 0.25, "speed": 0.05},
        "require": lambda d: d.context_len >= 32_000,
        "ctx_bias": 0.35,  # weight on log10(ctx_len/32k) for tie-breaking
    },
    "embedding": {
        "kinds": {"embed"},
        "weights": {},
        "require": None,
    },
    "tts": {
        "kinds": {"tts"},
        "weights": {},
        "require": None,
    },
    "stt": {
        "kinds": {"stt"},
        "weights": {},
        "require": None,
    },
}

SLOTS = tuple(_RECIPES.keys())


def _format_top_axes(
    weights: dict[str, float], desc: ModelDescriptor, n: int = 2
) -> str:
    """Top contributing positive axes for explainability in the reason string."""
    pairs = [(axis, w * desc.score(axis)) for axis, w in weights.items() if w > 0]
    pairs.sort(key=lambda p: -p[1])
    return ", ".join(f"{axis}={desc.score(axis):.2f}" for axis, _ in pairs[:n])


def _score(desc: ModelDescriptor, recipe: dict) -> float:
    base = sum(w * desc.score(axis) for axis, w in recipe["weights"].items())
    if recipe.get("ctx_bias") and desc.context_len > 0:
        # log10(ctx_len / 32k), clipped to [0, 1.5]
        import math

        bonus = min(1.5, max(0.0, math.log10(max(desc.context_len, 1) / 32_000)))
        base += recipe["ctx_bias"] * bonus
    return base


def pick_for_slot(slot: str, pool: list[ModelDescriptor]) -> Pick:
    """Best model for `slot` from `pool`. Returns Pick with model=None if no
    candidate is eligible (e.g. no embeddings registered → embedding slot empty)."""
    recipe = _RECIPES[slot]
    candidates = [d for d in pool if d.kind in recipe["kinds"]]
    if recipe["require"]:
        candidates = [d for d in candidates if recipe["require"](d)]
    if not candidates:
        return Pick(
            slot=slot,
            model=None,
            score=0.0,
            reason=f"no eligible models (kinds={recipe['kinds']})",
        )

    if not recipe["weights"]:
        # Type-only slots (embedding/tts/stt) — first registered wins
        chosen = sorted(candidates, key=lambda d: d.name)[0]
        return Pick(
            slot=slot,
            model=chosen,
            score=1.0,
            reason=f"first {chosen.kind} registered ({chosen.source})",
        )

    scored = [(d, _score(d, recipe)) for d in candidates]
    # Deterministic tie-break: name ascending
    scored.sort(key=lambda p: (-p[1], p[0].name))
    chosen, top = scored[0]
    top_axes = _format_top_axes(recipe["weights"], chosen)
    return Pick(
        slot=slot,
        model=chosen,
        score=top,
        reason=f"{top_axes} ({chosen.source})",
    )


def assign_all(pool: list[ModelDescriptor]) -> dict[str, Pick]:
    """Run pick_for_slot across all known slots."""
    return {slot: pick_for_slot(slot, pool) for slot in SLOTS}


def pick_chat_llm_file(
    gguf_dir: Path,
    *,
    ram_ceiling_gb: float | None = None,
) -> Path | None:
    """Select the best chat-suitable .gguf in `gguf_dir` for the
    llama-cpp chat-completion server to load.

    Same scoring as the `chat` recipe used by the DefaultModels assigner,
    so the loaded model matches what gets assigned. Used by app.py instead
    of the legacy `Hermes-3*.gguf` glob — that hardcoded selection made
    `DEEPER_NOTEBOOK_CHAT_RAM_GB_CEILING` ineffective for the actual chat experience
    (the assignment slot would change, but the loaded model wouldn't).

    Fallback: if no chat-kind model fits the ceiling, return the smallest
    chat-kind model in the directory so the server still spawns; user can
    override via the wizard's default-model field.
    """
    if not gguf_dir.exists():
        return None
    # v0.8.67h — explicit pin. DEEPER_NOTEBOOK_CHAT_LLM_GGUF forces a specific chat GGUF
    # (by filename, with or without the .gguf suffix, case-insensitive) instead
    # of the heuristic scorer below. Addresses "the loaded chat model doesn't
    # match what I picked" — e.g. DEEPER_NOTEBOOK_CHAT_LLM_GGUF=Qwen3.5-9B-Q4_K_M.gguf pins
    # Qwen over the auto-pick. If unset, or the named file isn't present, we fall
    # through to the scorer so the sidecar always spawns with *something*.
    _pin = (resolve_env("DEEPER_NOTEBOOK_CHAT_LLM_GGUF") or "").strip()
    if _pin:
        _pin_name = _pin if _pin.lower().endswith(".gguf") else f"{_pin}.gguf"
        for _cand in sorted(gguf_dir.glob("*.gguf")):
            if _cand.name.lower() == _pin_name.lower():
                return _cand
        # named pin not found in gguf_dir → fall through to the heuristic.
    ceiling = (
        ram_ceiling_gb if ram_ceiling_gb is not None else _get_chat_ram_ceiling_gb()
    )
    recipe = _RECIPES["chat"]

    pool: list[tuple[float, Path, ModelDescriptor]] = []
    fallback_pool: list[tuple[float, Path, ModelDescriptor]] = []
    for path in sorted(gguf_dir.glob("*.gguf")):
        # Filter to keep only valid GGUF files (skip 29-byte stub placeholders
        # and obvious incomplete downloads).
        try:
            if path.stat().st_size < 1_000_000:
                continue
        except OSError:
            continue
        desc = score_model(path.stem)
        if desc.kind != "chat":
            continue
        s = _score(desc, recipe)
        fallback_pool.append((s, path, desc))
        if desc.ram_gb_q4 <= ceiling:
            pool.append((s, path, desc))

    target_pool = pool if pool else fallback_pool
    if not target_pool:
        return None
    # Tie-break by ram_gb_q4 ASC, then name ASC — when scores are close, prefer
    # the smaller model.
    target_pool.sort(key=lambda t: (-t[0], t[2].ram_gb_q4, t[1].name))
    return target_pool[0][1]
