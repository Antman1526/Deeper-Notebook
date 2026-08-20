"""v0.8.113 — Reciprocal Rank Fusion for hybrid retrieval.

WHY

`/api/search` has always run exactly one leg. `api/routers/search.py` reads:

    if effective_type == "vector":  ... else: text_search(...)

Keyword and semantic retrieval fail in different directions — BM25-style text
search misses paraphrase, vector search misses exact identifiers, rare proper
nouns, and error strings — so answering with one and discarding the other loses
recall on every query. Fusing them is the best-understood quality win available
to a retrieval system, and this codebase already computes both legs; it simply
threw one away.

The approach is taken from qmd (github.com/tobi/qmd, MIT), which fuses BM25 +
vector + an LLM reranker with RRF. Only the *architecture* is borrowed. qmd is
Node/TypeScript over SQLite FTS5 + sqlite-vec and is not a drop-in for a
Python/SurrealDB app; the reranker leg is deliberately not implemented here
because it would add another GGUF to the sidecar fleet for a benefit this
codebase has not yet measured.

WHY RRF AND NOT SCORE BLENDING

The two legs produce incomparable numbers: vector search returns cosine
similarity in [0, 1], text search returns a SurrealDB relevance score on an
unbounded scale that shifts with corpus size. Normalising them against each
other requires calibration that would silently rot as the corpus grows. RRF
uses only ORDER, so it needs no calibration and cannot be skewed by one leg
reporting large magnitudes.

    score(d) = sum over legs of 1 / (k + rank(d))

`k` damps the head of each list so a single leg cannot dominate on rank alone;
60 is the value from the original Cormack et al. formulation and the one qmd
uses. It is exposed as a parameter for tests rather than for tuning.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

# Cormack et al. 2009. Larger k flattens the contribution of top ranks; smaller
# k lets a single leg's #1 dominate. Not env-tunable on purpose: a retrieval
# knob nobody can evaluate is a knob that gets set badly.
DEFAULT_RRF_K = 60


def _result_identity(row: Any) -> str | None:
    """Stable identity for a search row, so the same document fuses as one.

    Rows come from two different SurrealQL functions and are not guaranteed to
    carry identical field sets, so several id spellings are accepted. A row
    without any usable id is passed through rather than dropped — losing a
    result to a missing field would be a worse failure than ranking it poorly.
    """
    if not isinstance(row, dict):
        return None
    for key in ("id", "item_id", "source_id", "note_id"):
        value = row.get(key)
        if value:
            return str(value)
    return None


def reciprocal_rank_fusion(
    legs: Sequence[Iterable[Any]],
    *,
    limit: int,
    k: int = DEFAULT_RRF_K,
) -> list[Any]:
    """Fuse ranked result lists by reciprocal rank.

    Args:
        legs: ranked results, best first, one sequence per retrieval leg.
        limit: maximum rows to return.
        k: RRF damping constant.

    Returns:
        Rows ordered by fused score, each row appearing once. The first
        occurrence of a document is the one returned, so whichever leg ranked it
        higher supplies its fields — that leg had more confidence in it.

    Rows without a resolvable identity are kept and ranked, but never merged
    with anything, since there is no safe way to prove two of them are the same
    document.
    """
    if limit <= 0:
        return []

    scores: dict[str, float] = {}
    representatives: dict[str, Any] = {}
    best_rank: dict[str, int] = {}
    anonymous: list[tuple[float, int, Any]] = []
    order = 0

    for leg in legs:
        for rank, row in enumerate(leg or []):
            contribution = 1.0 / (k + rank + 1)
            identity = _result_identity(row)
            if identity is None:
                anonymous.append((contribution, order, row))
                order += 1
                continue
            # Keep the copy from whichever leg ranked it HIGHEST, not whichever
            # leg happened to be iterated first. The two legs return overlapping
            # but not identical field sets, and the leg that ranked a document
            # higher is the one that was more confident about it. Ties keep the
            # incumbent so leg order still breaks them deterministically.
            if identity not in representatives or rank < best_rank[identity]:
                representatives[identity] = row
                best_rank[identity] = rank
            scores[identity] = scores.get(identity, 0.0) + contribution

    fused: list[tuple[float, int, Any]] = [
        # Ties break on first-seen order so the output is deterministic; a
        # search endpoint that reshuffles equal-scoring rows between identical
        # requests is impossible to test and unsettling to use.
        (score, index, representatives[identity])
        for index, (identity, score) in enumerate(scores.items())
    ]
    fused.extend(anonymous)
    fused.sort(key=lambda item: (-item[0], item[1]))
    return [row for _score, _index, row in fused[:limit]]
