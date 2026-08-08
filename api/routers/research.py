"""Notebook-owned, approval-first Research Run endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from api.schemas.research import (
    ApproveResearchSourcesRequest,
    CreateResearchRunRequest,
    ResearchCandidateResponse,
    ResearchComparisonResponse,
    ResearchEventResponse,
    ResearchRunResponse,
)
from deeper_notebook.domain.notebook import Notebook
from deeper_notebook.research.analysis import (
    compare_research_evidence,
    extract_research_evidence,
    synthesize_research_evidence,
    validate_research_evidence,
)
from deeper_notebook.research.discovery import (
    candidate_domain,
    discover_sources,
    ingest_approved_sources,
)
from deeper_notebook.research.graph import ResearchWorkflow
from deeper_notebook.research.repository import (
    ResearchRunRepository,
    ResearchRunRepositoryError,
)
from deeper_notebook.research.state import ResearchRun, ResearchStageResult
from deeper_notebook.security.outbound_url import (
    OutboundURLPolicyError,
    validate_outbound_url,
)

router = APIRouter()


def _workflow(repository: ResearchRunRepository) -> ResearchWorkflow:
    async def plan(run: ResearchRun) -> ResearchStageResult:
        query = next(
            (item for item in run.search_queries if item.strip()), run.objective
        )
        return ResearchStageResult(checkpoint={"query": query}, search_queries=[query])

    return ResearchWorkflow(
        repository,
        handlers={
            "plan": plan,
            "discover": discover_sources,
            "ingest": ingest_approved_sources,
            "extract": extract_research_evidence,
            "compare": compare_research_evidence,
            "synthesize": synthesize_research_evidence,
            "validate": validate_research_evidence,
        },
    )


async def _require_notebook(notebook_id: str) -> None:
    if not await Notebook.get(notebook_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found"
        )


async def _owned_run(
    repository: ResearchRunRepository, notebook_id: str, run_id: str
) -> ResearchRun:
    run = await repository.get(run_id)
    if run is None or str(run.notebook_id) != notebook_id:
        # Do not disclose the existence of a run owned by another notebook.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found"
        )
    return run


def _response(run: ResearchRun) -> ResearchRunResponse:
    query = next((item for item in run.search_queries if item.strip()), None)
    candidates: list[ResearchCandidateResponse] = []
    for candidate in run.candidates:
        value = run.approval_decisions.get(candidate.candidate_id)
        decision = (
            "accepted" if value is True else "rejected" if value is False else "pending"
        )
        candidates.append(
            ResearchCandidateResponse(
                candidate_id=candidate.candidate_id,
                url=candidate.url,
                title=candidate.title,
                domain=candidate_domain(candidate.url),
                snippet=candidate.summary,
                search_query=query,
                decision=decision,
                evidence=candidate.evidence,
            )
        )
    comparison_data = run.checkpoints.get("compare", {}).get("comparison", {})
    if not isinstance(comparison_data, dict):
        comparison_data = {}
    return ResearchRunResponse(
        id=str(run.id),
        notebook_id=str(run.notebook_id),
        objective=run.objective,
        stage=run.stage,
        plan=run.plan,
        hypotheses=run.hypotheses,
        search_query=query,
        candidates=candidates,
        source_ids=run.source_ids,
        errors=run.errors,
        comparison=ResearchComparisonResponse.model_validate(comparison_data),
        cancelled=run.cancelled,
    )


def _repository() -> ResearchRunRepository:
    return ResearchRunRepository()


@router.post(
    "/notebooks/{notebook_id}/research-runs",
    response_model=ResearchRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_research_run(
    notebook_id: str, payload: CreateResearchRunRequest
) -> ResearchRunResponse:
    """Discover candidates, then stop at explicit source approval."""
    await _require_notebook(notebook_id)
    repository = _repository()
    try:
        created = await repository.create(
            ResearchRun(
                notebook_id=notebook_id,
                objective=payload.objective,
                search_queries=[payload.query or payload.objective],
            )
        )
        run = await _workflow(repository).resume(created.id or "")
    except ResearchRunRepositoryError:
        raise HTTPException(
            status_code=503, detail="Research runs are unavailable"
        ) from None
    return _response(run)


@router.get(
    "/notebooks/{notebook_id}/research-runs/{run_id}",
    response_model=ResearchRunResponse,
)
async def get_research_run(notebook_id: str, run_id: str) -> ResearchRunResponse:
    return _response(await _owned_run(_repository(), notebook_id, run_id))


@router.post(
    "/notebooks/{notebook_id}/research-runs/{run_id}/approve",
    response_model=ResearchRunResponse,
)
async def approve_research_sources(
    notebook_id: str, run_id: str, payload: ApproveResearchSourcesRequest
) -> ResearchRunResponse:
    """Record every candidate decision before any accepted URL is imported."""
    repository = _repository()
    run = await _owned_run(repository, notebook_id, run_id)
    if run.cancelled:
        raise HTTPException(status_code=409, detail="Research run has been cancelled")
    if run.stage != "await_source_approval":
        raise HTTPException(
            status_code=409, detail="Research run is not awaiting source approval"
        )

    candidate_ids = {candidate.candidate_id for candidate in run.candidates}
    accepted_ids = set(payload.accepted_candidate_ids)
    if unknown := accepted_ids - candidate_ids:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown research candidate: {sorted(unknown)[0]}",
        )
    # Approval is an independent policy check before the safe fetcher's
    # connection-time revalidation. A search-result URL cannot be approved if
    # it now resolves to a private or otherwise disallowed destination.
    for candidate in run.candidates:
        if candidate.candidate_id in accepted_ids:
            try:
                await validate_outbound_url(candidate.url)
            except OutboundURLPolicyError:
                raise HTTPException(
                    status_code=409,
                    detail="An accepted source no longer passes the outbound URL policy",
                ) from None

    decisions = {
        candidate.candidate_id: candidate.candidate_id in accepted_ids
        for candidate in run.candidates
    }
    try:
        approved = await repository.save_approval_decisions(run, decisions)
        resumed = await _workflow(repository).resume(approved.id or "")
    except ResearchRunRepositoryError:
        raise HTTPException(
            status_code=503, detail="Research runs are unavailable"
        ) from None
    return _response(resumed)


@router.post(
    "/notebooks/{notebook_id}/research-runs/{run_id}/cancel",
    response_model=ResearchRunResponse,
)
async def cancel_research_run(notebook_id: str, run_id: str) -> ResearchRunResponse:
    repository = _repository()
    await _owned_run(repository, notebook_id, run_id)
    cancelled = await repository.request_cancellation(run_id)
    if cancelled is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return _response(cancelled)


@router.post(
    "/notebooks/{notebook_id}/research-runs/{run_id}/resume",
    response_model=ResearchRunResponse,
)
async def resume_research_run(notebook_id: str, run_id: str) -> ResearchRunResponse:
    repository = _repository()
    run = await _owned_run(repository, notebook_id, run_id)
    if run.cancelled:
        return _response(run)
    try:
        return _response(await _workflow(repository).resume(run_id))
    except ResearchRunRepositoryError:
        raise HTTPException(
            status_code=503, detail="Research runs are unavailable"
        ) from None


async def _event_stream(run: ResearchRun) -> AsyncIterator[str]:
    event = ResearchEventResponse(run=_response(run))
    yield f"event: {event.event}\ndata: {json.dumps(event.model_dump(mode='json'))}\n\n"


@router.get("/notebooks/{notebook_id}/research-runs/{run_id}/events")
async def research_run_events(notebook_id: str, run_id: str) -> StreamingResponse:
    """Emit a current durable-state receipt for polling/EventSource clients."""
    run = await _owned_run(_repository(), notebook_id, run_id)
    return StreamingResponse(
        _event_stream(run),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
