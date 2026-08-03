"""Strict, storage-neutral contracts for unified knowledge projections."""

from __future__ import annotations

import re
from datetime import date, datetime
from hashlib import sha256
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from deeper_notebook.knowledge_engine.capabilities import (
    AuthorityKind,
    KnowledgeCapability,
    capabilities_for,
)
from deeper_notebook.knowledge_engine.identity import (
    canonical_locator,
    engine_record_id,
)
from deeper_notebook.vault.contracts import VaultFormat

SourceKind = Literal["overlay", "obsidian", "logseq", "markdown"]
AvailabilityState = Literal["available", "unavailable", "stale", "degraded"]
ProjectionState = Literal["pending", "projecting", "ready", "failed"]
ParseState = Literal[
    "pending",
    "ready",
    "invalid",
    "unsupported",
    "conflict",
    "missing",
    "failed",
]
TaskState = Literal["open", "in_progress", "done", "cancelled", "unknown"]
DiagnosticSeverity = Literal["info", "warning", "error"]
AssetAvailability = Literal["available", "referenced", "missing", "unavailable"]

_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_DIGEST_ID = r"^[a-z][a-z0-9_]*:[A-Za-z0-9:_-]+$"
_ENGINE_ID = r"^knowledge_engine_[a-z0-9_]+:[A-Za-z0-9_-]+$"
_OVERLAY_NOTE_ID = r"^overlay_note:[A-Za-z0-9_-]+$"
_GRAPH_EDGE = (
    r"^[a-z][a-z0-9_]*:[A-Za-z0-9_-]+->"
    r"[a-z][a-z0-9_]*:[A-Za-z0-9_-]+:[a-z][a-z0-9_]*$"
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _validate_unique_capabilities(
    value: list[KnowledgeCapability],
) -> list[KnowledgeCapability]:
    if len(value) != len(set(value)):
        raise ValueError("capabilities must be unique")
    return value


def _validate_hashes(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("content hashes must be lowercase SHA-256 values")
    return value


def _validate_optional_locator(value: str | None) -> str | None:
    if value is None:
        return None
    return canonical_locator(value)


def _validate_derived_capabilities(
    value: list[KnowledgeCapability],
    authority_kind: AuthorityKind,
    resource_kind: str,
) -> None:
    if frozenset(value) != capabilities_for(authority_kind, resource_kind):
        raise ValueError("capabilities must match server-derived capabilities")


class _SourceSpan(_Strict):
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_source_span(self) -> "_SourceSpan":
        if self.source_end < self.source_start:
            raise ValueError("source_end must be greater than or equal to source_start")
        return self


class DocumentViewState(_Strict):
    kind: Literal["document"]
    mode: Literal["reading", "source", "live-preview"] = "reading"


class CollectionViewState(_Strict):
    kind: Literal["collection"]
    sort_by: Literal["title", "created_at", "updated_at"] = "updated_at"


class GraphViewState(_Strict):
    kind: Literal["graph"]
    depth: int = Field(default=1, ge=1, le=5)


ViewState = Annotated[
    DocumentViewState | CollectionViewState | GraphViewState,
    Field(discriminator="kind"),
]


class AdapterDiagnostic(_Strict):
    code: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    severity: DiagnosticSeverity
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)
    relative_context_id: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_optional_source_span(self) -> "AdapterDiagnostic":
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("diagnostic source spans must include both offsets")
        if (
            self.source_start is not None
            and self.source_end is not None
            and self.source_end < self.source_start
        ):
            raise ValueError("source_end must be greater than or equal to source_start")
        if self.relative_context_id is not None:
            canonical_locator(self.relative_context_id)
        return self


class KnowledgeSpace(_Strict):
    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=256)
    authority_kind: AuthorityKind
    source_kind: SourceKind
    format_mode: VaultFormat
    source_ref: str = Field(min_length=1, max_length=128)
    availability_state: AvailabilityState
    projection_state: ProjectionState
    adapter_version: str = Field(min_length=1, max_length=128)
    parser_version: str = Field(min_length=1, max_length=128)
    policy_version: int = Field(ge=1)
    capabilities: list[KnowledgeCapability] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    _capabilities_are_unique = field_validator("capabilities")(
        _validate_unique_capabilities
    )

    @model_validator(mode="after")
    def validate_capabilities(self) -> "KnowledgeSpace":
        _validate_derived_capabilities(
            self.capabilities, self.authority_kind, "space"
        )
        return self


