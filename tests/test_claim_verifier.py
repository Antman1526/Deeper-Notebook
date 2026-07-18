"""Claim-to-citation verification tests for the evidence evaluation contract."""

import pytest

from open_notebook.evaluation.claims import extract_material_claims
from open_notebook.evaluation.schemas import (
    hash_source_text,
    resolve_source_states,
    validate_verdict_against_snapshots,
)
from open_notebook.evaluation.verifier import CitationSource, verify_claim
from open_notebook.utils.citation_offsets import slice_passage


def _source(source_id: str, text: str) -> CitationSource:
    return CitationSource(source_id=source_id, text=text)


def test_marks_exactly_supported_claim_with_exact_quote_slice() -> None:
    source_text = "The launch completed on 12 March 2026 after a final audit."
    claim = extract_material_claims("The launch completed on 12 March 2026 [S1].")[0]

    verdict = verify_claim(claim, {"[S1]": _source("source:release", source_text)})

    assert verdict.status == "supported"
    assert (
        verdict.evidence[0].quote
        == source_text[verdict.evidence[0].start : verdict.evidence[0].end]
    )
    assert verdict.evidence[0].source_content_sha256 == hash_source_text(source_text)
    validate_verdict_against_snapshots(verdict, {"source:release": source_text})


def test_marks_numeric_mismatch_as_contradicted() -> None:
    claim = extract_material_claims("The import retries three times [S1].")[0]

    verdict = verify_claim(
        claim,
        {
            "[S1]": _source(
                "source:guide", "The import retries two times after failure."
            )
        },
    )

    assert verdict.status == "contradicted"
    assert verdict.evidence


def test_marks_negated_claim_as_contradicted() -> None:
    claim = extract_material_claims("The desktop app sends telemetry [S1].")[0]

    verdict = verify_claim(
        claim,
        {"[S1]": _source("source:privacy", "The desktop app does not send telemetry.")},
    )

    assert verdict.status == "contradicted"


def test_requires_markers_to_exist_in_the_selected_response_map() -> None:
    claim = extract_material_claims("The import retries three times [S9].")[0]

    with pytest.raises(ValueError, match="not in the response citation map"):
        verify_claim(
            claim, {"[S1]": _source("source:guide", "The import retries three times.")}
        )


def test_uncited_claim_has_no_evidence_or_markers() -> None:
    claim = extract_material_claims("The import retries three times.")[0]

    verdict = verify_claim(
        claim, {"[S1]": _source("source:guide", "The import retries three times.")}
    )

    assert verdict.status == "uncited"
    assert verdict.citation_markers == []
    assert verdict.evidence == []


def test_rejects_corrupted_source_content_before_creating_evidence() -> None:
    with pytest.raises(ValueError, match="does not match its text"):
        CitationSource(
            source_id="source:guide",
            text="The import retries three times.",
            source_content_sha256="0" * 64,
        )


def test_source_drift_is_visible_without_relocating_the_saved_quote() -> None:
    source_text = "The launch completed on 12 March 2026 after a final audit."
    claim = extract_material_claims("The launch completed on 12 March 2026 [S1].")[0]
    verdict = verify_claim(claim, {"[S1]": _source("source:release", source_text)})

    resolved = resolve_source_states(
        verdict,
        {"source:release": "Updated source text with a different hash."},
    )

    assert resolved.evidence[0].source_state == "source_changed"
    assert resolved.evidence[0].quote == verdict.evidence[0].quote
    assert resolved.evidence[0].start == verdict.evidence[0].start


def test_rejects_corrupted_unicode_codepoint_offsets() -> None:
    with pytest.raises(ValueError, match="outside the source text"):
        slice_passage("Cafe \u2615", 0, 99)
