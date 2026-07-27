"""Quality-task definitions and deterministic evaluators."""

from __future__ import annotations

from types import SimpleNamespace

from deeper_notebook.local_models.quality_tasks import (
    evaluate_quality_response,
    gate_quality_task,
    quality_task_for_role,
)


def test_quality_task_evaluates_typed_response_signals():
    task = quality_task_for_role("source_synthesis")

    signals = evaluate_quality_response(
        task,
        '{"answer": "The evidence says the archive is local.", '
        '"citation": "[source:brief]", "context": "ORCHID-17", '
        '"refusal": "Insufficient evidence for any other claim."}',
    )

    assert signals.schema_valid is True
    assert signals.citation_fidelity is True
    assert signals.instruction_following is True
    assert signals.context_recall is True
    assert signals.answer_correctness is True
    assert signals.refusal_when_evidence_absent is True
    assert signals.tool_calling is None


def test_quality_task_gate_requires_context_and_rejects_known_missing_structured_output():
    task = quality_task_for_role("source_synthesis")
    too_small = SimpleNamespace(metadata=SimpleNamespace(context_length=2048))

    context_gate = gate_quality_task(task, too_small, SimpleNamespace())
    assert context_gate.allowed is False
    assert "context" in (context_gate.reason or "").lower()

    enough_context = SimpleNamespace(metadata=SimpleNamespace(context_length=8192))
    structured_gate = gate_quality_task(
        task,
        enough_context,
        SimpleNamespace(supports_structured_output=False),
    )
    assert structured_gate.allowed is False
    assert "structured output" in (structured_gate.reason or "").lower()