class KnowledgeDocument(_Strict):
    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    source_native_id: str = Field(min_length=1, max_length=256)
    authority_kind: AuthorityKind
    relative_locator: str = Field(min_length=1, max_length=4096)
    document_kind: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=4096)
    normalized_body: str = Field(max_length=10 * 1024 * 1024)
    properties: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=10_000)
    content_hash: str = Field(pattern=_SHA256_PATTERN)
    source_revision_id: str = Field(min_length=1, max_length=128)
    provenance: str = Field(min_length=1, max_length=128)
    availability: AssetAvailability
    parse_state: ParseState
    journal_date: date | None = None
    capabilities: list[KnowledgeCapability] = Field(default_factory=list)
    created_at: datetime
    observed_at: datetime
    updated_at: datetime

    _canonical_locator = field_validator("relative_locator")(canonical_locator)
    _content_hash = field_validator("content_hash")(_validate_hashes)
    _capabilities_are_unique = field_validator("capabilities")(
        _validate_unique_capabilities
    )

    @model_validator(mode="after")
    def validate_capabilities(self) -> "KnowledgeDocument":
        _validate_derived_capabilities(
            self.capabilities, self.authority_kind, self.document_kind
        )
        return self


class KnowledgeBlock(_SourceSpan):
    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    parent_block_id: str | None = Field(default=None, min_length=1, max_length=128)
    position: int = Field(ge=0)
    source_key: str = Field(min_length=1, max_length=4096)
    block_kind: str = Field(min_length=1, max_length=128)
    markdown: str = Field(max_length=10 * 1024 * 1024)
    plain_text: str = Field(max_length=10 * 1024 * 1024)
    properties: dict[str, Any] = Field(default_factory=dict)
    raw_task_state: str | None = Field(default=None, max_length=128)
    normalized_task_state: TaskState | None = None
    heading_path: list[str] = Field(default_factory=list, max_length=256)
    source_revision_id: str = Field(min_length=1, max_length=128)
    capabilities: list[KnowledgeCapability] = Field(default_factory=list)

    _canonical_source_key = field_validator("source_key")(canonical_locator)
    _capabilities_are_unique = field_validator("capabilities")(
        _validate_unique_capabilities
    )


class KnowledgeRelation(_SourceSpan):
    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    source_document_id: str = Field(min_length=1, max_length=128)
    source_block_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_document_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_block_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_text: str = Field(min_length=1, max_length=4096)
    target_heading: str | None = Field(default=None, max_length=4096)
    target_block: str | None = Field(default=None, max_length=4096)
    alias: str | None = Field(default=None, max_length=4096)
    relation_kind: str = Field(min_length=1, max_length=64)
    resolved: bool
    source_revision_id: str = Field(min_length=1, max_length=128)


class KnowledgeTask(_SourceSpan):
    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    block_id: str | None = Field(default=None, min_length=1, max_length=128)
    raw_status: str = Field(min_length=1, max_length=128)
    normalized_status: TaskState
    scheduled: date | None = None
    due: date | None = None
    completed: date | None = None
    priority: str | None = Field(default=None, max_length=128)
    recurrence: str | None = Field(default=None, max_length=1024)
    tags: list[str] = Field(default_factory=list, max_length=10_000)
    properties: dict[str, Any] = Field(default_factory=dict)
    source_revision_id: str = Field(min_length=1, max_length=128)
    capabilities: list[KnowledgeCapability] = Field(default_factory=list)

    _capabilities_are_unique = field_validator("capabilities")(
        _validate_unique_capabilities
    )


