"""Versioned contracts for source-grounded claim evaluation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EvidenceSourceState = Literal["current", "source_changed"]
ClaimStatus = Literal[
    "supported",
    "partial",
    "contradicted",
    "unsupported",
    "uncited",
]


class EvidenceSpan(BaseModel):
    """An immutable quote location within one evaluated source snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    source_id: str
    source_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_state: EvidenceSourceState = "current"
    offset_encoding: Literal["unicode_codepoint"] = "unicode_codepoint"
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_range(self) -> "EvidenceSpan":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class ClaimVerdict(BaseModel):
    """A versioned assessment of one claim and its supporting evidence."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    claim: str = Field(min_length=1, max_length=2000)
    status: ClaimStatus
    confidence: float = Field(ge=0, le=1)
    citation_markers: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    explanation: str = Field(max_length=1000)

    @model_validator(mode="after")
    def validate_invariants(self) -> "ClaimVerdict":
        if (
            self.status in {"supported", "partial", "contradicted"}
            and not self.evidence
        ):
            raise ValueError(f"{self.status} verdicts require evidence")
        if self.status == "uncited" and self.citation_markers:
            raise ValueError("uncited verdicts require no citation markers")

        span_keys = {
            (
                span.source_id,
                span.source_content_sha256,
                span.start,
                span.end,
            )
            for span in self.evidence
        }
        if len(span_keys) != len(self.evidence):
            raise ValueError("duplicate evidence spans are not allowed")
        return self


def hash_source_text(text: str) -> str:
    """Return the canonical SHA-256 used to bind a quote to its snapshot."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_verdict_against_snapshots(
    verdict: ClaimVerdict,
    source_snapshots: Mapping[str, str],
) -> None:
    """Require every saved excerpt to match its original source snapshot.

    Source text is intentionally not persisted with the run. This check is
    therefore performed before persistence, while the immutable evaluation
    snapshot is still available to the evaluator.
    """
    for span in verdict.evidence:
        try:
            snapshot = source_snapshots[span.source_id]
        except KeyError as exc:
            raise ValueError(
                f"missing evaluation snapshot for {span.source_id}"
            ) from exc
        if not isinstance(snapshot, str):
            raise ValueError(f"evaluation snapshot for {span.source_id} must be text")
        if hash_source_text(snapshot) != span.source_content_sha256:
            raise ValueError(
                f"evaluation snapshot hash does not match evidence span for {span.source_id}"
            )
        if span.quote != snapshot[span.start : span.end]:
            raise ValueError(
                f"evidence quote does not match the evaluation snapshot for {span.source_id}"
            )


def resolve_source_states(
    verdict: ClaimVerdict,
    current_source_texts: Mapping[str, str],
) -> ClaimVerdict:
    """Mark evidence drift without moving the saved quote or its offsets."""
    resolved_evidence: list[EvidenceSpan] = []
    for span in verdict.evidence:
        if span.source_id not in current_source_texts:
            resolved_evidence.append(span)
            continue
        current_text = current_source_texts[span.source_id]
        source_state: EvidenceSourceState = (
            "current"
            if isinstance(current_text, str)
            and hash_source_text(current_text) == span.source_content_sha256
            else "source_changed"
        )
        resolved_evidence.append(span.model_copy(update={"source_state": source_state}))
    return verdict.model_copy(update={"evidence": resolved_evidence})
