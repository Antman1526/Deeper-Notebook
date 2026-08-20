"""Owner-operated endpoints for the private local Capture Inbox."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from math import sqrt
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status

from api.schemas.capture import (
    CaptureItemResponse,
    CaptureRootResponse,
    CaptureRouteRequest,
    CaptureRouteResponse,
    CaptureScanRequest,
    CaptureScanResponse,
    RegisterCaptureRootRequest,
)
from api.source_visual_projection import project_capture_linked_sources
from deeper_notebook.ai.models import Model, model_manager
from deeper_notebook.ai.offline_gate import LOCAL_PROVIDERS
from deeper_notebook.capture.routing import (
    CaptureNotebook,
    CaptureNotebookSuggestion,
    CaptureRouteSource,
    CaptureRoutingError,
    CaptureRoutingService,
)
from deeper_notebook.capture.watcher import (
    DEFAULT_CAPTURE_ROOT,
    CaptureInboxWatcher,
    SurrealCaptureRepository,
    _resolved_root,
)
from deeper_notebook.domain.notebook import Notebook
from deeper_notebook.feature_flags import source_visuals_enabled

router = APIRouter(prefix="/capture", tags=["capture"])


async def _local_semantic_suggestions(
    transcript: str,
    source: CaptureRouteSource,
    notebooks: tuple[CaptureNotebook, ...],
) -> list[CaptureNotebookSuggestion]:
    """Rank capture targets with local embeddings only; never call a cloud model."""
    if not notebooks:
        return []
    defaults = await model_manager.get_defaults()
    model_id = defaults.default_embedding_model
    if not model_id:
        return []
    record = await Model.get(model_id)
    if (record.provider or "").lower() not in LOCAL_PROVIDERS:
        return []
    model = await model_manager.get_embedding_model()
    if model is None:
        return []
    embeddings = await model.aembed(
        [
            f"{transcript}\n{source.relative_path}",
            *[f"{item.name}" for item in notebooks],
        ]
    )
    if len(embeddings) != len(notebooks) + 1:
        return []
    query = embeddings[0]
    query_norm = sqrt(sum(value * value for value in query))
    if not query_norm:
        return []
    scored: list[CaptureNotebookSuggestion] = []
    for notebook, vector in zip(notebooks, embeddings[1:], strict=True):
        if len(vector) != len(query):
            continue
        norm = sqrt(sum(value * value for value in vector))
        if not norm:
            continue
        score = sum(left * right for left, right in zip(query, vector, strict=True)) / (
            query_norm * norm
        )
        if score > 0:
            scored.append(
                CaptureNotebookSuggestion(
                    **notebook.model_dump(),
                    score=round(score, 3),
                    reason="Local semantic match",
                )
            )
    return sorted(scored, key=lambda item: (-item.score, item.name.lower()))[:3]


async def _approved_roots(repository: SurrealCaptureRepository) -> list[Path]:
    configured = await repository.list_roots()
    if not configured:
        # A first launch gets one predictable, local-only intake folder. It is
        # still an explicit root in the durable configuration, and no OAuth or
        # cloud-drive credentials are involved.
        DEFAULT_CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
        root = _resolved_root(DEFAULT_CAPTURE_ROOT)
        await repository.approve_root(root)
        return [root]
    return [_resolved_root(path) for path in configured]


@router.get("/roots", response_model=list[CaptureRootResponse])
async def list_capture_roots() -> list[CaptureRootResponse]:
    repository = SurrealCaptureRepository()
    try:
        return [
            CaptureRootResponse(path=str(root))
            for root in await _approved_roots(repository)
        ]
    except (OSError, ValueError):
        raise HTTPException(
            status_code=409, detail="A configured capture root is unavailable"
        ) from None


@router.post(
    "/roots", response_model=CaptureRootResponse, status_code=status.HTTP_201_CREATED
)
async def register_capture_root(
    payload: RegisterCaptureRootRequest,
) -> CaptureRootResponse:
    try:
        root = _resolved_root(payload.path)
        await SurrealCaptureRepository().approve_root(root)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=422, detail="Capture root must be an existing local directory"
        ) from None
    return CaptureRootResponse(path=str(root))


@router.get("/items", response_model=list[CaptureItemResponse])
async def list_capture_items(limit: int = 200) -> list[CaptureItemResponse]:
    items = await SurrealCaptureRepository().list_items(limit=limit)
    payloads = [item.model_dump() for item in items]
    if source_visuals_enabled():
        payloads = await project_capture_linked_sources(payloads)
    return [CaptureItemResponse(**item) for item in payloads]


@router.post("/scan", response_model=CaptureScanResponse)
async def scan_capture_inbox(payload: CaptureScanRequest) -> CaptureScanResponse:
    repository = SurrealCaptureRepository()
    try:
        roots = await _approved_roots(repository)
        if payload.root_path is not None:
            selected = _resolved_root(payload.root_path)
            if selected not in roots:
                raise ValueError("path is not an approved capture root")
            roots = [selected]
        watcher = CaptureInboxWatcher(approved_roots=roots, repository=repository)
        items = []
        for root in roots:
            items.extend(await watcher.scan_root(root))
    except (OSError, ValueError):
        raise HTTPException(
            status_code=422, detail="Capture root is not approved or available"
        ) from None
    return CaptureScanResponse(
        items=[CaptureItemResponse(**item.model_dump()) for item in items]
    )


async def _route_capture_media(
    payload: CaptureRouteRequest,
    *,
    repository: Any,
    get_speech_to_text: Callable[[], Awaitable[Any | None]],
    load_notebooks: Callable[[], Awaitable[list[Any]]],
    semantic_suggester: Callable[..., Awaitable[list[CaptureNotebookSuggestion]]]
    | None = None,
) -> CaptureRouteResponse:
    roots = [_resolved_root(path) for path in await repository.list_roots()]
    notebooks = [
        CaptureNotebook(id=str(notebook.id), name=notebook.name)
        for notebook in await load_notebooks()
        if getattr(notebook, "id", None) and not getattr(notebook, "archived", False)
    ]
    result = await CaptureRoutingService(
        approved_roots=roots,
        capture_items=await repository.list_items(limit=500),
        notebooks=notebooks,
        get_speech_to_text=get_speech_to_text,
        semantic_suggester=semantic_suggester or _local_semantic_suggestions,
    ).route(payload.path)
    return CaptureRouteResponse(**result.model_dump())


@router.post("/route", response_model=CaptureRouteResponse)
async def route_capture_media(payload: CaptureRouteRequest) -> CaptureRouteResponse:
    """Preview a private voice-note route without importing or moving its source."""
    try:
        return await _route_capture_media(
            payload,
            repository=SurrealCaptureRepository(),
            get_speech_to_text=model_manager.get_speech_to_text,
            load_notebooks=Notebook.get_all,
        )
    except (CaptureRoutingError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
