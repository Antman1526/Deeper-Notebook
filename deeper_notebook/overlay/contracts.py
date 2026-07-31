"""Strict public contracts for app-owned Markdown overlay records."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime
from itertools import islice, zip_longest
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deeper_notebook.vault.repository import VaultGraph, VaultLink

OverlaySourceAuthority = Literal["overlay"]
OverlayNoteKind = Literal["daily", "unique"]
OverlayProjectionState = Literal["pending", "current", "failed", "conflict"]
OverlayReceiptStatus = Literal[
    "started", "success", "unchanged", "conflict", "failed", "superseded"
]

_HASH = re.compile(r"^[0-9a-f]{64}$")
_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNIQUE_RELATIVE_PATH = re.compile(
    r"^Notes/(?P<timestamp>\d{8}-\d{4}) (?P<title>[^/\x00]+?)(?:-[2-9]\d*)?\.md$"
)
_OVERLAY_GRAPH_MAX_NEIGHBORS = 128
_OVERLAY_GRAPH_MAX_EDGES = 128
_OVERLAY_GRAPH_MAX_LINKS_PER_DIRECTION = 256


def _canonical_relative_path(value: str) -> str:
    parts = value.split("/")
    if (
        value.strip() != value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or "\x00" in value
        or re.match(r"^[A-Za-z]:", value)
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("path must be canonical and relative")
    return value


def _calendar_date_key(value: str) -> str:
    if not _DATE_KEY.fullmatch(value):
        raise ValueError("date_key must be an ISO calendar date")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("date_key must be an ISO calendar date") from error
    return value


def _unique_note_relative_path(value: str) -> str:
    match = _UNIQUE_RELATIVE_PATH.fullmatch(value)
    if match is None:
        raise ValueError("unique note path must use the generated filename shape")
    try:
        datetime.strptime(match.group("timestamp"), "%Y%m%d-%H%M")
    except ValueError as error:
        raise ValueError("unique note path must use a valid timestamp") from error
    return value


def _visible_title(value: str) -> str:
    normalized = value.strip()
    if not normalized or any(ord(char) < 32 for char in normalized):
        raise ValueError("title must contain visible text")
    return normalized


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class OverlaySpace(_Strict):
    id: str = Field(min_length=1, max_length=128)
    slug: Literal["default"] = "default"
    display_name: Literal["Deeper Notebook Overlay"] = "Deeper Notebook Overlay"
    root_version: Literal[1] = 1
    created_at: datetime
    updated_at: datetime


class OverlayNote(_Strict):
    id: str = Field(min_length=1, max_length=128)
    source_authority: OverlaySourceAuthority = "overlay"
    space_id: str = Field(min_length=1, max_length=128)
    projected_note_id: str = Field(min_length=1, max_length=128)
    stable_id: str = Field(min_length=20, max_length=128)
    kind: OverlayNoteKind
    date_key: str | None = Field(default=None, max_length=10)
    relative_path: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=512)
    content_hash: str = Field(min_length=64, max_length=64)
    revision: int = Field(ge=1)
    projection_state: OverlayProjectionState
    encoding: Literal["utf-8"] = "utf-8"
    newline: Literal["lf"] = "lf"
    created_at: datetime
    updated_at: datetime

    @field_validator("content_hash")
    @classmethod
    def hash_is_lower_hex(cls, value: str) -> str:
        if not _HASH.fullmatch(value):
            raise ValueError("content_hash must be lowercase SHA-256")
        return value

    @field_validator("relative_path")
    @classmethod
    def path_is_canonical_relative(cls, value: str) -> str:
        return _canonical_relative_path(value)

    @model_validator(mode="after")
    def kind_matches_date_key(self) -> OverlayNote:
        if self.kind == "daily":
            if self.date_key is None:
                raise ValueError("daily note requires an ISO date_key")
            _calendar_date_key(self.date_key)
            if self.relative_path != f"Daily/{self.date_key}.md":
                raise ValueError("daily note path must match its date_key")
        if self.kind == "unique" and self.date_key is not None:
            raise ValueError("unique note cannot have date_key")
        if self.kind == "unique":
            _unique_note_relative_path(self.relative_path)
        return self


class OverlayRevision(_Strict):
    id: str
    overlay_note_id: str
    revision: int = Field(ge=1)
    relative_snapshot: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    created_at: datetime

    @field_validator("relative_snapshot")
    @classmethod
    def snapshot_is_canonical_relative(cls, value: str) -> str:
        return _canonical_relative_path(value)


class OverlayMutationReceipt(_Strict):
    id: str
    operation_id: str
    idempotency_key: str = Field(min_length=1, max_length=128)
    overlay_note_id: str | None = None
    operation: Literal["create-daily", "create-unique", "update", "recover"]
    expected_revision: int | None = Field(default=None, ge=1)
    resulting_revision: int | None = Field(default=None, ge=1)
    before_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    after_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    status: OverlayReceiptStatus
    error_code: str | None = Field(default=None, max_length=64)
    started_at: datetime
    completed_at: datetime | None = None


class CreateDailyNote(_Strict):
    date_key: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("date_key")
    @classmethod
    def date_key_is_calendar_date(cls, value: str) -> str:
        return _calendar_date_key(value)


class CreateUniqueNote(_Strict):
    title: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("title")
    @classmethod
    def title_is_visible(cls, value: str) -> str:
        return _visible_title(value)


class UpdateOverlayNote(_Strict):
    title: str = Field(min_length=1, max_length=512)
    markdown: str = Field(max_length=10 * 1024 * 1024)
    expected_revision: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("title")
    @classmethod
    def title_is_visible(cls, value: str) -> str:
        return _visible_title(value)


class OverlayLink(VaultLink):
    """A projected link with explicit app-owned identities for navigation."""

    model_config = ConfigDict(extra="ignore", strict=True)

    source_overlay_note_id: str | None = Field(min_length=1, max_length=128)
    source_relative_path: str | None = Field(min_length=1, max_length=4096)
    target_overlay_note_id: str | None = Field(min_length=1, max_length=128)

    @field_validator("source_relative_path")
    @classmethod
    def source_path_is_canonical(cls, value: str | None) -> str | None:
        return None if value is None else _canonical_relative_path(value)


def _build_overlay_local_graph(
    *,
    overlay: OverlayNote,
    note: dict[str, Any],
    outgoing_links: Sequence[OverlayLink],
    backlinks: Sequence[OverlayLink],
) -> VaultGraph:
    center_id = overlay.projected_note_id
    nodes: dict[str, dict[str, Any]] = {
        center_id: {
            "id": center_id,
            "title": note.get("title") or overlay.title,
            "source_format": note.get("source_format") or "markdown",
            "external_state": None,
        }
    }
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str, str]] = set()

    def add_link(link: OverlayLink, *, incoming: bool) -> None:
        if not link.resolved or len(edges) >= _OVERLAY_GRAPH_MAX_EDGES:
            return
        if incoming:
            if (
                link.target_note_id != center_id
                or link.target_overlay_note_id != overlay.id
                or link.source_note_id == center_id
                or link.source_overlay_note_id is None
                or link.source_relative_path is None
            ):
                return
            source_id = link.source_note_id
            target_id = center_id
            neighbor_id = source_id
            neighbor_title = link.source_note_title
        else:
            if (
                link.source_note_id != center_id
                or link.source_overlay_note_id != overlay.id
                or link.target_note_id is None
                or link.target_note_id == center_id
                or link.target_overlay_note_id is None
            ):
                return
            source_id = center_id
            target_id = link.target_note_id
            neighbor_id = target_id
            neighbor_title = link.target_note_title

        edge_key = (source_id, target_id, link.link_kind)
        if edge_key in edge_keys:
            return
        if neighbor_id not in nodes and len(nodes) - 1 >= _OVERLAY_GRAPH_MAX_NEIGHBORS:
            return
        nodes.setdefault(
            neighbor_id,
            {
                "id": neighbor_id,
                "title": neighbor_title,
                "source_format": "markdown",
                "external_state": None,
            },
        )
        edge_keys.add(edge_key)
        edges.append(
            {
                "id": link.id,
                "source": source_id,
                "target": target_id,
                "kind": link.link_kind,
                "resolved": True,
            }
        )

    outgoing = islice(
        outgoing_links,
        _OVERLAY_GRAPH_MAX_LINKS_PER_DIRECTION,
    )
    incoming = islice(
        backlinks,
        _OVERLAY_GRAPH_MAX_LINKS_PER_DIRECTION,
    )
    for outgoing_link, incoming_link in zip_longest(outgoing, incoming):
        if outgoing_link is not None:
            add_link(outgoing_link, incoming=False)
        if incoming_link is not None:
            add_link(incoming_link, incoming=True)
        if len(edges) >= _OVERLAY_GRAPH_MAX_EDGES:
            break

    return VaultGraph(nodes=list(nodes.values()), edges=edges)


class OverlayPage(_Strict):
    knowledge_document_id: str | None = Field(
        default=None,
        pattern=r"^knowledge_engine_document:[A-Za-z0-9_-]+$",
    )
    overlay: OverlayNote
    editable_markdown: str = Field(default="", max_length=10 * 1024 * 1024)
    note: dict[str, Any]
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    outgoing_links: list[OverlayLink] = Field(default_factory=list)
    backlinks: list[OverlayLink] = Field(default_factory=list)
    graph: VaultGraph | None = None

    @model_validator(mode="after")
    def note_matches_overlay_projection(self) -> OverlayPage:
        if self.note.get("id") != self.overlay.projected_note_id:
            raise ValueError("page note must match the overlay projection")
        self.graph = _build_overlay_local_graph(
            overlay=self.overlay,
            note=self.note,
            outgoing_links=self.outgoing_links,
            backlinks=self.backlinks,
        )
        return self