class KnowledgeAsset(_Strict):
    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    source_document_id: str = Field(min_length=1, max_length=128)
    relative_locator: str = Field(min_length=1, max_length=4096)
    media_kind: str = Field(min_length=1, max_length=128)
    content_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    byte_size: int | None = Field(default=None, ge=0, le=100 * 1024 * 1024)
    availability: AssetAvailability
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: str = Field(min_length=1, max_length=128)
    source_revision_id: str = Field(min_length=1, max_length=128)
    capabilities: list[KnowledgeCapability] = Field(
        default_factory=lambda: sorted(capabilities_for("external_read_only", "asset"))
    )

    _canonical_locator = field_validator("relative_locator")(canonical_locator)
    _content_hash = field_validator("content_hash")(_validate_hashes)
    _capabilities_are_unique = field_validator("capabilities")(
        _validate_unique_capabilities
    )


class KnowledgeView(_Strict):
    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    authority_kind: AuthorityKind = "external_read_only"
    view_kind: Literal["document", "collection", "graph"]
    name: str = Field(min_length=1, max_length=256)
    revision: int = Field(ge=1)
    target_ids: list[str] = Field(default_factory=list, max_length=50_000)
    definition: dict[str, Any] = Field(default_factory=dict)
    view_state: ViewState
    capabilities: list[KnowledgeCapability] = Field(
        default_factory=lambda: sorted(
            capabilities_for("external_read_only", "view")
        )
    )
    created_at: datetime
    updated_at: datetime

    _capabilities_are_unique = field_validator("capabilities")(
        _validate_unique_capabilities
    )

    @field_validator("target_ids")
    @classmethod
    def validate_target_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("view target IDs must be unique")
        if any(not target.startswith("knowledge_engine_") for target in value):
            raise ValueError("view target IDs must be engine record IDs")
        return value

    @model_validator(mode="after")
    def validate_view_contract(self) -> "KnowledgeView":
        _validate_derived_capabilities(
            self.capabilities, self.authority_kind, "view"
        )
        if self.view_state.kind != self.view_kind:
            raise ValueError("view_state kind must match view_kind")
        if self.view_kind == "collection" and self.target_ids:
            raise ValueError("collection views must not include target IDs")
        if self.view_kind in {"document", "graph"} and len(self.target_ids) != 1:
            raise ValueError("document and graph views require one target ID")
        return self


class SourceRevision(_Strict):
    id: str = Field(min_length=1, max_length=128)
    space_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=_SHA256_PATTERN)
    byte_size: int = Field(ge=0, le=100 * 1024 * 1024)
    encoding: str | None = Field(default=None, max_length=64)
    newline: Literal["lf", "crlf", "mixed", "none"] | None = None
    observed_modified_ns: int = Field(ge=0)
    adapter_version: str = Field(min_length=1, max_length=128)
    parser_version: str = Field(min_length=1, max_length=128)
    parse_status: ParseState
    diagnostics: list[AdapterDiagnostic] = Field(default_factory=list, max_length=10_000)
    observed_at: datetime
    created_at: datetime

    _content_hash = field_validator("content_hash")(_validate_hashes)


class KnowledgeIdentityClaim(_Strict):
    legacy_kind: str = Field(min_length=1, max_length=64)
    legacy_id: str = Field(min_length=1, max_length=256)
    engine_kind: str = Field(min_length=1, max_length=64)
    engine_id: str = Field(min_length=1, max_length=128)
    source_revision_id: str = Field(min_length=1, max_length=128)
    claim_hash: str = Field(pattern=_SHA256_PATTERN)

    _claim_hash = field_validator("claim_hash")(_validate_hashes)


