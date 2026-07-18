"""v0.8.78 — citation passage location (improvement roadmap, Batch 2).

ONP citations are bare record IDs (``[source:ID]``) with no passage offsets, so
there's nothing to scroll-to/highlight when a user clicks a citation. Rather
than change the citation FORMAT (which the frontend CitationPill parser + many
tests depend on), we locate the cited passage *on demand*: given a source's
extracted ``full_text`` and the citing sentence (the "query"), find the char
offset range of the best-matching window. The frontend passes the sentence that
precedes a clicked citation and uses the returned [start, end] to highlight the
passage in the source viewer.

The matcher is deliberately simple + deterministic (token-containment over a
sliding window) so it's fully unit-testable and needs no embeddings/LLM. It
returns the most-overlapping region; an exact highlight isn't guaranteed (the
LLM paraphrases), but it reliably lands the reader in the right area — which is
the goal. Returns ``None`` when there's no decent match so the caller can fall
back to just opening the source at the top.
"""

from __future__ import annotations

import re
from typing import Optional, TypedDict

_TOKEN_RE = re.compile(r"[a-z0-9]+")
# Common words carry little locating signal; ignoring them sharpens the match.
_STOPWORDS = frozenset(
    "the a an of to in and or is are was were be been being it its this that "
    "these those for on at by with as from into about over under than then so "
    "such not no nor but if while which who whom whose what when where why how "
    "their there here have has had do does did can could should would may might "
    "will shall i you he she we they me him her us them my your his our".split()
)


class PassageMatch(TypedDict):
    start: int
    end: int
    score: float
    snippet: str


def _tokens(s: str) -> list[str]:
    return _TOKEN_RE.findall(s.lower())


def _content_tokens(s: str) -> set[str]:
    return {t for t in _tokens(s) if t not in _STOPWORDS and len(t) > 1}


def slice_passage(text: str, start: int, end: int) -> str:
    """Return an exact Unicode-codepoint source slice after bounds validation.

    Evidence contracts persist codepoint offsets, so malformed or byte-based
    offsets must fail rather than silently producing a nearby quote.
    """
    if not isinstance(text, str):
        raise ValueError("source text must be a string")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
    ):
        raise ValueError("citation offsets must be integers")
    if start < 0 or end <= start or end > len(text):
        raise ValueError("citation offsets are outside the source text")
    return text[start:end]


def locate_passage(
    text: str,
    query: str,
    *,
    window: int = 280,
    stride: int = 120,
    min_score: float = 0.2,
) -> Optional[PassageMatch]:
    """Find the char-offset range of the passage in ``text`` that best matches
    ``query`` (the citing sentence).

    Returns ``{start, end, score, snippet}`` for the best window whose
    query-token containment is >= ``min_score``, else ``None``. ``start``/``end``
    are snapped outward to word boundaries so a highlight never splits a word.
    """
    if not text or not query:
        return None
    qset = _content_tokens(query)
    if not qset:
        return None

    n = len(text)
    best_start = -1
    best_score = 0.0
    i = 0
    while i < n:
        chunk = text[i : i + window]
        cset = _content_tokens(chunk)
        if cset:
            # Containment of the query's content words within this window.
            score = len(qset & cset) / len(qset)
            if score > best_score:
                best_score = score
                best_start = i
        if i + window >= n:
            break
        i += stride

    if best_start < 0 or best_score < min_score:
        return None

    start = best_start
    end = min(best_start + window, n)
    # Snap outward to whitespace so we don't cut mid-word.
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    while end < n and not text[end].isspace():
        end += 1
    snippet = text[start:end].strip()
    return PassageMatch(
        start=start, end=end, score=round(best_score, 3), snippet=snippet
    )
