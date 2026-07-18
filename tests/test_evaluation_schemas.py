"""Contract tests for versioned evidence-evaluation payloads."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.evaluations import ClaimVerdictResponse
from open_notebook.evaluation.schemas import (
    ClaimVerdict,
    EvidenceSpan,
    hash_source_text,
    resolve_source_states,
    validate_verdict_against_snapshots,
)

SOURCE_ID = "source:evidence-contract"
SOURCE_TEXT = "Alpha evidence quote."


def _span(**overrides: object) -> EvidenceSpan:
    data: dict[str, object] = {
        "source_id": SOURCE_ID,
        "source_content_sha256": hash_source_text(SOURCE_TEXT),
        "start": 0,
        "end": 5,
        "quote": "Alpha",
    }
    data.update(overrides)
    return EvidenceSpan(**data)


def _verdict(**overrides: object) -> ClaimVerdict:
    data: dict[str, object] = {
        "claim": "Alpha is present.",
        "status": "supported",
        "confidence": 0.9,
        "citation_markers": ["[1]"],
        "evidence": [_span()],
        "explanation": "The source states Alpha.",
    }
    data.update(overrides)
    return ClaimVerdict(**data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_content_sha256": "A" * 64},
        {"end": 0},
        {"start": 5, "end": 5},
        {"quote": ""},
        {"offset_encoding": "utf8_bytes"},
    ],
)
def test_evidence_span_rejects_values_outside_the_closed_contract(overrides):
    with pytest.raises(ValidationError):
        _span(**overrides)


@pytest.mark.parametrize("status", ["supported", "partial", "contradicted"])
def test_material_verdicts_require_evidence(status):
    with pytest.raises(ValidationError, match="require evidence"):
        _verdict(status=status, evidence=[])


def test_uncited_verdict_rejects_citation_markers():
    with pytest.raises(
        ValidationError, match="uncited verdicts require no citation markers"
    ):
        _verdict(status="uncited", citation_markers=["[1]"], evidence=[])


def test_verdict_rejects_duplicate_evidence_spans():
    span = _span()
    with pytest.raises(ValidationError, match="duplicate evidence spans"):
        _verdict(evidence=[span, span])


def test_verdict_rejects_a_quote_that_does_not_match_its_hashed_snapshot():
    verdict = _verdict(evidence=[_span(quote="Wrong")])

    with pytest.raises(ValueError, match="does not match the evaluation snapshot"):
        validate_verdict_against_snapshots(verdict, {SOURCE_ID: SOURCE_TEXT})


def test_verdict_rejects_a_snapshot_whose_hash_does_not_match_the_span():
    verdict = _verdict()

    with pytest.raises(ValueError, match="hash does not match"):
        validate_verdict_against_snapshots(verdict, {SOURCE_ID: "Changed source text."})


def test_resolve_source_states_preserves_the_saved_quote_when_source_changed():
    verdict = _verdict()

    resolved = resolve_source_states(
        verdict,
        {SOURCE_ID: "Completely replaced source text."},
    )

    assert resolved.evidence[0].source_state == "source_changed"
    assert resolved.evidence[0].quote == "Alpha"
    assert resolved.evidence[0].start == 0
    assert resolved.evidence[0].end == 5


def test_api_response_contract_exposes_current_and_changed_source_states():
    current = ClaimVerdictResponse(
        id="claim_verdict:current",
        evaluation_run_id="evaluation_run:one",
        **_verdict().model_dump(mode="json"),
    )
    changed = ClaimVerdictResponse(
        id="claim_verdict:changed",
        evaluation_run_id="evaluation_run:one",
        **_verdict(evidence=[_span(source_state="source_changed")]).model_dump(
            mode="json"
        ),
    )

    assert current.evidence[0].source_state == "current"
    assert changed.evidence[0].source_state == "source_changed"