class SourceEnvelope(_Strict):
    space_id: str = Field(min_length=1, max_length=128)
    space_display_name: str = Field(min_length=1, max_length=256)
    source_ref: str = Field(min_length=1, max_length=128)
    authority_kind: AuthorityKind
    source_kind: SourceKind
    format_mode: VaultFormat
    relative_locator: str = Field(min_length=1, max_length=4096)
    canonical_bytes: bytes = Field(max_length=100 * 1024 * 1024)
    byte_size: int = Field(ge=0, le=100 * 1024 * 1024)
    declared_encoding: str | None = Field(default=None, max_length=64)
    declared_newline: Literal["lf", "crlf", "mixed", "none"] | None = None
    observed_content_hash: str = Field(pattern=_SHA256_PATTERN)
    observed_modified_ns: int = Field(ge=0)
    observed_at: datetime
    prior_revision: SourceRevision | None = None

    _canonical_locator = field_validator("relative_locator")(canonical_locator)
    _content_hash = field_validator("observed_content_hash")(_validate_hashes)

    @model_validator(mode="after")
    def validate_canonical_bytes(self) -> "SourceEnvelope":
        if self.byte_size != len(self.canonical_bytes):
            raise ValueError("byte_size must equal canonical_bytes length")
        if self.observed_content_hash != sha256(self.canonical_bytes).hexdigest():
            raise ValueError("observed_content_hash must match canonical_bytes")
        if self.prior_revision is not None:
            expected_document_id = engine_record_id(
                "document", self.space_id, self.relative_locator
            )
            if (
                self.prior_revision.space_id != self.space_id
                or self.prior_revision.document_id != expected_document_id
            ):
                raise ValueError("prior_revision must belong to the envelope document")
        return self


class KnowledgeSnapshot(_Strict):
    space: KnowledgeSpace
    document: KnowledgeDocument
    blocks: list[KnowledgeBlock] = Field(default_factory=list, max_length=50_000)
    relations: list[KnowledgeRelation] = Field(default_factory=list, max_length=100_000)
    tasks: list[KnowledgeTask] = Field(default_factory=list, max_length=50_000)
    assets: list[KnowledgeAsset] = Field(default_factory=list, max_length=50_000)
    identity_claims: list[KnowledgeIdentityClaim] = Field(
        default_factory=list, max_length=100_000
    )
    diagnostics: list[AdapterDiagnostic] = Field(default_factory=list, max_length=10_000)
    revision: SourceRevision

    @model_validator(mode="after")
    def validate_snapshot_ownership(self) -> "KnowledgeSnapshot":
        if self.document.space_id != self.space.id:
            raise ValueError("document space_id must match snapshot space")
        if self.document.authority_kind != self.space.authority_kind:
            raise ValueError("document authority_kind must match snapshot space")
        if self.revision.space_id != self.space.id:
            raise ValueError("revision space_id must match snapshot space")
        if self.revision.document_id != self.document.id:
            raise ValueError("revision document_id must match snapshot document")
        if self.document.source_revision_id != self.revision.id:
            raise ValueError("document source_revision_id must match snapshot revision")
        for block in self.blocks:
            _validate_child_ownership(
                block.space_id, block.document_id, block.source_revision_id, self
            )
            _validate_derived_capabilities(
                block.capabilities,
                self.space.authority_kind,
                self.document.document_kind,
            )
        for relation in self.relations:
            _validate_child_ownership(
                relation.space_id,
                relation.source_document_id,
                relation.source_revision_id,
                self,
            )
        for task in self.tasks:
            _validate_child_ownership(
                task.space_id, task.document_id, task.source_revision_id, self
            )
            _validate_derived_capabilities(
                task.capabilities,
                self.space.authority_kind,
                self.document.document_kind,
            )
        for asset in self.assets:
            _validate_child_ownership(
                asset.space_id,
                asset.source_document_id,
                asset.source_revision_id,
                self,
            )
            _validate_derived_capabilities(
                asset.capabilities,
                self.space.authority_kind,
                self.document.document_kind,
            )
        for claim in self.identity_claims:
            if claim.source_revision_id != self.revision.id:
                raise ValueError("identity claim source_revision_id must match snapshot")
        return self


