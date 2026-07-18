"""Deterministic extraction of material, source-grounded claims."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CITATION_MARKER_RE = re.compile(r"\[[^\[\]\n]{1,160}\]")
_SENTENCE_RE = re.compile(r"[^\n.!?]+(?:\[[^\[\]\n]{1,160}\])?[.!?]?")
_COMMAND_RE = re.compile(
    r"^(?:please\s+)?(?:run|execute|install|open|create|delete|remove|deploy|"
    r"click|select|use|add|set|configure|restart|try)\b",
    re.IGNORECASE,
)
_SUBJECTIVE_RE = re.compile(
    r"\b(?:i\s+(?:think|believe|feel)|in\s+my\s+opinion|feels?|"
    r"beautiful|amazing|great|best|worst|prefer)\b",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"^(?:who|what|when|where|why|how|can|could|should|would|is|are|do|does|did)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedClaim:
    """One material statement plus its exact response location and markers."""

    text: str
    text_with_markers: str
    start: int
    end: int
    citation_markers: tuple[str, ...]


def _without_markers(text: str) -> str:
    cleaned = _CITATION_MARKER_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", cleaned)


def _is_material_declaration(candidate: str, cleaned: str) -> bool:
    stripped = candidate.strip()
    if not cleaned or stripped.startswith("#") or stripped.startswith(">"):
        return False
    if stripped.startswith(("```", "`")) or "`" in stripped:
        return False
    if stripped.startswith(("- ", "* ", "+ ")):
        stripped = stripped[2:].lstrip()
    if stripped.endswith("?") or _QUESTION_RE.match(stripped):
        return False
    if _COMMAND_RE.match(stripped) or _SUBJECTIVE_RE.search(stripped):
        return False
    # A material claim needs enough lexical content to evaluate against evidence.
    return len(re.findall(r"[A-Za-z0-9]+", cleaned)) >= 3


def extract_material_claims(response_text: str) -> list[ExtractedClaim]:
    """Return material declarative claims from a generated response.

    The extractor deliberately avoids model calls. It keeps Unicode codepoint
    offsets into the original response so callers can render a verdict next to
    the exact generated statement rather than a reconstructed paraphrase.
    """
    if not isinstance(response_text, str) or not response_text:
        return []

    claims: list[ExtractedClaim] = []
    for match in _SENTENCE_RE.finditer(response_text):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw) - len(raw.rstrip())
        start = match.start() + leading
        end = match.end() - trailing if trailing else match.end()
        candidate = response_text[start:end]
        cleaned = _without_markers(candidate)
        if not _is_material_declaration(candidate, cleaned):
            continue

        markers = tuple(dict.fromkeys(_CITATION_MARKER_RE.findall(candidate)))
        claims.append(
            ExtractedClaim(
                text=cleaned,
                text_with_markers=candidate,
                start=start,
                end=end,
                citation_markers=markers,
            )
        )
    return claims
