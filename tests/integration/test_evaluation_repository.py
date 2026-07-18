"""Real-SurrealDB persistence tests for evidence evaluation records."""

from __future__ import annotations

import pytest

from open_notebook.database.repository import repo_query
from open_notebook.domain.notebook import Notebook, Source
from open_notebook.evaluation.repository import EvaluationRepository
from open_notebook.evaluation.schemas import (
    ClaimVerdict,
    EvidenceSpan,
    hash_source_text,
)

pytestmark = pytest.mark.integration_surreal


async def test_repository_persists_hashed_evidence_and_marks_source_drift(
    clean_namespace,
):
    notebook = Notebook(name="Evaluation", description="Evidence persistence test")
    await notebook.save()
    source = Source(title="Snapshot", full_text="Alpha evidence quote.")
    await source.save()

    source_id = str(source.id)
    snapshot = source.full_text
    verdict = ClaimVerdict(
        claim="Alpha is present.",
        status="supported",
        confidence=0.9,
        citation_markers=["[1]"],
        evidence=[
            EvidenceSpan(
                source_id=source_id,
                source_content_sha256=hash_source_text(snapshot),
                start=0,
                end=5,
                quote="Alpha",
            )
        ],
        explanation="The source states Alpha.",
    )

    repository = EvaluationRepository()
    saved = await repository.create_run(
        notebook_id=str(notebook.id),
        evaluator_version="evaluation-v1",
        model_id="local:test-model",
        source_snapshots={source_id: snapshot},
        verdicts=[verdict],
        metrics={"latency_ms": 14},
    )

    persisted_runs = await repo_query(
        "SELECT notebook_id, evaluator_version, model_id, source_content_hashes, metrics "
        "FROM evaluation_run WHERE id = $id",
        {"id": saved.id},
    )
    assert persisted_runs == [
        {
            "notebook_id": notebook.id,
            "evaluator_version": "evaluation-v1",
            "model_id": "local:test-model",
            "source_content_hashes": [
                {"source_id": source_id, "sha256": hash_source_text(snapshot)}
            ],
            "metrics": {"latency_ms": 14},
        }
    ]

    resolved = await repository.list_verdicts(
        str(saved.id),
        current_source_texts={source_id: "Completely replaced source text."},
    )
    assert len(resolved) == 1
    assert resolved[0].evidence[0].source_state == "source_changed"
    assert resolved[0].evidence[0].quote == "Alpha"


async def test_repository_persists_only_a_sanitized_error(clean_namespace):
    notebook = Notebook(name="Evaluation error", description="Sanitization test")
    await notebook.save()

    saved = await EvaluationRepository().create_run(
        notebook_id=str(notebook.id),
        evaluator_version="evaluation-v1",
        model_id=None,
        source_snapshots={},
        verdicts=[],
        error=RuntimeError("provider token=super-secret-value"),
    )

    rows = await repo_query(
        "SELECT error FROM evaluation_run WHERE id = $id",
        {"id": saved.id},
    )
    assert rows == [{"error": "Evaluation failed. Review local logs for details."}]
