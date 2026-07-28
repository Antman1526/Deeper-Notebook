"""Deterministic, citation-bound agreement and contradiction analysis."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.evaluation.claims import ExtractedClaim, extract_material_claims
from deeper_notebook.evaluation.schemas import ClaimVerdict
from deeper_notebook.evaluation.verifier import CitationSource, verify_claim
from deeper_notebook.studio.schemas.documents import (
    ResearchAgreement,
    ResearchContradiction,
    ResearchSourcePosition,
)

_CITATION_MARKER_RE = re.compile(r"^\[S[1-9]\d*\]$")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NUMBER_RE = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?%?\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_LONG_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(\d{4})\b",
    re.IGNORECASE,
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
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
}
_NEGATION_WORDS = {"no", "not", "never", "none", "without", "cannot", "cant"}


class ClaimVerificationError(ValueError):
    """Raised when a Research Run tries to complete with unverified claims."""


@dataclass(frozen=True)
class ComparisonSource:
    """An immutable source snapshot and the marker assigned to its claims."""

    source_id: str
    text: str
    citation_marker: str
    claims: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("comparison source_id must be a non-empty string")
        if not self.text.strip():
            raise ValueError("comparison source text must be non-empty")
        if not _CITATION_MARKER_RE.fullmatch(self.citation_marker):
            raise ValueError("comparison citation_marker must use the [S#] format")


class ResearchComparison(BaseModel):
    """Persistable comparison output used by the Research Run validation gate."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    agreements: list[ResearchAgreement] = Field(default_factory=list)
    contradictions: list[ResearchContradiction] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    verdicts: list[ClaimVerdict] = Field(default_factory=list)

    def strict_completion_ready(self) -> bool:
        """Completion needs at least one cited, fully supported checked claim."""
        return bool(self.verdicts) and all(
            verdict.status == "supported" and verdict.evidence
            for verdict in self.verdicts
        )

    def as_checkpoint(self) -> dict[str, object]:
        """Return the exact durable checkpoint shape required by the workflow."""
        return {"comparison": self.model_dump(mode="json")}


@dataclass(frozen=True)
class _VerifiedClaim:
    source: ComparisonSource
    claim: str
    verdict: ClaimVerdict
    subject: str
    predicate: str
    values: tuple[str, ...]
    negated: bool