def _validate_child_ownership(
    space_id: str,
    document_id: str,
    source_revision_id: str,
    snapshot: KnowledgeSnapshot,
) -> None:
    if space_id != snapshot.space.id:
        raise ValueError("child space_id must match snapshot space")
    if document_id != snapshot.document.id:
        raise ValueError("child document_id must match snapshot document")
    if source_revision_id != snapshot.revision.id:
        raise ValueError("child source_revision_id must match snapshot revision")


def validate_snapshot_spans(snapshot: KnowledgeSnapshot, *, source_size: int) -> None:
    """Reject byte spans that are reversed or outside the supplied source bytes."""
    if not isinstance(source_size, int) or source_size < 0:
        raise ValueError("source_size must be a non-negative integer")
    for item in (*snapshot.blocks, *snapshot.relations, *snapshot.tasks):
        if item.source_end > source_size:
            raise ValueError("source span is outside the original file bytes")
    for diagnostic in (*snapshot.revision.diagnostics, *snapshot.diagnostics):
        if diagnostic.source_end is not None and diagnostic.source_end > source_size:
            raise ValueError("diagnostic source span is outside the original file bytes")


class ProjectionReceipt(_Strict):
    operation_id: str = Field(min_length=1, max_length=256)
    space_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    source_revision_id: str = Field(min_length=1, max_length=128)
    relative_locator: str = Field(min_length=1, max_length=4096)
    input_hash: str = Field(pattern=_SHA256_PATTERN)
    output_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    adapter_version: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(ge=1)
    status: Literal["projected", "unchanged", "failed"]
    error_code: str | None = Field(default=None, max_length=128)
    started_at: datetime
    completed_at: datetime | None = None

    _canonical_locator = field_validator("relative_locator")(canonical_locator)
    _input_hash = field_validator("input_hash")(_validate_hashes)
    _output_hash = field_validator("output_hash")(_validate_hashes)


class BackfillCheckpoint(_Strict):
    space_id: str = Field(min_length=1, max_length=128)
    last_relative_locator: str | None = Field(default=None, max_length=4096)
    last_source_hash: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    status: Literal["pending", "running", "completed", "failed"]
    projected: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    failed: int = Field(ge=0)
    updated_at: datetime

    _canonical_locator = field_validator("last_relative_locator")(
        _validate_optional_locator
    )
    _source_hash = field_validator("last_source_hash")(_validate_hashes)


