"""Regression coverage for the immutable v1 research-quality corpus."""

from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from deeper_notebook.evaluation.datasets import (
    DatasetIntegrityError,
    ExpectedClaim,
    GoldenCorpus,
    SourceSnapshot,
    corpus_paths,
    load_golden_corpus,
)
from deeper_notebook.evaluation.runner import (
    DeterministicVerifier,
    EvaluationPrediction,
    PredictedSpan,
    ThresholdError,
    enforce_thresholds,
    load_thresholds,
    render_markdown_report,
    run_evaluation,
)


def _corpus() -> GoldenCorpus:
    corpus, manifest, _ = corpus_paths()
    return load_golden_corpus(corpus, manifest)


def test_v1_corpus_has_immutable_66_case_shape_and_release_denominators():
    corpus = _corpus()

    assert len(corpus.cases) == 66
    assert corpus.manifest.case_count == 66
    assert corpus.manifest.category_counts == {
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
    assert len(corpus.manifest.material_claim_ids) == 66
    assert all(case.expected_claims for case in corpus.cases)


def test_loader_refuses_a_manifest_checksum_mismatch(tmp_path: Path):
    corpus_path, manifest_path, _ = corpus_paths()
    copied_corpus = tmp_path / "corpus.jsonl"
    copied_manifest = tmp_path / "manifest.json"
    copied_corpus.write_text(
        corpus_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    copied_manifest.write_text(
        manifest_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    with pytest.raises(DatasetIntegrityError, match="SHA-256"):
        load_golden_corpus(copied_corpus, copied_manifest)


def test_loader_uses_canonical_lf_bytes_for_windows_checkouts(tmp_path: Path):
    corpus_path, manifest_path, _ = corpus_paths()
    copied_corpus = tmp_path / "corpus.jsonl"
    copied_manifest = tmp_path / "manifest.json"
    canonical_lf = corpus_path.read_bytes().replace(b"\r\n", b"\n")
    copied_corpus.write_bytes(canonical_lf.replace(b"\n", b"\r\n"))
    copied_manifest.write_text(
        manifest_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    assert len(load_golden_corpus(copied_corpus, copied_manifest).cases) == 66


def test_loader_refuses_a_rehashed_corpus_that_removes_a_release_denominator(
    tmp_path: Path,
):
    corpus_path, manifest_path, _ = corpus_paths()
    rows = [
        json.loads(line)
        for line in corpus_path.read_text(encoding="utf-8").splitlines()
    ]
    for row in rows:
        row["expected_claims"][0]["status"] = "unsupported"
        row["expected_claims"][0]["evidence"] = []
    contents = "\n".join(json.dumps(row) for row in rows) + "\n"
    altered_corpus = tmp_path / "corpus.jsonl"
    altered_manifest = tmp_path / "manifest.json"
    altered_corpus.write_text(contents, encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["corpus_sha256"] = sha256(contents.encode("utf-8")).hexdigest()
    altered_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetIntegrityError, match="supported-claim denominator"):
        load_golden_corpus(altered_corpus, altered_manifest)


def test_deterministic_verifier_produces_reproducible_passing_release_metrics():
    corpus = _corpus()

    first = run_evaluation(corpus, evaluator=DeterministicVerifier())
    second = run_evaluation(corpus, evaluator=DeterministicVerifier())

    assert first.to_dict() == second.to_dict()
    assert first.metrics["supported_precision"].value == 1.0
    assert first.metrics["supported_recall"].value == 1.0
    assert first.metrics["unsupported_escape_rate"].value == 0.0
    assert first.metrics["citation_location_rate"].value == 1.0
    assert first.metrics["schema_success_rate"].value == 1.0
    assert first.average_latency_ms == 0.0
    assert len(first.diagnostics) == 66
    assert "Per-case diagnostics" in render_markdown_report(first)


def test_runner_passes_model_identifier_and_forces_temperature_zero():
    class RecordingEvaluator:
        def __init__(self) -> None:
            self.calls: list[tuple[str, float]] = []

        def evaluate(self, case, *, model_id: str, temperature: float):
            self.calls.append((model_id, temperature))
            claim = case.expected_claims[0]
            return EvaluationPrediction(
                status=claim.status,
                evidence=tuple(
                    PredictedSpan.from_expected(span) for span in claim.evidence
                ),
                schema_valid=True,
                latency_ms=7,
            )

    evaluator = RecordingEvaluator()
    report = run_evaluation(_corpus(), evaluator=evaluator, model_id="model:local")

    assert report.model_id == "model:local"
    assert len(evaluator.calls) == 66
    assert set(evaluator.calls) == {("model:local", 0.0)}


def test_non_supported_predictions_are_not_counted_as_supported_and_escape_rate_is_honest():
    corpus = _corpus()

    class EscapingEvaluator:
        def evaluate(self, case, *, model_id: str, temperature: float):
            claim = case.expected_claims[0]
            return EvaluationPrediction(
                status="supported",
                evidence=tuple(
                    PredictedSpan.from_expected(span) for span in claim.evidence
                ),
                schema_valid=True,
            )

    report = run_evaluation(
        corpus, evaluator=EscapingEvaluator(), model_id="model:test"
    )

    assert report.metrics["supported_precision"].value == pytest.approx(12 / 66)
    assert report.metrics["supported_recall"].value == 1.0
    assert report.metrics["unsupported_escape_rate"].value == 1.0


def test_zero_denominator_is_not_applicable_and_excluded_from_macro_score():
    source = SourceSnapshot.from_text("source:one", "A factual source.")
    claim = ExpectedClaim(
        id="claim:one",
        text="A factual source exists.",
        status="supported",
        evidence=(),
    )
    tiny = GoldenCorpus(
        cases=(
            replace(
                _corpus().cases[0],
                id="ev1-tiny-01",
                category="supported_single_source",
                sources=(source,),
                expected_claims=(claim,),
            ),
        ),
        manifest=replace(_corpus().manifest, material_claim_ids=("claim:one",)),
    )
    report = run_evaluation(tiny, evaluator=DeterministicVerifier())

    assert report.metrics["unsupported_escape_rate"].value is None
    assert report.metrics["unsupported_escape_rate"].state == "not_applicable"
    assert report.metrics["citation_location_rate"].value is None
    assert report.macro_score == 1.0


def test_threshold_loader_and_gate_reject_unknown_versions_and_failing_metrics(
    tmp_path: Path,
):
    _, _, thresholds_path = corpus_paths()
    thresholds = load_thresholds(thresholds_path, corpus_version="v1")
    assert enforce_thresholds(run_evaluation(_corpus()), thresholds) == []

    bad = json.loads(thresholds_path.read_text(encoding="utf-8"))
    bad["threshold_version"] = "future"
    bad_path = tmp_path / "unknown.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ThresholdError, match="unknown threshold version"):
        load_thresholds(bad_path, corpus_version="v1")

    failing = replace(
        run_evaluation(_corpus()),
        metrics={
            **run_evaluation(_corpus()).metrics,
            "supported_precision": replace(
                run_evaluation(_corpus()).metrics["supported_precision"], value=0.0
            ),
        },
    )
    assert "supported_precision" in enforce_thresholds(failing, thresholds)
