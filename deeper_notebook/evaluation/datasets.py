"""Immutable, synthetic research-quality corpus loading and validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

CaseStatus = Literal["supported", "partial", "contradicted", "unsupported", "uncited"]
_V1_CATEGORY_COUNTS = {
    "contradiction": 6,
    "missing_citation": 6,
    "not_in_sources": 6,
    "numeric_mismatch": 6,
    "partial_support": 6,
    "prompt_injection": 6,
    "quote_mismatch": 6,
    "supported_multi_source": 6,
    "supported_single_source": 6,
    "temporal_mismatch": 6,
    "wrong_source": 6,
}


class DatasetIntegrityError(ValueError):
    """Raised when an evaluation fixture is malformed or has been altered."""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonicalize_corpus_bytes(raw_bytes: bytes) -> bytes:
    """Hash JSONL fixtures with LF line endings on every supported platform."""
    if b"\r" in raw_bytes.replace(b"\r\n", b""):
        raise DatasetIntegrityError("corpus contains an invalid carriage return")
    return raw_bytes.replace(b"\r\n", b"\n")


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DatasetIntegrityError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class SourceSnapshot:
    id: str
    text: str
    content_sha256: str

    @classmethod
    def from_text(cls, source_id: str, text: str) -> "SourceSnapshot":
        return cls(id=source_id, text=text, content_sha256=_sha256_text(text))

    @classmethod
    def from_dict(cls, raw: object, *, case_id: str) -> "SourceSnapshot":
        if not isinstance(raw, dict):
            raise DatasetIntegrityError(f"{case_id}: source must be an object")
        source = cls(
            id=_require_string(raw.get("id"), f"{case_id}: source.id"),
            text=_require_string(raw.get("text"), f"{case_id}: source.text"),
            content_sha256=_require_string(
                raw.get("content_sha256"), f"{case_id}: source.content_sha256"
            ),
        )
        if source.content_sha256 != _sha256_text(source.text):
            raise DatasetIntegrityError(f"{case_id}: source hash does not match text")
        return source


@dataclass(frozen=True)
class ExpectedSpan:
    source_id: str
    source_content_sha256: str
    start: int
    end: int
    quote: str

    @classmethod
    def from_dict(cls, raw: object, *, case_id: str) -> "ExpectedSpan":
        if not isinstance(raw, dict):
            raise DatasetIntegrityError(f"{case_id}: evidence span must be an object")
        start, end = raw.get("start"), raw.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or end <= start:
            raise DatasetIntegrityError(f"{case_id}: evidence range is invalid")
        return cls(
            source_id=_require_string(raw.get("source_id"), f"{case_id}: source_id"),
            source_content_sha256=_require_string(
                raw.get("source_content_sha256"), f"{case_id}: source_content_sha256"
            ),
            start=start,
            end=end,
            quote=_require_string(raw.get("quote"), f"{case_id}: quote"),
        )


@dataclass(frozen=True)
class ExpectedClaim:
    id: str
    text: str
    status: CaseStatus
    evidence: tuple[ExpectedSpan, ...]

    @classmethod
    def from_dict(cls, raw: object, *, case_id: str) -> "ExpectedClaim":
        if not isinstance(raw, dict):
            raise DatasetIntegrityError(f"{case_id}: expected claim must be an object")
        status = raw.get("status")
        if status not in {
            "supported",
            "partial",
            "contradicted",
            "unsupported",
            "uncited",
        }:
            raise DatasetIntegrityError(f"{case_id}: expected status is invalid")
        evidence = tuple(
            ExpectedSpan.from_dict(span, case_id=case_id)
            for span in raw.get("evidence", [])
        )
        if status in {"supported", "partial", "contradicted"} and not evidence:
            raise DatasetIntegrityError(f"{case_id}: {status} claims need evidence")
        if status in {"unsupported", "uncited"} and evidence:
            raise DatasetIntegrityError(
                f"{case_id}: {status} claims cannot have evidence"
            )
        return cls(
            id=_require_string(raw.get("id"), f"{case_id}: claim.id"),
            text=_require_string(raw.get("text"), f"{case_id}: claim.text"),
            status=status,
            evidence=evidence,
        )


@dataclass(frozen=True)
class CorpusCase:
    id: str
    category: str
    prompt: str
    candidate_answer: str
    sources: tuple[SourceSnapshot, ...]
    expected_claims: tuple[ExpectedClaim, ...]

    @classmethod
    def from_dict(cls, raw: object) -> "CorpusCase":
        if not isinstance(raw, dict):
            raise DatasetIntegrityError("corpus entry must be an object")
        case_id = _require_string(raw.get("id"), "case.id")
        if raw.get("schema_version") != 1:
            raise DatasetIntegrityError(f"{case_id}: unsupported case schema")
        sources = tuple(
            SourceSnapshot.from_dict(source, case_id=case_id)
            for source in raw.get("sources", [])
        )
        if not sources:
            raise DatasetIntegrityError(f"{case_id}: requires at least one source")
        source_by_id = {source.id: source for source in sources}
        claims = tuple(
            ExpectedClaim.from_dict(claim, case_id=case_id)
            for claim in raw.get("expected_claims", [])
        )
        if not claims:
            raise DatasetIntegrityError(f"{case_id}: requires expected claims")
        for claim in claims:
            for span in claim.evidence:
                source = source_by_id.get(span.source_id)
                if source is None:
                    raise DatasetIntegrityError(
                        f"{case_id}: evidence references an unknown source"
                    )
                if source.content_sha256 != span.source_content_sha256:
                    raise DatasetIntegrityError(
                        f"{case_id}: evidence source hash is invalid"
                    )
                if source.text[span.start : span.end] != span.quote:
                    raise DatasetIntegrityError(
                        f"{case_id}: evidence quote does not match source"
                    )
        return cls(
            id=case_id,
            category=_require_string(raw.get("category"), f"{case_id}: category"),
            prompt=_require_string(raw.get("prompt"), f"{case_id}: prompt"),
            candidate_answer=_require_string(
                raw.get("candidate_answer"), f"{case_id}: candidate_answer"
            ),
            sources=sources,
            expected_claims=claims,
        )


@dataclass(frozen=True)
class CorpusManifest:
    corpus_version: str
    case_count: int
    category_counts: dict[str, int]
    corpus_sha256: str
    material_claim_ids: tuple[str, ...]


@dataclass(frozen=True)
class GoldenCorpus:
    cases: tuple[CorpusCase, ...]
    manifest: CorpusManifest


def corpus_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[2]
    fixture_root = root / "tests" / "fixtures" / "evaluation"
    return (
        fixture_root / "corpus-v1.jsonl",
        fixture_root / "corpus-v1-manifest.json",
        fixture_root / "evaluation-thresholds-v1.json",
    )


def load_golden_corpus(corpus_path: Path, manifest_path: Path) -> GoldenCorpus:
    """Load v1 only after validating every immutable fixture invariant."""
    raw_bytes = _canonicalize_corpus_bytes(corpus_path.read_bytes())
    try:
        manifest_raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetIntegrityError("manifest is not valid JSON") from exc
    if not isinstance(manifest_raw, dict) or manifest_raw.get("schema_version") != 1:
        raise DatasetIntegrityError("manifest schema version is unsupported")
    corpus_version = manifest_raw.get("corpus_version")
    if corpus_version != "v1":
        raise DatasetIntegrityError("unknown corpus version")
    actual_hash = hashlib.sha256(raw_bytes).hexdigest()
    expected_hash = _require_string(
        manifest_raw.get("corpus_sha256"), "manifest.corpus_sha256"
    )
    if actual_hash != expected_hash:
        raise DatasetIntegrityError("corpus SHA-256 does not match manifest")

    cases: list[CorpusCase] = []
    for line_number, line in enumerate(raw_bytes.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            raise DatasetIntegrityError(f"corpus line {line_number} must not be blank")
        try:
            cases.append(CorpusCase.from_dict(json.loads(line)))
        except json.JSONDecodeError as exc:
            raise DatasetIntegrityError(
                f"corpus line {line_number} is not JSON"
            ) from exc
    case_ids = [case.id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise DatasetIntegrityError("corpus case IDs must be unique")
    category_counts = {
        str(key): int(value)
        for key, value in manifest_raw.get("category_counts", {}).items()
    }
    observed_counts: dict[str, int] = {}
    for case in cases:
        observed_counts[case.category] = observed_counts.get(case.category, 0) + 1
    if (
        len(cases) != manifest_raw.get("case_count")
        or observed_counts != category_counts
    ):
        raise DatasetIntegrityError(
            "manifest case or category counts do not match corpus"
        )
    if len(cases) != 66 or category_counts != _V1_CATEGORY_COUNTS:
        raise DatasetIntegrityError(
            "v1 requires exactly six cases in eleven categories"
        )
    material_claim_ids = tuple(
        str(value) for value in manifest_raw.get("material_claim_ids", [])
    )
    observed_claim_ids = tuple(
        claim.id for case in cases for claim in case.expected_claims
    )
    if set(material_claim_ids) != set(observed_claim_ids) or len(
        material_claim_ids
    ) != len(observed_claim_ids):
        raise DatasetIntegrityError("manifest material claim IDs do not match corpus")
    claims = tuple(claim for case in cases for claim in case.expected_claims)
    if not any(claim.status == "supported" for claim in claims):
        raise DatasetIntegrityError("v1 lacks a supported-claim denominator")
    if not any(claim.status != "supported" for claim in claims):
        raise DatasetIntegrityError("v1 lacks a non-supported-claim denominator")
    if not any(claim.evidence for claim in claims):
        raise DatasetIntegrityError("v1 lacks a citation-location denominator")
    return GoldenCorpus(
        cases=tuple(cases),
        manifest=CorpusManifest(
            corpus_version=corpus_version,
            case_count=len(cases),
            category_counts=category_counts,
            corpus_sha256=actual_hash,
            material_claim_ids=material_claim_ids,
        ),
    )
