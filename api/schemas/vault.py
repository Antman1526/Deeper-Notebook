"""Strict public contracts for the read-only vault API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from deeper_notebook.vault.contracts import VaultFormat, VaultState


class _VaultSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VaultMountCreateRequest(_VaultSchema):
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=4096)
    format_mode: VaultFormat
    parent_vault_id: str | None = None
    watch_enabled: bool = True

    @field_validator("name", "path")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class VaultMountSummary(_VaultSchema):
    id: str
    name: str
    format_mode: VaultFormat
    state: VaultState
    parent_vault_id: str | None = None
    watch_enabled: bool


class VaultMountDetail(VaultMountSummary):
    """The selected owner mount may confirm its root; lists never include it."""

    root_path: str


class VaultScanResponse(_VaultSchema):
    operation_id: str
    state: VaultState
    observed: int
    parsed: int
    unchanged: int
    unsupported: int
    invalid: int
    missing: int
    embeddings_pending: int


class VaultTrustImportRequest(_VaultSchema):
    manifest_relative_path: str = Field(min_length=1, max_length=4096)


class VaultTrustImportResponse(_VaultSchema):
    changed: int
    unchanged: int
    resolved: int
    unresolved: int


class VaultTrustSummaryResponse(_VaultSchema):
    total: int
    resolved: int
    unresolved: int


class VaultErrorDetail(_VaultSchema):
    code: str


class VaultFileResponse(_VaultSchema):
    id: str
    note_id: str
    vault_id: str
    relative_path: str
    file_kind: str
    format: str
    content_hash: str | None = None
    size_bytes: int = 0
    modified_ns: int = 0
    encoding: str | None = None
    newline: Literal["lf", "crlf", "mixed", "none"] | None = None
    parse_status: str
    parse_error_code: str | None = None
    deleted_state: str


class VaultLinkResponse(_VaultSchema):
    id: str
    source_note_id: str
    source_note_title: str | None = None
    source_block_id: str | None = None
    target_note_id: str | None = None
    target_note_title: str | None = None
    target_relative_path: str | None = None
    target_block_id: str | None = None
    target_text: str
    target_heading: str | None = None
    target_block: str | None = None
    alias: str | None = None
    link_kind: str
    resolved: bool = False
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)


class VaultPageResponse(_VaultSchema):
    knowledge_document_id: str | None = Field(
        default=None,
        pattern=r"^knowledge_engine_document:[A-Za-z0-9_-]+$",
    )
    file: VaultFileResponse
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[VaultLinkResponse] = Field(default_factory=list)
    backlinks: list[VaultLinkResponse] = Field(default_factory=list)
