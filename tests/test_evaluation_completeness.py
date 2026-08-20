"""Behavior contracts for notebook-scoped evidence review lookup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routers import evaluations
from deeper_notebook.evaluation.repository import EvaluationRepository
from deeper_notebook.evaluation.schemas import ClaimVerdict


def _uncited(claim: str) -> ClaimVerdict:
    return ClaimVerdict(
        claim=claim,
        status="uncited",
        confidence=1,
        explanation="No source marker.",
    )


@pytest.mark.asyncio
async def test_latest_lookup_is_notebook_owned_and_returns_newest_selector_run(
    monkeypatch,
):
    captured: dict[str, object] = {}

    async def fake_query(query: str, variables: dict[str, object]):
        if "claim_verdict" in query:
            return [
                {
                    "created": "2026-08-11T02:00:00Z",
                    "schema_version": 1,
                    "claim": "The newest run",
                    "status": "uncited",
                    "confidence": 1,
                    "citation_markers": [],
                    "evidence": [],
                    "explanation": "No source marker.",
                }
            ]
        captured["query"] = query
        captured["variables"] = variables
        return [
            {
                "id": "evaluation_run:new",
                "notebook_id": "notebook:mine",
                "artifact_id": "studio_artifact:one",
                "message_id": None,
                "evaluator_version": "deterministic-v1",
                "metrics": {"status": "completed"},
                "created": "2026-08-11T02:00:00Z",
            }
        ]

    monkeypatch.setattr("deeper_notebook.evaluation.repository.repo_query", fake_query)

    result = await evaluations.get_latest_evaluation(
        notebook_id="notebook:mine",
        artifact_id="studio_artifact:one",
    )

    assert result["run"]["id"] == "evaluation_run:new"
    assert result["run"]["artifact_id"] == "studio_artifact:one"
    assert result["counts"]["uncited"] == 1
    query = str(captured["query"])
    assert "SELECT *" not in query
    assert "ORDER BY created DESC" in query
    assert "LIMIT 1" in query
    variables = captured["variables"]
    assert isinstance(variables, dict)
    assert str(variables["notebook_id"]) == "notebook:mine"
    assert str(variables["artifact_id"]) == "studio_artifact:one"


@pytest.mark.asyncio
async def test_latest_lookup_returns_404_for_missing_or_cross_notebook_selector(
    monkeypatch,
):
    async def fake_query(_query: str, _variables: dict[str, object]):
        return []

    class Repository:
        async def latest_run(self, **_kwargs):
            return None

    monkeypatch.setattr(evaluations, "EvaluationRepository", Repository)

    with pytest.raises(HTTPException) as missing:
        await evaluations.get_latest_evaluation(
            notebook_id="notebook:mine", message_id="message:missing"
        )
    assert missing.value.status_code == 404

    with pytest.raises(HTTPException) as cross_notebook:
        await evaluations.get_latest_evaluation(
            notebook_id="notebook:mine", artifact_id="studio_artifact:other"
        )
    assert cross_notebook.value.status_code == 404


@pytest.mark.asyncio
async def test_latest_routes_preserve_typed_http_errors_from_repository(monkeypatch):
    class Repository:
        async def latest_run(self, **_kwargs):
            raise HTTPException(status_code=409, detail="evaluation is changing")

        async def latest_runs_for_messages(self, **_kwargs):
            raise HTTPException(status_code=409, detail="evaluation is changing")

    monkeypatch.setattr(evaluations, "EvaluationRepository", Repository)

    with pytest.raises(HTTPException) as latest:
        await evaluations.get_latest_evaluation(
            notebook_id="notebook:mine", message_id="message:one"
        )
    assert latest.value.status_code == 409
    assert latest.value.detail == "evaluation is changing"

    with pytest.raises(HTTPException) as batch:
        await evaluations.batch_latest_evaluations(
            evaluations.EvaluationBatchRequest(
                notebook_id="notebook:mine", message_ids=["message:one"]
            )
        )
    assert batch.value.status_code == 409
    assert batch.value.detail == "evaluation is changing"


@pytest.mark.asyncio
async def test_latest_lookup_requires_exactly_one_bounded_selector(monkeypatch):
    monkeypatch.setattr(
        evaluations, "repo_query", lambda *_args: pytest.fail("query should not run")
    )

    with pytest.raises(HTTPException) as missing:
        await evaluations.get_latest_evaluation(notebook_id="notebook:mine")
    assert missing.value.status_code == 422

    with pytest.raises(HTTPException) as both:
        await evaluations.get_latest_evaluation(
            notebook_id="notebook:mine",
            artifact_id="studio_artifact:one",
            message_id="message:one",
        )
    assert both.value.status_code == 422

    with pytest.raises(HTTPException) as malformed_notebook:
        await evaluations.get_latest_evaluation(
            notebook_id="notebook:bad:id", message_id="message:one"
        )
    assert malformed_notebook.value.status_code == 422


@pytest.mark.asyncio
async def test_batch_lookup_deduplicates_ids_and_uses_one_run_and_one_verdict_query(
    monkeypatch,
):
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_query(query: str, variables: dict[str, object]):
        calls.append((query, variables))
        if "claim_verdict" in query:
            return [
                {
                    "evaluation_run_id": "evaluation_run:one",
                    "created": "2026-08-11T02:00:00Z",
                    "schema_version": 1,
                    "claim": "One claim",
                    "status": "uncited",
                    "confidence": 1,
                    "citation_markers": [],
                    "evidence": [],
                    "explanation": "No source marker.",
                }
            ]
        return [
            {
                "id": "evaluation_run:one",
                "notebook_id": "notebook:mine",
                "artifact_id": None,
                "message_id": "message:one",
                "evaluator_version": "deterministic-v1",
                "metrics": {"status": "completed"},
                "created": "2026-08-11T02:00:00Z",
            },
            {
                "id": "evaluation_run:two",
                "notebook_id": "notebook:mine",
                "artifact_id": None,
                "message_id": "message:two",
                "evaluator_version": "deterministic-v1",
                "metrics": {"status": "running"},
                "created": "2026-08-11T01:00:00Z",
            },
        ]

    monkeypatch.setattr("deeper_notebook.evaluation.repository.repo_query", fake_query)

    result = await evaluations.batch_latest_evaluations(
        evaluations.EvaluationBatchRequest(
            notebook_id="notebook:mine",
            message_ids=["message:one", "message:one", "message:two", "message:absent"],
        )
    )

    assert set(result) == {"message:one", "message:two"}
    assert result["message:one"]["counts"]["uncited"] == 1
    assert result["message:two"]["status"] == "running"
    assert len(calls) == 2
    run_query, run_variables = calls[0]
    assert "SELECT *" not in run_query
    assert "ORDER BY created DESC" in run_query
    assert run_query.count("message_id = $message_id_") == 3
    assert run_query.count("LIMIT 1") == 3
    assert set(run_variables) == {
        "notebook_id",
        "message_id_0",
        "message_id_1",
        "message_id_2",
    }
    verdict_query, verdict_variables = calls[1]
    assert "evaluation_run_id IN" in verdict_query
    assert set(str(value) for value in verdict_variables["run_ids"]) == {
        "evaluation_run:one",
        "evaluation_run:two",
    }


def test_batch_lookup_bounds_message_ids_before_querying():
    with pytest.raises(ValidationError):
        evaluations.EvaluationBatchRequest(
            notebook_id="notebook:mine",
            message_ids=[f"message:{index}" for index in range(101)],
        )

    with pytest.raises(ValidationError):
        evaluations.EvaluationBatchRequest(
            notebook_id="notebook:mine",
            message_ids=["x" * 513],
        )


def test_batch_lookup_applies_the_limit_after_deduplicating_ids():
    payload = evaluations.EvaluationBatchRequest(
        notebook_id="notebook:mine",
        message_ids=["message:one"] * 101,
    )

    assert payload.message_ids == ["message:one"]

    with pytest.raises(ValidationError):
        evaluations.EvaluationBatchRequest(
            notebook_id="notebook:mine",
            message_ids=["message:one"] * 257,
        )


@pytest.mark.asyncio
async def test_batch_query_limits_each_selector_branch_with_many_histories(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_query(query: str, variables: dict[str, object]):
        captured["query"] = query
        captured["variables"] = variables
        return []

    monkeypatch.setattr("deeper_notebook.evaluation.repository.repo_query", fake_query)
    message_ids = [f"message:{index}" for index in range(100)]

    result = await EvaluationRepository().latest_runs_for_messages(
        notebook_id="notebook:mine",
        message_ids=message_ids,
    )

    assert result == []
    query = str(captured["query"])
    assert query.count("message_id = $message_id_") == 100
    assert query.count("ORDER BY created DESC LIMIT 1") == 100
    assert "ORDER BY created DESC LIMIT 100" not in query
    variables = captured["variables"]
    assert isinstance(variables, dict)
    assert len(variables) == 101


@pytest.mark.asyncio
async def test_recheck_preserves_original_artifact_and_message_selector(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_owned_run(_run_id: str, _notebook_id: str):
        return {
            "id": "evaluation_run:old",
            "notebook_id": "notebook:mine",
            "artifact_id": "studio_artifact:one",
            "message_id": "message:one",
        }

    class SourceRecord:
        id = "source:one"
        full_text = "The report is complete."

        async def get_notebooks(self):
            return [SimpleNamespace(id="notebook:mine")]

    class Repository:
        async def create_run(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(id="evaluation_run:new")

    monkeypatch.setattr(evaluations, "_owned_run", fake_owned_run)

    async def fake_source_get(_source_id: str):
        return SourceRecord()

    monkeypatch.setattr(evaluations.Source, "get", fake_source_get)
    monkeypatch.setattr(
        evaluations,
        "verify_response_claims",
        lambda _response_text, _source_map: [],
    )
    monkeypatch.setattr(evaluations, "EvaluationRepository", Repository)

    async def fake_get_evaluation(run_id: str, notebook_id: str):
        return {"run": {"id": run_id, "notebook_id": notebook_id}}

    monkeypatch.setattr(evaluations, "get_evaluation", fake_get_evaluation)

    result = await evaluations.recheck_evaluation(
        evaluations.RecheckRequest(
            evaluation_run_id="evaluation_run:old",
            notebook_id="notebook:mine",
            response_text="The report is complete [S1].",
            sources=[{"marker": "[S1]", "source_id": "source:one"}],
        )
    )

    assert result["run"]["id"] == "evaluation_run:new"
    assert captured["artifact_id"] == "studio_artifact:one"
    assert captured["message_id"] == "message:one"
