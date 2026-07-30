"""Strict wire contracts for the app-owned overlay API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from deeper_notebook.overlay.contracts import (
    CreateDailyNote,
    CreateUniqueNote,
    OverlayMutationReceipt,
    OverlayNote,
    OverlayNoteKind,
    OverlayPage,
    OverlayProjectionState,
    OverlayReceiptStatus,
    OverlayRevision,
    OverlaySourceAuthority,
    OverlaySpace,
    UpdateOverlayNote,
)


class OverlayRootResponse(BaseModel):
    """Public logical identity; filesystem layout is intentionally absent."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: Literal["overlay_space:default"] = "overlay_space:default"
    source_authority: Literal["overlay"] = "overlay"


__all__ = [
    "CreateDailyNote",
    "CreateUniqueNote",
    "OverlayMutationReceipt",
    "OverlayNote",
    "OverlayNoteKind",
    "OverlayPage",
    "OverlayProjectionState",
    "OverlayReceiptStatus",
    "OverlayRevision",
    "OverlayRootResponse",
    "OverlaySourceAuthority",
    "OverlaySpace",
    "UpdateOverlayNote",
]
