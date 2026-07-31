"""Strict, redacted wire contracts for unified knowledge diagnostics."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.knowledge_engine.capabilities import (
    AuthorityKind,
    KnowledgeCapability,
)
from deeper_notebook.knowledge_engine.contracts import (
    AssetAvailability,
    AvailabilityState,
    ProjectionState,
    SourceKind,
)


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


StableKnowledgeEngineErrorCode = Literal[
    "knowledge_document_not_found",
    "knowledge_engine_disabled",
    "knowledge_engine_request_invalid",
    "knowledge_engine_unavailable",
]


class KnowledgeEngineErrorDetail(_StrictResponse):
    """Machine-readable, content-free diagnostic failure code."""

    code: StableKnowledgeEngineErrorCode


class KnowledgeEngineErrorResponse(_StrictResponse):
    """The only public diagnostic API error envelope."""

    detail: KnowledgeEngineErrorDetail


class KnowledgeSpaceResponse(_StrictResponse):
    """Logical source identity without a filesystem root or source reference."""

    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    source_kind: SourceKind
    authority_kind: AuthorityKind
    state: AvailabilityState | ProjectionState
    capabilities: list[KnowledgeCapability] = Field(default_factory=list)


class KnowledgeDocumentListResponse(_StrictResponse):
    """A summary deliberately excluding body, properties, and native identity."""

    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    relative_locator: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=4096)
    kind: str = Field(min_length=1, max_length=64)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision_id: str = Field(min_length=1, max_length=128)
    provenance: str = Field(min_length=1, max_length=128)
    authority_kind: AuthorityKind
    availability: AssetAvailability
    state: str = Field(min_length=1, max_length=32)
    capabilities: list[KnowledgeCapability] = Field(default_factory=list)


class KnowledgeDocumentDetailResponse(KnowledgeDocumentListResponse):
    """Authenticated local read projection; canonical bytes stay server-private."""

    normalized_body: str = Field(max_length=10 * 1024 * 1024)


class KnowledgeEngineStatusResponse(_StrictResponse):
    """Stable, aggregate projection counts with no source content."""

    projected: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    failed: int = Field(ge=0)


__all__ = [
    "KnowledgeDocumentDetailResponse",
    "KnowledgeDocumentListResponse",
    "KnowledgeEngineErrorDetail",
    "KnowledgeEngineErrorResponse",
    "KnowledgeEngineStatusResponse",
    "KnowledgeSpaceResponse",
]