class ProjectionDigest(_Strict):
    space_id: str = Field(min_length=1, max_length=128)
    document_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    task_count: int = Field(ge=0)
    property_count: int = Field(default=0, ge=0)
    tag_count: int = Field(default=0, ge=0)
    asset_count: int = Field(ge=0)
    document_hashes: dict[str, str] = Field(default_factory=dict)
    identity_pairs: dict[str, str] = Field(default_factory=dict)
    outgoing_membership: dict[str, list[str]] = Field(default_factory=dict)
    backlink_membership: dict[str, list[str]] = Field(default_factory=dict)
    graph_edges: list[str] = Field(default_factory=list)
    exact_search_membership: dict[str, list[str]] = Field(default_factory=dict)
    authority_kind: AuthorityKind | None = None
    source_kind: SourceKind | None = None
    format_mode: VaultFormat | None = None
    provenance: str | None = Field(default=None, max_length=128)
    capabilities: list[KnowledgeCapability] = Field(default_factory=list)
    overlay_revision_mappings: dict[str, str] = Field(default_factory=dict)

    _capabilities_are_unique = field_validator("capabilities")(
        _validate_unique_capabilities
    )

    @field_validator("document_hashes")
    @classmethod
    def validate_document_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for locator, content_hash in value.items():
            canonical_locator(locator)
            _validate_hashes(content_hash)
            normalized[locator] = content_hash
        return dict(sorted(normalized.items()))

    @field_validator(
        "identity_pairs",
        "overlay_revision_mappings",
    )
    @classmethod
    def validate_redacted_pairs(
        cls, value: dict[str, str], info: ValidationInfo
    ) -> dict[str, str]:
        if any(
            "/" in key or "\\" in key or any(ord(char) < 32 for char in key)
            for key in value
        ):
            raise ValueError("digest mappings must be redacted stable identifiers")
        if any(
            "/" in item or "\\" in item or any(ord(char) < 32 for char in item)
            for item in value.values()
        ):
            raise ValueError("digest mappings must be redacted stable identifiers")
        for key, item in value.items():
            if info.field_name == "overlay_revision_mappings":
                valid = re.fullmatch(_OVERLAY_NOTE_ID, key) and re.fullmatch(
                    r"^knowledge_engine_revision:[A-Za-z0-9_-]+$", item
                )
            else:
                valid = re.fullmatch(_DIGEST_ID, key) and re.fullmatch(_ENGINE_ID, item)
            if not valid:
                raise ValueError("digest mappings must be redacted stable identifiers")
        return dict(sorted(value.items()))

    @field_validator(
        "outgoing_membership",
        "backlink_membership",
        "exact_search_membership",
    )
    @classmethod
    def validate_locator_membership(
        cls, value: dict[str, list[str]], info: ValidationInfo
    ) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for key, members in value.items():
            if info.field_name == "exact_search_membership":
                if re.fullmatch(_SHA256_PATTERN, key) is None:
                    raise ValueError("exact search digest keys must be query hashes")
                normalized_key = key
            else:
                normalized_key = canonical_locator(key)
            normalized[normalized_key] = sorted(
                {canonical_locator(member) for member in members}
            )
        return dict(sorted(normalized.items()))

    @field_validator("graph_edges")
    @classmethod
    def validate_graph_edges(cls, value: list[str]) -> list[str]:
        if any(
            not edge
            or len(edge) > 512
            or "/" in edge
            or "\\" in edge
            or any(ord(char) < 32 for char in edge)
            or re.fullmatch(_GRAPH_EDGE, edge) is None
            for edge in value
        ):
            raise ValueError("digest graph edges must be redacted stable identifiers")
        return sorted(set(value))

    @field_validator("capabilities")
    @classmethod
    def normalize_capabilities(
        cls, value: list[KnowledgeCapability]
    ) -> list[KnowledgeCapability]:
        return sorted(value)


class EquivalenceDifference(_Strict):
    code: str = Field(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
    legacy_value: str | int | None = None
    unified_value: str | int | None = None

    @field_validator("legacy_value", "unified_value")
    @classmethod
    def validate_redacted_value(cls, value: str | int | None) -> str | int | None:
        if not isinstance(value, str):
            return value
        if (
            not value
            or any(ord(character) < 32 for character in value)
            or "\\" in value
            or "/Users/" in value
            or "token" in value.casefold()
        ):
            raise ValueError("equivalence values must remain redacted")
        return value


class EquivalenceReport(_Strict):
    passed: bool
    differences: list[EquivalenceDifference] = Field(default_factory=list, max_length=10_000)


__all__ = [
    "AdapterDiagnostic",
    "AssetAvailability",
    "AvailabilityState",
    "BackfillCheckpoint",
    "DiagnosticSeverity",
    "EquivalenceDifference",
    "EquivalenceReport",
    "KnowledgeAsset",
    "KnowledgeBlock",
    "KnowledgeDocument",
    "KnowledgeIdentityClaim",
    "KnowledgeRelation",
    "KnowledgeSnapshot",
    "KnowledgeSpace",
    "KnowledgeTask",
    "KnowledgeView",
    "ParseState",
    "ProjectionDigest",
    "ProjectionReceipt",
    "ProjectionState",
    "SourceEnvelope",
    "SourceKind",
    "SourceRevision",
    "TaskState",
    "validate_snapshot_spans",
]
