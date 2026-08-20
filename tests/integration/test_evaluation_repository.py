"""Real-SurrealDB persistence tests for evidence evaluation records."""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import Notebook, Source
from deeper_notebook.evaluation.repository import EvaluationRepository
from deeper_notebook.evaluation.schemas import (
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
        {"id": ensure_record_id(saved.id)},
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
        {"id": ensure_record_id(saved.id)},
    )
    assert rows == [{"error": "Evaluation failed. Review local logs for details."}]


async def test_repository_batches_newest_message_runs_with_notebook_ownership(
    clean_namespace,
):
    """Exercise the production nested query against a real SurrealDB runtime."""
    notebook = Notebook(name="Batch evaluation", description="Owned batch lookup")
    other_notebook = Notebook(name="Other notebook", description="Isolation check")
    await notebook.save()
    await other_notebook.save()

    repository = EvaluationRepository()
    older = await repository.create_run(
        notebook_id=str(notebook.id),
        evaluator_version="evaluation-v1",
        model_id="local:test-model",
        source_snapshots={},
        verdicts=[],
        message_id="message:one",
        metrics={"generation": 1},
    )
    await asyncio.sleep(0.01)
    newest = await repository.create_run(
        notebook_id=str(notebook.id),
        evaluator_version="evaluation-v1",
        model_id="local:test-model",
        source_snapshots={},
        verdicts=[
            ClaimVerdict(
                claim="Newest claim",
                status="uncited",
                confidence=1,
                explanation="No source marker.",
            )
        ],
        message_id="message:one",
        metrics={"generation": 2},
    )
    second = await repository.create_run(
        notebook_id=str(notebook.id),
        evaluator_version="evaluation-v1",
        model_id="local:test-model",
        source_snapshots={},
        verdicts=[],
        message_id="message:two",
        metrics={"generation": 1},
    )
    await repository.create_run(
        notebook_id=str(other_notebook.id),
        evaluator_version="evaluation-v1",
        model_id="local:test-model",
        source_snapshots={},
        verdicts=[],
        message_id="message:one",
        metrics={"generation": 99},
    )

    runs = await repository.latest_runs_for_messages(
        notebook_id=str(notebook.id),
        message_ids=["message:one", "message:two", "message:missing"],
    )

    assert {str(run["id"]) for run in runs} == {newest.id, second.id}
    assert older.id not in {str(run["id"]) for run in runs}
    assert {str(run["notebook_id"]) for run in runs} == {str(notebook.id)}
    assert {run["message_id"] for run in runs} == {"message:one", "message:two"}
    assert next(run for run in runs if run["message_id"] == "message:one")[
        "metrics"
    ] == {"generation": 2}

    verdicts = await repository.list_verdicts_for_runs([str(run["id"]) for run in runs])
    assert [verdict.claim for verdict in verdicts[newest.id]] == ["Newest claim"]
    assert verdicts[second.id] == []
