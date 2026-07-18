"""Owner-operated endpoints for the private local Capture Inbox."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from api.schemas.capture import (
    CaptureItemResponse,
    CaptureRootResponse,
    CaptureScanRequest,
    CaptureScanResponse,
    RegisterCaptureRootRequest,
)
from open_notebook.capture.watcher import (
    DEFAULT_CAPTURE_ROOT,
    CaptureInboxWatcher,
    SurrealCaptureRepository,
    _resolved_root,
)

router = APIRouter(prefix="/capture", tags=["capture"])


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
    return [CaptureItemResponse(**item.model_dump()) for item in items]


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
