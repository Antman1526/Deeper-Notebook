"""Notebook-scoped evidence evaluation retrieval and rechecks."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import Source
from deeper_notebook.evaluation.repository import (
    EvaluationRepository,
    EvaluationRepositoryError,
)
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


class EvaluationBatchRequest(BaseModel):
    """Bounded notebook-owned lookup for visible notebook-chat messages."""

    notebook_id: str = Field(min_length=1, max_length=512)
    # Keep the raw request bounded before validation while applying the public
    # 100-item limit to unique IDs. This accepts harmless duplicate-heavy
    # clients without allowing an attacker-sized list to materialize.
    message_ids: list[str] = Field(min_length=1, max_length=256)

    @field_validator("notebook_id")
    @classmethod
    def validate_notebook_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("notebook_id must not be blank")
        return value

    @field_validator("message_ids")
    @classmethod
    def validate_message_ids(cls, value: list[str]) -> list[str]:
        if any(not message_id.strip() for message_id in value):
            raise ValueError("message_ids must not contain blank identifiers")
        if any(len(message_id) > 512 for message_id in value):
            raise ValueError("message IDs must be at most 512 characters")
        unique = list(dict.fromkeys(value))
        if len(unique) > 100:
            raise ValueError("message_ids must contain at most 100 unique identifiers")
        return unique


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


def _evaluation_payload(
    run: dict[str, Any], verdicts: list[object]
) -> dict[str, Any]:
    """Project one run through the existing public detail response shape."""
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


def _validate_selector(
    *,
    notebook_id: str,
    artifact_id: str | None,
    message_id: str | None,
) -> tuple[Literal["artifact_id", "message_id"], str, object]:
    """Require one bounded selector and prepare its parameterized value."""
    if not notebook_id.strip():
        raise HTTPException(status_code=422, detail="notebook_id must not be blank")
    supplied = [
        ("artifact_id", artifact_id),
        ("message_id", message_id),
    ]
    selected = [(name, value) for name, value in supplied if value is not None]
    if len(selected) != 1:
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of artifact_id or message_id",
        )
    field, value = selected[0]
    assert value is not None
    if not value.strip() or len(value) > 512:
        raise HTTPException(status_code=422, detail="Evaluation selector is invalid")
    if field == "artifact_id":
        try:
            return field, value, ensure_record_id(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422, detail="artifact_id is not a valid record ID"
            ) from None
    return field, value, value


@router.get("/evaluations/latest")
async def get_latest_evaluation(
    notebook_id: str = Query(..., min_length=1, max_length=512),
    artifact_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
    message_id: Annotated[str | None, Query(min_length=1, max_length=512)] = None,
) -> dict[str, Any]:
    """Return the newest evaluation for exactly one notebook-owned selector."""
    selector_field, _selector_text, selector_value = _validate_selector(
        notebook_id=notebook_id,
        artifact_id=artifact_id,
        message_id=message_id,
    )
    try:
        ensure_record_id(notebook_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="notebook_id is invalid") from None
    repository = EvaluationRepository()
    try:
        run = await repository.latest_run(
            notebook_id=notebook_id,
            selector_field=selector_field,
            selector_value=selector_value,
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=422, detail="Evaluation selector is invalid") from None
    except Exception as exc:
        # Repository errors are deliberately not projected as raw DB details.
        # Keep the existing router's fail-soft boundary for unavailable storage.
        if isinstance(exc, EvaluationRepositoryError):
            raise HTTPException(status_code=503, detail="Evaluations are unavailable") from None
        raise
    if run is None:
        # Missing and cross-notebook selectors intentionally have one response.
        raise HTTPException(status_code=404, detail="Evaluation not found")
    verdicts = await repository.list_verdicts(_record_id(run.get("id")))
    return _evaluation_payload(run, verdicts)


@router.post("/evaluations/latest/batch")
async def batch_latest_evaluations(
    payload: EvaluationBatchRequest,
) -> dict[str, dict[str, Any]]:
    """Return at most one newest notebook-owned run per requested message ID."""
    try:
        ensure_record_id(payload.notebook_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="notebook_id is invalid") from None

    message_ids = list(dict.fromkeys(payload.message_ids))
    if not message_ids:
        raise HTTPException(status_code=422, detail="message_ids must not be empty")
    repository = EvaluationRepository()
    try:
        rows = await repository.latest_runs_for_messages(
            notebook_id=payload.notebook_id,
            message_ids=message_ids,
        )
    except HTTPException:
        raise
    except Exception as exc:
        if isinstance(exc, EvaluationRepositoryError):
            raise HTTPException(status_code=503, detail="Evaluations are unavailable") from None
        raise

    # The query is newest-first; first row wins for each requested ID. Keep the
    # response a literal requested-ID map so arbitrary DB fields never leak.
    requested = set(message_ids)
    runs_by_message: dict[str, dict[str, Any]] = {}
    for row in rows:
        run = dict(row)
        message_id = run.get("message_id")
        if (
            not isinstance(message_id, str)
            or message_id not in requested
            or message_id in runs_by_message
        ):
            continue
        runs_by_message[message_id] = run
    if not runs_by_message:
        return {}

    verdicts_by_run = await repository.list_verdicts_for_runs(
        [_record_id(run.get("id")) for run in runs_by_message.values()]
    )
    return {
        message_id: _evaluation_payload(
            run, verdicts_by_run.get(_record_id(run.get("id")), [])
        )
        for message_id, run in runs_by_message.items()
    }


@router.get("/evaluations/{run_id}")
async def get_evaluation(run_id: str, notebook_id: str) -> dict[str, Any]:
    """Return exactly one notebook-owned run and its immutable verdicts."""
    run = await _owned_run(run_id, notebook_id)
    verdicts = await EvaluationRepository().list_verdicts(run_id)
    return _evaluation_payload(run, verdicts)


@router.post("/evaluations/recheck")
async def recheck_evaluation(payload: RecheckRequest) -> dict[str, Any]:
    """Create a new evaluation from explicit notebook-owned source selections."""
    original_run = await _owned_run(payload.evaluation_run_id, payload.notebook_id)

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
        artifact_id=_record_id(original_run.get("artifact_id")) or None,
        message_id=original_run.get("message_id"),
        metrics={
            "status": "completed",
            "surface": "recheck",
            "counts": _counts(verdicts),
        },
    )
    return await get_evaluation(stored.id, payload.notebook_id)
