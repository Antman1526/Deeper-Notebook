"""Deterministic claim verification against response-selected source text."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from deeper_notebook.evaluation.claims import ExtractedClaim, extract_material_claims
from deeper_notebook.evaluation.schemas import (
    ClaimVerdict,
    EvidenceSpan,
    hash_source_text,
)
from deeper_notebook.utils.citation_offsets import _content_tokens, slice_passage

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")
_NUMBER_RE = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?%?\b")
_ENTITY_RE = re.compile(r"\b(?:[A-Z][A-Za-z0-9-]*|[A-Z]{2,})\b")
_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|none|without|cannot|can't|won't|neither|nor)\b", re.I
)
_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}


@dataclass(frozen=True)
class CitationSource:
    """The immutable source snapshot selected by one response citation marker."""

    source_id: str
    text: str
    source_content_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ValueError("citation source_id must be a non-empty string")
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("citation source text must be a non-empty string")
        actual_hash = hash_source_text(self.text)
        if (
            self.source_content_sha256 is not None
            and self.source_content_sha256 != actual_hash
        ):
            raise ValueError("citation source hash does not match its text")
        object.__setattr__(self, "source_content_sha256", actual_hash)


@dataclass(frozen=True)
class _CandidatePassage:
    source: CitationSource
    start: int
    end: int
    quote: str
    score: float
    numeric_mismatch: bool
    entity_mismatch: bool
    negation_mismatch: bool


def _numbers(text: str) -> set[str]:
    values = {value.replace(",", "").lower() for value in _NUMBER_RE.findall(text)}
    values.update(
        _NUMBER_WORDS[token]
        for token in re.findall(r"[a-z]+", text.lower())
        if token in _NUMBER_WORDS
    )
    return values


def _entities(text: str) -> set[str]:
    return {value.lower() for value in _ENTITY_RE.findall(text) if len(value) > 1}


def _has_negation(text: str) -> bool:
    return bool(_NEGATION_RE.search(text))


def _passages(source: CitationSource) -> list[tuple[int, int, str]]:
    """Yield bounded source passages using original Unicode-codepoint offsets."""
    passages: list[tuple[int, int, str]] = []
    for match in _SENTENCE_RE.finditer(source.text):
        start, end = match.start(), min(match.end(), match.start() + 1200)
        raw_quote = slice_passage(source.text, start, end)
        quote = raw_quote.strip()
        if quote:
            # Evidence offsets must still address the trimmed quote exactly.
            quote_start = start + (len(raw_quote) - len(raw_quote.lstrip()))
            passages.append((quote_start, quote_start + len(quote), quote))
    return passages


def _best_candidate(
    claim_text: str, sources: list[CitationSource]
) -> _CandidatePassage | None:
    claim_tokens = _content_tokens(claim_text)
    claim_numbers = _numbers(claim_text)
    claim_entities = _entities(claim_text)
    if not claim_tokens:
        return None

    best: _CandidatePassage | None = None
    for source in sources:
        for start, end, quote in _passages(source):
            quote_tokens = _content_tokens(quote)
            if not quote_tokens:
                continue
            score = len(claim_tokens & quote_tokens) / len(claim_tokens)
            quote_numbers = _numbers(quote)
            quote_entities = _entities(quote)
            candidate = _CandidatePassage(
                source=source,
                start=start,
                end=end,
                quote=quote,
                score=score,
                numeric_mismatch=bool(claim_numbers) and claim_numbers != quote_numbers,
                entity_mismatch=bool(claim_entities)
                and not claim_entities.issubset(quote_entities),
                negation_mismatch=_has_negation(claim_text) != _has_negation(quote),
            )
            if best is None or candidate.score > best.score:
                best = candidate
    return best


def _evidence(candidate: _CandidatePassage) -> EvidenceSpan:
    return EvidenceSpan(
        source_id=candidate.source.source_id,
        source_content_sha256=candidate.source.source_content_sha256 or "",
        start=candidate.start,
        end=candidate.end,
        quote=candidate.quote,
    )


def _explanation(status: str, candidate: _CandidatePassage | None) -> str:
    if candidate is None:
        return "No selected citation passage contains enough of the claim to verify it."
    if status == "supported":
        return "The selected source passage agrees with the claim's material terms."
    if status == "contradicted":
        if candidate.numeric_mismatch:
            return "The selected source passage uses a different numeric or date value."
        return "The selected source passage has the opposite negation or factual assertion."
    if status == "partial":
        return "The selected source passage overlaps with the claim but does not establish every material term."
    return "The selected citation does not support the claim."


def verify_claim(
    claim: ExtractedClaim | str,
    response_citation_map: Mapping[str, CitationSource],
) -> ClaimVerdict:
    """Return a contract-valid verdict using only response-selected sources.

    An unknown marker is rejected rather than searched globally: a response can
    only claim support from sources that were explicitly selected for it.
    """
    if isinstance(claim, str):
        extracted = extract_material_claims(claim)
        if len(extracted) != 1:
            raise ValueError("verify_claim requires exactly one material claim")
        claim = extracted[0]

    markers = list(claim.citation_markers)
    if not markers:
        return ClaimVerdict(
            claim=claim.text,
            status="uncited",
            confidence=1.0,
            explanation="The material claim has no citation marker in the response.",
        )

    unknown_markers = [
        marker for marker in markers if marker not in response_citation_map
    ]
    if unknown_markers:
        raise ValueError(
            "citation marker is not in the response citation map: "
            + ", ".join(unknown_markers)
        )
    sources = [response_citation_map[marker] for marker in markers]
    candidate = _best_candidate(claim.text, sources)
    if candidate is None or candidate.score < 0.30:
        status = "unsupported"
    elif candidate.score >= 0.50 and (
        candidate.numeric_mismatch or candidate.negation_mismatch
    ):
        status = "contradicted"
    elif candidate.score >= 0.85 and not (
        candidate.numeric_mismatch
        or candidate.entity_mismatch
        or candidate.negation_mismatch
    ):
        status = "supported"
    elif candidate.score >= 0.40:
        status = "partial"
    else:
        status = "unsupported"

    evidence = (
        [] if status == "unsupported" or candidate is None else [_evidence(candidate)]
    )
    confidence = round(min(0.99, max(0.0, candidate.score if candidate else 0.0)), 3)
    if status == "contradicted":
        confidence = max(confidence, 0.8)
    return ClaimVerdict(
        claim=claim.text,
        status=status,
        confidence=confidence,
        citation_markers=markers,
        evidence=evidence,
        explanation=_explanation(status, candidate)[:1000],
    )


def verify_response_claims(
    response_text: str,
    response_citation_map: Mapping[str, CitationSource],
) -> list[ClaimVerdict]:
    """Extract and verify all material claims from one generated response."""
    return [
        verify_claim(claim, response_citation_map)
        for claim in extract_material_claims(response_text)
    ]
