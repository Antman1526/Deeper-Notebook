"""Notebook-scoped evidence evaluation retrieval and rechecks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import Source
from deeper_notebook.evaluation.repository import EvaluationRepository
from deeper_notebook.evaluation.verifier import CitationSource, verify_response_claims

router = APIRouter()


class RecheckSource(BaseModel):
    marker: str = Field(pattern=r"^\[[^\[\]\n]{1,160}\]$")
    source_id: str = Field(min_length=1)


class RecheckRequest(BaseModel):
    evaluation_run_id: str = Field(min_length=1)
    notebook_id: str = Field(min_length=1)
    response_text: str = Field(min_length=1, max_length=100_000)
    sources: list[RecheckSource] = Field(min_length=1, max_length=100)


def _record_id(value: object) -> str:
    return str(value or "")


async def _owned_run(run_id: str, notebook_id: str) -> dict[str, Any]:
    rows = await repo_query(
        "SELECT * FROM $run_id WHERE notebook_id = $notebook_id LIMIT 1",
        {
            "run_id": ensure_record_id(run_id),
            "notebook_id": ensure_record_id(notebook_id),
        },
    )
    if not rows:
        # Do not reveal whether a run exists in another notebook.
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return dict(rows[0])


def _run_status(run: dict[str, Any]) -> str:
    metrics = run.get("metrics")
    if isinstance(metrics, dict) and metrics.get("status") in {
        "pending",
        "running",
        "completed",
        "failed",
    }:
        return str(metrics["status"])
    return "failed" if run.get("error") else "completed"


def _counts(verdicts: list[object]) -> dict[str, int]:
    result = {
        name: 0
        for name in ("supported", "partial", "contradicted", "unsupported", "uncited")
    }
    for verdict in verdicts:
        status = getattr(verdict, "status", None)
        if status in result:
            result[status] += 1
    return result


@router.get("/evaluations/{run_id}")
async def get_evaluation(run_id: str, notebook_id: str) -> dict[str, Any]:
    """Return exactly one notebook-owned run and its immutable verdicts."""
    run = await _owned_run(run_id, notebook_id)
    verdicts = await EvaluationRepository().list_verdicts(run_id)
    return {
        "run": {
            "id": _record_id(run.get("id")),
            "notebook_id": _record_id(run.get("notebook_id")),
            "artifact_id": _record_id(run.get("artifact_id")) or None,
            "message_id": run.get("message_id"),
            "evaluator_version": run.get("evaluator_version"),
            "model_id": run.get("model_id"),
            "metrics": run.get("metrics") or {},
            "error": run.get("error"),
            "created": str(run.get("created")) if run.get("created") else None,
        },
        "status": _run_status(run),
        "counts": _counts(verdicts),
        "verdicts": [verdict.model_dump(mode="json") for verdict in verdicts],
    }


@router.post("/evaluations/recheck")
async def recheck_evaluation(payload: RecheckRequest) -> dict[str, Any]:
    """Create a new evaluation from explicit notebook-owned source selections."""
    await _owned_run(payload.evaluation_run_id, payload.notebook_id)

    source_map: dict[str, CitationSource] = {}
    snapshots: dict[str, str] = {}
    for selection in payload.sources:
        source = await Source.get(selection.source_id)
        source_notebooks = await source.get_notebooks()
        if not any(
            str(notebook.id) == payload.notebook_id for notebook in source_notebooks
        ):
            raise HTTPException(status_code=404, detail="Source not found")
        text = (source.full_text or "").strip()
        if not text:
            raise HTTPException(status_code=409, detail="Source text is not ready")
        citation_source = CitationSource(str(source.id), text)
        source_map[selection.marker] = citation_source
        snapshots[citation_source.source_id] = citation_source.text

    verdicts = verify_response_claims(payload.response_text, source_map)
    stored = await EvaluationRepository().create_run(
        notebook_id=payload.notebook_id,
        evaluator_version="deterministic-v1",
        model_id=None,
        source_snapshots=snapshots,
        verdicts=verdicts,
        metrics={
            "status": "completed",
            "surface": "recheck",
            "counts": _counts(verdicts),
        },
    )
    return await get_evaluation(stored.id, payload.notebook_id)
