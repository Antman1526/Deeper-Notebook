"""Quality-task definitions and deterministic evaluators."""

from __future__ import annotations

from types import SimpleNamespace

from deeper_notebook.local_models.quality_tasks import (
    evaluate_quality_response,
    gate_quality_task,
    quality_task_for_role,
)


def test_quality_tasks_cover_every_approved_role_and_keep_speech_probes_bounded():
    roles = {
        "research_chat",
        "evidence_extraction",
        "claim_verification",
        "editorial_writing",
        "embedding_retrieval",
        "vision_analysis",
        "code_data_analysis",
        "podcast_outline",
        "podcast_script",
        "speech_to_text",
        "text_to_speech",
    }

    tasks = {role: quality_task_for_role(role) for role in roles}

    assert set(tasks) == roles
    assert all(task.role in roles for task in tasks.values())
    assert all(task.prompt for role, task in tasks.items() if "speech" not in role)
    assert tasks["speech_to_text"].probe_kind == "capability_identity"
    assert tasks["text_to_speech"].probe_kind == "capability_identity"
    assert tasks["speech_to_text"].prompt == ""
    assert tasks["text_to_speech"].prompt == ""
    assert tasks["speech_to_text"].maximum_probe_bytes <= 4096
    assert tasks["text_to_speech"].maximum_probe_bytes <= 4096


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
