"""Deterministic quality probes for local language-model benchmarks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QualityMeasurement:
    """Raw, task-derived quality signals persisted with a benchmark result."""

    schema_valid: bool | None = None
    citation_fidelity: bool | None = None
    instruction_following: bool | None = None
    tool_calling: bool | None = None
    context_recall: bool | None = None
    answer_correctness: bool | None = None
    refusal_when_evidence_absent: bool | None = None


@dataclass(frozen=True)
class QualityTask:
    role: str
    prompt: str
    minimum_context_tokens: int
    requires_structured_output: bool = False
    required_json_fields: tuple[str, ...] = ()
    expected_citation: str | None = None
    instruction_terms: tuple[str, ...] = ()
    expected_tool_name: str | None = None
    context_marker: str | None = None
    correctness_terms: tuple[str, ...] = ()
    requires_evidence_refusal: bool = False


@dataclass(frozen=True)
class QualityTaskGate:
    allowed: bool
    reason: str | None = None


_SOURCE_CONTEXT = "ORCHID-17"
_SOURCE_CITATION = "[source:brief]"

_QUALITY_TASKS: dict[str, QualityTask] = {
    "chat": QualityTask(
        role="chat",
        minimum_context_tokens=2048,
        prompt=(
            "Use only this evidence: the archive is local and its key is ORCHID-17. "
            "Answer that the archive is local, include [source:brief], mention ORCHID-17, "
            "and say 'insufficient evidence' for claims outside the evidence."
        ),
        expected_citation=_SOURCE_CITATION,
        instruction_terms=("local",),
        context_marker=_SOURCE_CONTEXT,
        correctness_terms=("archive", "local"),
        requires_evidence_refusal=True,
    ),
    "source_synthesis": QualityTask(
        role="source_synthesis",
        minimum_context_tokens=8192,
        requires_structured_output=True,
        required_json_fields=("answer", "citation", "context", "refusal"),
        prompt=(
            "Use only this evidence: the archive is local and its key is ORCHID-17. "
            "Return JSON with answer, citation, context, and refusal. The answer must say the "
            "archive is local; citation must be [source:brief]; context must be ORCHID-17; "
            "refusal must say insufficient evidence for any other claim."
        ),
        expected_citation=_SOURCE_CITATION,
        instruction_terms=("answer", "citation", "context", "refusal"),
        context_marker=_SOURCE_CONTEXT,
        correctness_terms=("archive", "local"),
        requires_evidence_refusal=True,
    ),
    "coding_research": QualityTask(
        role="coding_research",
        minimum_context_tokens=8192,
        requires_structured_output=True,
        required_json_fields=("answer", "context"),
        prompt=(
            "Use the lookup_evidence tool before answering. The evidence says the archive is "
            "local and its key is ORCHID-17. Return JSON with answer and context; the answer "
            "must say the archive is local and context must be ORCHID-17."
        ),
        instruction_terms=("answer", "context"),
        expected_tool_name="lookup_evidence",
        context_marker=_SOURCE_CONTEXT,
        correctness_terms=("archive", "local"),
    ),
    "study_fast": QualityTask(
        role="study_fast",
        minimum_context_tokens=4096,
        requires_structured_output=True,
        required_json_fields=("flashcards",),
        prompt=(
            "Return JSON with exactly a flashcards field containing three concise flashcards "
            "about retrieval augmented generation."
        ),
        instruction_terms=("flashcards",),
        correctness_terms=("retrieval",),
    ),
}


def quality_task_for_role(role: str) -> QualityTask:
    """Return the deterministic probe for a benchmark role."""
    task = _QUALITY_TASKS.get(role)
    if task is not None:
        return task
    return QualityTask(
        role=role,
        minimum_context_tokens=0,
        prompt="Answer briefly: why does local-first AI matter for private notebooks?",
        correctness_terms=("local",),
    )


def gate_quality_task(
    task: QualityTask,
    local_model: object,
    registered_model: object,
) -> QualityTaskGate:
    """Reject benchmarks that cannot exercise the task they claim to measure."""
    metadata = getattr(local_model, "metadata", None)
    context_length = getattr(metadata, "context_length", None)
    if isinstance(context_length, int) and context_length < task.minimum_context_tokens:
        return QualityTaskGate(
            allowed=False,
            reason=(
                f"Context window ({context_length}) is below this task's required "
                f"{task.minimum_context_tokens} tokens."
            ),
        )
    if (
        task.requires_structured_output
        and getattr(registered_model, "supports_structured_output", None) is False
    ):
        return QualityTaskGate(
            allowed=False,
            reason="Model is known not to support required structured output.",
        )
    return QualityTaskGate(allowed=True)


def evaluate_quality_response(
    task: QualityTask,
    response_text: str,
    *,
    tool_calls: object | None = None,
) -> QualityMeasurement:
    """Measure a task response without using an external judge or prompt text."""
    text = str(response_text or "")
    normalized = text.lower()
    payload = _parse_json_object(text)

    schema_valid = None
    if task.requires_structured_output:
        schema_valid = bool(
            payload is not None
            and all(field in payload for field in task.required_json_fields)
        )

    return QualityMeasurement(
        schema_valid=schema_valid,
        citation_fidelity=(
            task.expected_citation in text
            if task.expected_citation is not None
            else None
        ),
        instruction_following=(
            all(term.lower() in normalized for term in task.instruction_terms)
            if task.instruction_terms
            else None
        ),
        tool_calling=(
            _contains_tool_call(tool_calls, task.expected_tool_name)
            if task.expected_tool_name is not None
            else None
        ),
        context_recall=(
            task.context_marker in text if task.context_marker is not None else None
        ),
        answer_correctness=(
            all(term.lower() in normalized for term in task.correctness_terms)
            if task.correctness_terms
            else None
        ),
        refusal_when_evidence_absent=(
            "insufficient evidence" in normalized
            if task.requires_evidence_refusal
            else None
        ),
    )


def _parse_json_object(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _contains_tool_call(tool_calls: object | None, expected_name: str) -> bool:
    if not isinstance(tool_calls, list):
        return False
    for call in tool_calls:
        if isinstance(call, dict) and str(call.get("name", "")) == expected_name:
            return True
        if str(getattr(call, "name", "")) == expected_name:
            return True
    return False
