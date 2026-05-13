"""Given a pool of ModelDescriptors, pick the best fit for each role slot.

Each slot has a *recipe*: weighted axes + a kind filter + optional minimum
constraints. Picks are deterministic — given the same input pool, the output
never changes — so re-running auto_register on relaunch is idempotent.

Every pick comes with a human-readable `reason` for logging, so users can run
`cat ~/.open-notebook-plus/logs/auto_register.log` and see WHY each slot got
the model it got.
"""
from __future__ import annotations

from dataclasses import dataclass

from desktop.auto_register.capability import ModelDescriptor


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
        "kinds": {"chat"},
        "weights": {"chat": 0.55, "speed": 0.25, "tools": 0.10, "reasoning": -0.10},
        "require": None,
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


def _format_top_axes(weights: dict[str, float], desc: ModelDescriptor, n: int = 2) -> str:
    """Top contributing positive axes for explainability in the reason string."""
    pairs = [
        (axis, w * desc.score(axis))
        for axis, w in weights.items()
        if w > 0
    ]
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
        return Pick(slot=slot, model=None, score=0.0,
                    reason=f"no eligible models (kinds={recipe['kinds']})")

    if not recipe["weights"]:
        # Type-only slots (embedding/tts/stt) — first registered wins
        chosen = sorted(candidates, key=lambda d: d.name)[0]
        return Pick(slot=slot, model=chosen, score=1.0,
                    reason=f"first {chosen.kind} registered ({chosen.source})")

    scored = [(d, _score(d, recipe)) for d in candidates]
    # Deterministic tie-break: name ascending
    scored.sort(key=lambda p: (-p[1], p[0].name))
    chosen, top = scored[0]
    top_axes = _format_top_axes(recipe["weights"], chosen)
    return Pick(
        slot=slot, model=chosen, score=top,
        reason=f"{top_axes} ({chosen.source})",
    )


def assign_all(pool: list[ModelDescriptor]) -> dict[str, Pick]:
    """Run pick_for_slot across all known slots."""
    return {slot: pick_for_slot(slot, pool) for slot in SLOTS}