def _canonical_token(token: str) -> str:
    token = token.lower()
    if token in _NUMBER_WORDS:
        return _NUMBER_WORDS[token]
    # This deliberately small singularizer is deterministic and avoids a model
    # dependency while grouping routine verb inflections such as sends/send.
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _normalized_dates(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for year, month, day in _ISO_DATE_RE.findall(text):
        try:
            values.append(datetime(int(year), int(month), int(day)).date().isoformat())
        except ValueError:
            continue
    for day, month, year in _LONG_DATE_RE.findall(text):
        try:
            values.append(
                datetime.strptime(f"{day} {month} {year}", "%d %B %Y")
                .date()
                .isoformat()
            )
        except ValueError:
            continue
    return tuple(dict.fromkeys(values))


def _values(text: str) -> tuple[str, ...]:
    dates = _normalized_dates(text)
    without_dates = _ISO_DATE_RE.sub(" ", text)
    without_dates = _LONG_DATE_RE.sub(" ", without_dates)
    numbers = [
        value.replace(",", "").lower() for value in _NUMBER_RE.findall(without_dates)
    ]
    number_words = [
        _NUMBER_WORDS[token]
        for token in _TOKEN_RE.findall(without_dates.lower())
        if token in _NUMBER_WORDS
    ]
    return tuple(dict.fromkeys([*dates, *numbers, *number_words]))


def _relationship(claim: str) -> tuple[str, str, bool]:
    """Create a stable claim key after removing values and polarity tokens."""
    value_free = _ISO_DATE_RE.sub(" ", claim)
    value_free = _LONG_DATE_RE.sub(" ", value_free)
    value_free = _NUMBER_RE.sub(" ", value_free)
    tokens = [
        _canonical_token(token) for token in _TOKEN_RE.findall(value_free.lower())
    ]
    negated = any(token in _NEGATION_WORDS for token in tokens)
    content = [
        token
        for token in tokens
        if token not in _STOP_WORDS
        and token not in _NEGATION_WORDS
        and token not in _NUMBER_WORDS
        and not token.isdigit()
    ]
    if not content:
        return "claim", "unspecified", negated
    # A compact subject makes comparisons readable while the full predicate
    # remains the collision-resistant grouping key.
    return content[0], " ".join(content), negated


def _claimed_statements(source: ComparisonSource) -> list[ExtractedClaim]:
    texts = source.claims or tuple(
        extracted.text for extracted in extract_material_claims(source.text)
    )
    statements: list[ExtractedClaim] = []
    for text in texts:
        # The shared extractor associates a marker with the preceding sentence,
        # so insert it before terminal punctuation rather than after it.
        statement = text.strip().rstrip(".?!")
        extracted = extract_material_claims(f"{statement} {source.citation_marker}.")
        if len(extracted) != 1:
            raise ClaimVerificationError(
                "comparison claims must contain exactly one material declaration"
            )
        statements.append(extracted[0])
    return statements


def _position(verified: _VerifiedClaim, position: str) -> ResearchSourcePosition:
    return ResearchSourcePosition(
        source_id=verified.source.source_id,
        claim=verified.claim,
        position=position,
        citations=[verified.source.citation_marker],
    )


def _gap(subject: str, predicate: str, positions: Sequence[_VerifiedClaim]) -> str:
    sources = ", ".join(item.source.source_id for item in positions)
    return f"Unresolved evidence for {subject}: {predicate} (sources: {sources})."


def compare_research_sources(sources: Sequence[ComparisonSource]) -> ResearchComparison:
    """Compare source claims only after each one passes strict citation checks.

    Statements are grouped by a deterministic value-free subject/predicate key.
    Numeric/date differences and opposite polarity become contradictions; a lone
    cited position or an ambiguous value becomes an explicit evidence gap.
    """
    if len({source.source_id for source in sources}) != len(sources):
        raise ValueError("comparison source_ids must be unique")
    if len({source.citation_marker for source in sources}) != len(sources):
        raise ValueError("comparison citation markers must be unique")

    citation_map: Mapping[str, CitationSource] = {
        source.citation_marker: CitationSource(source.source_id, source.text)
        for source in sources
    }
    verified: list[_VerifiedClaim] = []
    for source in sources:
        for statement in _claimed_statements(source):
            verdict = verify_claim(statement, citation_map)
            if verdict.status != "supported":
                raise ClaimVerificationError(
                    f"claim from {source.source_id} is {verdict.status}, not supported"
                )
            subject, predicate, negated = _relationship(statement.text)
            verified.append(
                _VerifiedClaim(
                    source=source,
                    claim=statement.text,
                    verdict=verdict,
                    subject=subject,
                    predicate=predicate,
                    values=_values(statement.text),
                    negated=negated,
                )
            )

    grouped: dict[tuple[str, str], list[_VerifiedClaim]] = defaultdict(list)
    for item in verified:
        grouped[(item.subject, item.predicate)].append(item)

    agreements: list[ResearchAgreement] = []
    contradictions: list[ResearchContradiction] = []
    gaps: list[str] = []
    for (subject, predicate), entries in grouped.items():
        by_source = {entry.source.source_id: entry for entry in entries}
        positions = list(by_source.values())
        if len(positions) < 2:
            gaps.append(_gap(subject, predicate, positions))
            continue
        values = {entry.values for entry in positions}
        negations = {entry.negated for entry in positions}
        if len(values) == 1 and len(negations) == 1:
            agreements.append(
                ResearchAgreement(
                    subject=subject,
                    predicate=predicate,
                    positions=[_position(entry, "supports") for entry in positions],
                )
            )
        elif all(entry.values for entry in positions) or len(negations) > 1:
            display_values = sorted(
                {
                    *(value for entry in positions for value in entry.values),
                    *(
                        "negated" if entry.negated else "affirmed"
                        for entry in positions
                    ),
                }
            )
            contradictions.append(
                ResearchContradiction(
                    subject=subject,
                    predicate=predicate,
                    values=display_values,
                    positions=[_position(entry, "contradicts") for entry in positions],
                )
            )
        else:
            gaps.append(_gap(subject, predicate, positions))

    return ResearchComparison(
        agreements=agreements,
        contradictions=contradictions,
        gaps=gaps,
        verdicts=[item.verdict for item in verified],
    )


def require_strict_comparison(checkpoint: Mapping[str, object]) -> ResearchComparison:
    """Reject completion when a validation stage lacks a strict receipt."""
    try:
        raw_comparison = checkpoint["comparison"]
    except KeyError as exc:
        raise ClaimVerificationError(
            "research completion requires a strict comparison receipt"
        ) from exc
    try:
        comparison = ResearchComparison.model_validate(raw_comparison)
    except Exception as exc:
        raise ClaimVerificationError(
            "research completion has an invalid comparison receipt"
        ) from exc
    if not comparison.strict_completion_ready():
        raise ClaimVerificationError(
            "research completion requires fully supported cited claims"
        )
    return comparison


__all__ = [
    "ClaimVerificationError",
    "ComparisonSource",
    "ResearchComparison",
    "compare_research_sources",
    "require_strict_comparison",
]
