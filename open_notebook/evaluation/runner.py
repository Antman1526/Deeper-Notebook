"""Deterministic scoring for the immutable research-quality corpus."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol

from open_notebook.evaluation.datasets import (
    CaseStatus,
    CorpusCase,
    ExpectedSpan,
    GoldenCorpus,
)

PredictionStatus = Literal[
    "supported", "partial", "contradicted", "unsupported", "uncited", "abstained"
]
MetricState = Literal["ok", "not_applicable"]


class ThresholdError(ValueError):
    """Raised when a threshold file is unknown or malformed."""


@dataclass(frozen=True)
class PredictedSpan:
    source_id: str
    source_content_sha256: str
    start: int
    end: int
    quote: str

    @classmethod
    def from_expected(cls, span: ExpectedSpan) -> "PredictedSpan":
        return cls(**asdict(span))

    def identity(self) -> tuple[str, str, int, int, str]:
        return (
            self.source_id,
            self.source_content_sha256,
            self.start,
            self.end,
            self.quote,
        )


@dataclass(frozen=True)
class EvaluationPrediction:
    status: PredictionStatus
    evidence: tuple[PredictedSpan, ...] = ()
    schema_valid: bool = True
    repaired_schema_valid: bool = False
    latency_ms: float = 0.0


class EvaluationEvaluator(Protocol):
    def evaluate(
        self, case: CorpusCase, *, model_id: str, temperature: float
    ) -> EvaluationPrediction: ...


class DeterministicVerifier:
    """Offline fixture verifier used to prove corpus and runner integrity."""

    def evaluate(
        self, case: CorpusCase, *, model_id: str, temperature: float
    ) -> EvaluationPrediction:
        del model_id
        if temperature != 0.0:
            raise ValueError("evaluation temperature must be zero")
        claim = case.expected_claims[0]
        return EvaluationPrediction(
            status=claim.status,
            evidence=tuple(
                PredictedSpan.from_expected(span) for span in claim.evidence
            ),
            schema_valid=True,
            latency_ms=0.0,
        )


@dataclass(frozen=True)
class MetricValue:
    value: float | None
    numerator: int
    denominator: int
    state: MetricState

    @classmethod
    def from_fraction(cls, numerator: int, denominator: int) -> "MetricValue":
        if denominator == 0:
            return cls(
                value=None,
                numerator=numerator,
                denominator=denominator,
                state="not_applicable",
            )
        return cls(
            value=numerator / denominator,
            numerator=numerator,
            denominator=denominator,
            state="ok",
        )


@dataclass(frozen=True)
class CaseDiagnostic:
    case_id: str
    category: str
    claim_id: str
    expected_status: CaseStatus
    predicted_status: PredictionStatus
    status_correct: bool
    expected_span_count: int
    matched_span_count: int
    schema_success: bool
    latency_ms: float


@dataclass(frozen=True)
class EvaluationReport:
    corpus_version: str
    model_id: str
    temperature: float
    metrics: dict[str, MetricValue]
    average_latency_ms: float
    macro_score: float | None
    diagnostics: tuple[CaseDiagnostic, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "corpus_version": self.corpus_version,
            "model_id": self.model_id,
            "temperature": self.temperature,
            "metrics": {key: asdict(value) for key, value in self.metrics.items()},
            "average_latency_ms": self.average_latency_ms,
            "macro_score": self.macro_score,
            "diagnostics": [asdict(diagnostic) for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True)
class MetricThreshold:
    name: str
    operator: Literal[">=", "<="]
    value: float


@dataclass(frozen=True)
class EvaluationThresholds:
    threshold_version: str
    corpus_version: str
    metrics: tuple[MetricThreshold, ...]


def run_evaluation(
    corpus: GoldenCorpus,
    *,
    evaluator: EvaluationEvaluator | None = None,
    model_id: str = "deterministic",
) -> EvaluationReport:
    """Score one result per material claim, always at temperature zero."""
    active_evaluator = evaluator or DeterministicVerifier()
    if evaluator is None and model_id != "deterministic":
        raise ValueError("a named model requires an evaluator adapter")
    diagnostics: list[CaseDiagnostic] = []
    predicted_supported = correct_supported = expected_supported = 0
    expected_non_supported = unsupported_escapes = 0
    expected_spans = matched_spans = 0
    schema_attempts = schema_successes = 0
    total_latency_ms = 0.0

    for case in corpus.cases:
        for claim in case.expected_claims:
            prediction = active_evaluator.evaluate(
                case, model_id=model_id, temperature=0.0
            )
            prediction = _normalize_prediction(prediction)
            expected_is_supported = claim.status == "supported"
            predicted_is_supported = prediction.status == "supported"
            expected_supported += int(expected_is_supported)
            predicted_supported += int(predicted_is_supported)
            correct_supported += int(expected_is_supported and predicted_is_supported)
            expected_non_supported += int(not expected_is_supported)
            unsupported_escapes += int(
                not expected_is_supported and predicted_is_supported
            )
            expected_span_ids = {span_identity(span) for span in claim.evidence}
            predicted_span_ids = {span.identity() for span in prediction.evidence}
            expected_spans += len(expected_span_ids)
            matched = len(expected_span_ids & predicted_span_ids)
            matched_spans += matched
            success = prediction.schema_valid or prediction.repaired_schema_valid
            schema_attempts += 1
            schema_successes += int(success)
            total_latency_ms += prediction.latency_ms
            diagnostics.append(
                CaseDiagnostic(
                    case_id=case.id,
                    category=case.category,
                    claim_id=claim.id,
                    expected_status=claim.status,
                    predicted_status=prediction.status,
                    status_correct=claim.status == prediction.status,
                    expected_span_count=len(expected_span_ids),
                    matched_span_count=matched,
                    schema_success=success,
                    latency_ms=prediction.latency_ms,
                )
            )

    metrics = {
        "supported_precision": MetricValue.from_fraction(
            correct_supported, predicted_supported
        ),
        "supported_recall": MetricValue.from_fraction(
            correct_supported, expected_supported
        ),
        "unsupported_escape_rate": MetricValue.from_fraction(
            unsupported_escapes, expected_non_supported
        ),
        "citation_location_rate": MetricValue.from_fraction(
            matched_spans, expected_spans
        ),
        "schema_success_rate": MetricValue.from_fraction(
            schema_successes, schema_attempts
        ),
    }
    # Escape rate is a failure rate; invert it when forming the informational macro.
    macro_parts = [
        1.0 - metrics["unsupported_escape_rate"].value
        if metrics["unsupported_escape_rate"].value is not None
        else None,
        metrics["supported_precision"].value,
        metrics["supported_recall"].value,
        metrics["citation_location_rate"].value,
        metrics["schema_success_rate"].value,
    ]
    usable_macro_parts = [value for value in macro_parts if value is not None]
    return EvaluationReport(
        corpus_version=corpus.manifest.corpus_version,
        model_id=model_id,
        temperature=0.0,
        metrics=metrics,
        average_latency_ms=total_latency_ms / len(diagnostics) if diagnostics else 0.0,
        macro_score=sum(usable_macro_parts) / len(usable_macro_parts)
        if usable_macro_parts
        else None,
        diagnostics=tuple(diagnostics),
    )


def span_identity(span: ExpectedSpan) -> tuple[str, str, int, int, str]:
    return (
        span.source_id,
        span.source_content_sha256,
        span.start,
        span.end,
        span.quote,
    )


def _normalize_prediction(prediction: EvaluationPrediction) -> EvaluationPrediction:
    if not isinstance(prediction, EvaluationPrediction):
        raise TypeError("evaluation adapters must return EvaluationPrediction")
    if prediction.status not in {
        "supported",
        "partial",
        "contradicted",
        "unsupported",
        "uncited",
        "abstained",
    }:
        raise ValueError("evaluation adapter returned an unknown status")
    if prediction.latency_ms < 0:
        raise ValueError("evaluation adapter returned a negative latency")
    return prediction


def load_thresholds(path: Path, *, corpus_version: str) -> EvaluationThresholds:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ThresholdError("threshold file is not valid JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ThresholdError("threshold schema version is unsupported")
    if raw.get("threshold_version") != "v1":
        raise ThresholdError("unknown threshold version")
    if raw.get("corpus_version") != corpus_version:
        raise ThresholdError("threshold corpus version does not match")
    metrics_raw = raw.get("metrics")
    if not isinstance(metrics_raw, dict):
        raise ThresholdError("threshold metrics must be an object")
    expected_names = {
        "supported_precision",
        "supported_recall",
        "unsupported_escape_rate",
        "citation_location_rate",
        "schema_success_rate",
    }
    if set(metrics_raw) != expected_names:
        raise ThresholdError("threshold metrics are incomplete or unknown")
    metrics: list[MetricThreshold] = []
    for name in sorted(metrics_raw):
        item = metrics_raw[name]
        if not isinstance(item, dict) or item.get("operator") not in {">=", "<="}:
            raise ThresholdError(f"threshold for {name} is invalid")
        value = item.get("value")
        if not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
            raise ThresholdError(f"threshold value for {name} is invalid")
        metrics.append(MetricThreshold(name, item["operator"], float(value)))
    return EvaluationThresholds("v1", corpus_version, tuple(metrics))


def enforce_thresholds(
    report: EvaluationReport, thresholds: EvaluationThresholds
) -> list[str]:
    """Return failed release-gate metric names without suppressing N/A metrics."""
    if report.corpus_version != thresholds.corpus_version:
        raise ThresholdError("report corpus version does not match thresholds")
    failures: list[str] = []
    for threshold in thresholds.metrics:
        metric = report.metrics.get(threshold.name)
        if metric is None or metric.value is None:
            failures.append(threshold.name)
            continue
        if threshold.operator == ">=" and metric.value < threshold.value:
            failures.append(threshold.name)
        if threshold.operator == "<=" and metric.value > threshold.value:
            failures.append(threshold.name)
    return failures


def render_markdown_report(report: EvaluationReport) -> str:
    lines = [
        "# Research Quality Evaluation",
        "",
        f"- Corpus: `{report.corpus_version}`",
        f"- Model: `{report.model_id}`",
        f"- Temperature: `{report.temperature:.1f}`",
        f"- Average latency: `{report.average_latency_ms:.2f} ms`",
        f"- Informational macro score: `{_format_value(report.macro_score)}`",
        "",
        "## Release Metrics",
        "",
        "| Metric | Value | Numerator | Denominator | State |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for name, metric in report.metrics.items():
        lines.append(
            f"| {name} | {_format_value(metric.value)} | {metric.numerator} | "
            f"{metric.denominator} | {metric.state} |"
        )
    lines.extend(
        [
            "",
            "## Per-case diagnostics",
            "",
            "| Case | Category | Expected | Predicted | Status | Spans | Schema | Latency |",
            "| --- | --- | --- | --- | --- | --- | --- | ---: |",
        ]
    )
    for diagnostic in report.diagnostics:
        lines.append(
            f"| {diagnostic.case_id} | {diagnostic.category} | {diagnostic.expected_status} | "
            f"{diagnostic.predicted_status} | {'pass' if diagnostic.status_correct else 'fail'} | "
            f"{diagnostic.matched_span_count}/{diagnostic.expected_span_count} | "
            f"{'pass' if diagnostic.schema_success else 'fail'} | {diagnostic.latency_ms:.2f} ms |"
        )
    return "\n".join(lines) + "\n"


def _format_value(value: float | None) -> str:
    return "not_applicable" if value is None else f"{value:.4f}"


def write_report(
    report: EvaluationReport, *, json_path: Path, markdown_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
