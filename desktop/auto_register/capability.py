"""Score a model name → ModelDescriptor (kind + 5 capability scores + meta).

Order of resolution:
  1. Exact-prefix match in model_registry.MODELS (longest prefix wins)
  2. Regex pass over FALLBACK_PATTERNS — first match sets `kind`, all match
     score-deltas merge
  3. Last-resort defaults (kind="chat", all scores=0.5)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from desktop.auto_register import model_registry as reg


@dataclass(frozen=True)
class ModelDescriptor:
    name: str  # original model name as registered
    kind: str  # "chat" | "reasoning" | "embed" | "stt" | "tts"
    scores: dict[str, float] = field(default_factory=dict)
    context_len: int = 0  # tokens
    ram_gb_q4: float = 0.0  # rough memory footprint at Q4
    source: str = "default"  # "registry" | "fallback" | "default" — useful in logs

    def score(self, axis: str) -> float:
        return self.scores.get(axis, 0.5)


@lru_cache(maxsize=512)
def score_model(name: str) -> ModelDescriptor:
    """Resolve a model name to its capability descriptor.

    Never raises — unknown models return a neutral descriptor so callers can
    proceed without special-casing.

    Memoized: assignment fires score_model repeatedly across slots for the
    same model name. Cache size 512 covers any realistic model pool with
    headroom.
    """
    # 1. Exact-prefix match in the curated registry
    prefix = reg._lookup_prefix(name)
    if prefix is not None:
        entry = reg.MODELS[prefix]
        return ModelDescriptor(
            name=name,
            kind=entry["kind"],
            scores={**reg.DEFAULT_SCORES, **entry.get("scores", {})}
            if entry["kind"] in ("chat", "reasoning")
            else {},
            context_len=entry.get("context_len", 0),
            ram_gb_q4=entry.get("ram_gb_q4", 0.0),
            source="registry",
        )

    # 2. Filename regex fallback — patterns are ordered baseline → specializing.
    # Both kind AND scores merge with "last match wins" semantics so a
    # specializing pattern (e.g. `r1` for reasoning) overrides an earlier
    # baseline (e.g. `deepseek` for generic chat).
    kind: str | None = None
    scores: dict[str, float] = {}
    for pattern, score_delta, pkind in reg.FALLBACK_PATTERNS:
        if re.search(pattern, name):
            if pkind is not None:
                kind = pkind
            scores.update(score_delta)
    if kind is not None:
        if kind in ("chat", "reasoning"):
            merged = {**reg.DEFAULT_SCORES, **scores}
        else:
            merged = {}  # embed/stt/tts don't use the 5-axis vector
        return ModelDescriptor(
            name=name,
            kind=kind,
            scores=merged,
            source="fallback",
        )

    # 3. Last-resort default — neutral chat model
    return ModelDescriptor(
        name=name,
        kind="chat",
        scores=dict(reg.DEFAULT_SCORES),
        source="default",
    )
