"""Strict, content-free contracts for knowledge navigation metadata."""

from __future__ import annotations

import base64
import json
import re
import unicodedata
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deeper_notebook.knowledge_engine.capabilities import AuthorityKind
from deeper_notebook.knowledge_engine.contracts import SourceKind
from deeper_notebook.workspace.contracts import (
    KnowledgeLayoutNode,
    PaneLayoutNode,
    SplitLayoutNode,
)

_ENGINE_ID = r"[A-Za-z0-9_-]+"
_OPERATION_ID = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$"
_NAVIGATION_LOCAL_ID = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
_ABSOLUTE_PATH = re.compile(r"^(?:[\\/]|[A-Za-z]:[\\/])")
WORKSPACE_CAPACITY_ALLOCATOR_ID = "named_knowledge_workspace:capacity_allocator"

KnowledgeDocumentId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=rf"^knowledge_engine_document:{_ENGINE_ID}$",
    ),
]
KnowledgeBlockId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=rf"^knowledge_engine_block:{_ENGINE_ID}$",
    ),
]
KnowledgeRevisionId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=rf"^knowledge_engine_(?:revision|source_revision):{_ENGINE_ID}$",
    ),
]
KnowledgeSpaceId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=rf"^knowledge_engine_space:{_ENGINE_ID}$",
    ),
]
NamedWorkspaceId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=rf"^named_knowledge_workspace:{_ENGINE_ID}$",
    ),
]
BookmarkId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=rf"^knowledge_bookmark:{_ENGINE_ID}$",
    ),
]
BookmarkFolderId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=rf"^knowledge_bookmark_folder:{_ENGINE_ID}$",
    ),
]
NavigationLocalId = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=_NAVIGATION_LOCAL_ID),
]

TargetKind = Literal["document", "block", "search", "graph", "workspace"]
TargetState = Literal["available", "stale", "unavailable", "missing"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _display_text(value: str, *, label: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized or len(normalized) > limit:
        raise ValueError(f"{label} must contain visible text")
    if _ABSOLUTE_PATH.match(normalized) or "\x00" in normalized:
        raise ValueError(f"{label} must not contain an absolute path")
    if any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{label} must not contain control characters")
    return normalized


def normalize_name(value: str) -> tuple[str, str]:
    """Normalize a user-visible name while retaining its first display spelling."""
    display = _display_text(value, label="name", limit=256)
    return display, display.casefold()


def normalize_tags(values: list[str]) -> list[str]:
    """Normalize tags and keep the first display spelling for each folded key."""
    if not isinstance(values, list):
        raise ValueError("tags must be a list")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        display = _display_text(value, label="tag", limit=128)
        key = display.casefold()
        if key not in seen:
            seen.add(key)
            result.append(display)
    return result


class GraphViewport(_Strict):
    x: float = 0.0
    y: float = 0.0
    zoom: float = Field(default=1.0, ge=0.1, le=10.0)


class DocumentTarget(_Strict):
    kind: Literal["document"] = "document"
    document_id: KnowledgeDocumentId


class BlockTarget(_Strict):
    kind: Literal["block"] = "block"
    document_id: KnowledgeDocumentId
    block_id: KnowledgeBlockId
    source_revision_id: KnowledgeRevisionId | None = None


class SearchTarget(_Strict):
    kind: Literal["search"] = "search"
    query: str = Field(min_length=1, max_length=512)
    search_mode: Literal["exact", "text", "semantic"] = "text"
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    authority_kinds: list[AuthorityKind] = Field(default_factory=list, max_length=2)
    tags: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("query")
    @classmethod
    def query_is_visible(cls, value: str) -> str:
        return _display_text(value, label="query", limit=512)

    @field_validator("tags")
    @classmethod
    def tags_are_normalized(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)


class GraphTarget(_Strict):
    kind: Literal["graph"] = "graph"
    root_document_id: KnowledgeDocumentId | None = None
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    relation_kinds: list[str] = Field(default_factory=list, max_length=32)
    viewport: GraphViewport = Field(default_factory=GraphViewport)

    @field_validator("relation_kinds")
    @classmethod
    def relation_kinds_are_bounded(cls, value: list[str]) -> list[str]:
        return [_display_text(item, label="relation kind", limit=64) for item in value]


class WorkspaceTarget(_Strict):
    kind: Literal["workspace"] = "workspace"
    workspace_id: NamedWorkspaceId

    @field_validator("workspace_id")
    @classmethod
    def workspace_id_is_public(cls, value: str) -> str:
        if value == WORKSPACE_CAPACITY_ALLOCATOR_ID:
            raise ValueError("workspace target must reference a public workspace")
        return value


KnowledgeTarget = Annotated[
    DocumentTarget | BlockTarget | SearchTarget | GraphTarget | WorkspaceTarget,
    Field(discriminator="kind"),
]


class NamedWorkspaceTab(_Strict):
    id: NavigationLocalId
    target: KnowledgeTarget
    display_label: str = Field(min_length=1, max_length=512)
    view_mode: Literal["reading", "source", "live-preview", "graph"] = "reading"

    @field_validator("display_label")
    @classmethod
    def display_label_is_safe(cls, value: str) -> str:
        return _display_text(value, label="display label", limit=512)


class NamedWorkspacePane(_Strict):
    id: NavigationLocalId
    active_tab_id: NavigationLocalId | None = None
    tabs: list[NamedWorkspaceTab] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def tab_selection_is_consistent(self) -> "NamedWorkspacePane":
        tab_ids = [tab.id for tab in self.tabs]
        if len(tab_ids) != len(set(tab_ids)):
            raise ValueError("tab IDs must be unique within each pane")
        if self.active_tab_id is not None and self.active_tab_id not in tab_ids:
            raise ValueError("active tab must exist in its pane")
        return self


class NamedWorkspaceNavigation(_Strict):
    utility_mode: Literal["sources", "bookmarks", "workspaces"] = "sources"
    sidebar_visible: bool = True
    sidebar_width: int = Field(default=320, ge=240, le=640)
    active_bookmark_folder_id: BookmarkFolderId | None = None
    bookmark_tags: list[str] = Field(default_factory=list, max_length=32)
    source_tree_query: str = Field(default="", max_length=256)
    search_query: str = Field(default="", max_length=512)
    active_draft_id: NavigationLocalId | None = None
    selected_space_ids: list[KnowledgeSpaceId] = Field(
        default_factory=list, max_length=32
    )
    authority_filters: list[AuthorityKind] = Field(default_factory=list, max_length=2)
    metrics_visible: bool = True

    _bookmark_tags = field_validator("bookmark_tags")(normalize_tags)


def _require_navigation_local_id(value: object) -> None:
    if not isinstance(value, str) or re.fullmatch(_NAVIGATION_LOCAL_ID, value) is None:
        raise ValueError("navigation identifiers must be bounded and path-free")


def _validate_raw_layout_identifiers(node: object) -> None:
    stack: list[tuple[object, int]] = [(node, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > 64:
            raise ValueError("workspace layout cannot exceed depth 64")
        if not isinstance(current, dict):
            continue
        node_type = current.get("type")
        if node_type == "pane":
            _require_navigation_local_id(current.get("pane_id"))
            continue
        if node_type == "split":
            _require_navigation_local_id(current.get("id"))
            stack.append((current.get("first"), depth + 1))
            stack.append((current.get("second"), depth + 1))


def _validate_snapshot_navigation_identifiers(value: dict[object, object]) -> None:
    _require_navigation_local_id(value.get("active_pane_id"))
    panes = value.get("panes")
    if isinstance(panes, dict):
        for pane_key, pane in panes.items():
            _require_navigation_local_id(pane_key)
            if not isinstance(pane, dict):
                continue
            _require_navigation_local_id(pane.get("id"))
            active_tab_id = pane.get("active_tab_id")
            if active_tab_id is not None:
                _require_navigation_local_id(active_tab_id)
            tabs = pane.get("tabs")
            if isinstance(tabs, list):
                for tab in tabs:
                    if isinstance(tab, dict):
                        _require_navigation_local_id(tab.get("id"))
    navigation = value.get("navigation")
    if isinstance(navigation, dict) and navigation.get("active_draft_id") is not None:
        _require_navigation_local_id(navigation["active_draft_id"])
    _validate_raw_layout_identifiers(value.get("layout"))


def _validate_layout_references(
    layout: KnowledgeLayoutNode,
    pane_ids: set[str],
) -> None:
    layout_panes: list[str] = []
    split_ids: set[str] = set()
    stack: list[KnowledgeLayoutNode] = [layout]
    while stack:
        node = stack.pop()
        if isinstance(node, PaneLayoutNode):
            _require_navigation_local_id(node.pane_id)
            layout_panes.append(node.pane_id)
            continue
        _require_navigation_local_id(node.id)
        if node.id in split_ids:
            raise ValueError("split IDs must be unique")
        split_ids.add(node.id)
        stack.extend((node.first, node.second))
    if len(layout_panes) != len(set(layout_panes)):
        raise ValueError("workspace layout cannot duplicate panes")
    if set(layout_panes) != pane_ids:
        raise ValueError("workspace layout must reference every pane exactly once")


class NamedWorkspaceSnapshot(_Strict):
    version: Literal[1] = 1
    active_pane_id: NavigationLocalId
    next_id: int = Field(ge=1)
    panes: dict[NavigationLocalId, NamedWorkspacePane] = Field(max_length=32)
    layout: KnowledgeLayoutNode
    navigation: NamedWorkspaceNavigation = Field(
        default_factory=NamedWorkspaceNavigation
    )

    @model_validator(mode="before")
    @classmethod
    def snapshot_is_bounded_before_nested_validation(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        panes = value.get("panes")
        if isinstance(panes, dict) and len(panes) > 32:
            raise ValueError("workspace cannot contain more than 32 panes")
        _validate_snapshot_navigation_identifiers(value)
        return value

    @model_validator(mode="after")
    def snapshot_references_are_consistent(self) -> "NamedWorkspaceSnapshot":
        if self.active_pane_id not in self.panes:
            raise ValueError("active pane must exist in the workspace")
        total_tabs = 0
        for pane_key, pane in self.panes.items():
            if pane_key != pane.id:
                raise ValueError("pane dictionary keys must match pane IDs")
            total_tabs += len(pane.tabs)
        if total_tabs > 128:
            raise ValueError("workspace cannot contain more than 128 tabs")

        _validate_layout_references(self.layout, set(self.panes))
        return self


class BookmarkFolder(_Strict):
    schema_version: Literal[1] = 1
    id: BookmarkFolderId
    name: str = Field(min_length=1, max_length=256)
    name_key: str = Field(min_length=1, max_length=256)
    parent_folder_id: BookmarkFolderId | None = None
    position: int = Field(ge=0)
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class Bookmark(_Strict):
    schema_version: Literal[1] = 1
    id: BookmarkId
    target_kind: TargetKind
    target: KnowledgeTarget
    display_label: str = Field(min_length=1, max_length=512)
    authority_kind: AuthorityKind | None = None
    space_id: KnowledgeSpaceId | None = None
    folder_id: BookmarkFolderId | None = None
    tags: list[str] = Field(default_factory=list, max_length=32)
    position: int = Field(ge=0)
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    _display_label = field_validator("display_label")(
        lambda value: _display_text(value, label="display label", limit=512)
    )
    _tags = field_validator("tags")(normalize_tags)

    @model_validator(mode="after")
    def target_kind_matches_target(self) -> "Bookmark":
        if self.target_kind != self.target.kind:
            raise ValueError("target_kind must match target.kind")
        return self


class CreateFolder(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    name: str = Field(min_length=1, max_length=256)
    parent_folder_id: BookmarkFolderId | None = None
    position: int = Field(default=0, ge=0)
    name_key: str = Field(default="", min_length=0, max_length=256)

    @model_validator(mode="after")
    def normalized_name(self) -> "CreateFolder":
        name, name_key = normalize_name(self.name)
        if self.name_key and self.name_key != name_key:
            raise ValueError("name_key must match normalized name")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "name_key", name_key)
        return self


class UpdateFolder(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=256)
    parent_folder_id: BookmarkFolderId | None = None
    position: int | None = Field(default=None, ge=0)
    name_key: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def normalized_name(self) -> "UpdateFolder":
        if self.name is None:
            if self.name_key is not None:
                raise ValueError("name_key requires a name")
            return self
        name, name_key = normalize_name(self.name)
        if self.name_key is not None and self.name_key != name_key:
            raise ValueError("name_key must match normalized name")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "name_key", name_key)
        return self


class DeleteFolder(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    expected_revision: int = Field(ge=1)
    child_disposition: Literal["move_children", "delete_tree"] = "move_children"


class CreateBookmark(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    target: KnowledgeTarget
    display_label: str = Field(min_length=1, max_length=512)
    authority_kind: AuthorityKind | None = None
    space_id: KnowledgeSpaceId | None = None
    folder_id: BookmarkFolderId | None = None
    tags: list[str] = Field(default_factory=list, max_length=32)
    position: int = Field(default=0, ge=0)

    _display_label = field_validator("display_label")(
        lambda value: _display_text(value, label="display label", limit=512)
    )
    _tags = field_validator("tags")(normalize_tags)


class UpdateBookmark(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    expected_revision: int = Field(ge=1)
    target: KnowledgeTarget | None = None
    display_label: str | None = Field(default=None, min_length=1, max_length=512)
    authority_kind: AuthorityKind | None = None
    space_id: KnowledgeSpaceId | None = None
    folder_id: BookmarkFolderId | None = None
    tags: list[str] | None = Field(default=None, max_length=32)
    position: int | None = Field(default=None, ge=0)

    _display_label = field_validator("display_label")(
        lambda value: None
        if value is None
        else _display_text(value, label="display label", limit=512)
    )
    _tags = field_validator("tags")(
        lambda value: None if value is None else normalize_tags(value)
    )


class DeleteBookmark(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    expected_revision: int = Field(ge=1)


class BookmarkFilters(_Strict):
    folder_id: BookmarkFolderId | None = None
    tags: list[str] = Field(default_factory=list, max_length=32)
    target_kinds: list[TargetKind] = Field(default_factory=list, max_length=5)
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    authority_kinds: list[AuthorityKind] = Field(default_factory=list, max_length=2)

    _tags = field_validator("tags")(normalize_tags)


class BookmarkCursor(_Strict):
    folder_id: BookmarkFolderId | None = None
    position: int = Field(ge=0)
    id: BookmarkId

    def encode(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, value: str) -> "BookmarkCursor":
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 512
            or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
        ):
            raise ValueError("invalid bookmark cursor")
        try:
            padding = "=" * (-len(value) % 4)
            decoded = base64.urlsafe_b64decode((value + padding).encode("ascii"))
            payload = json.loads(decoded.decode("utf-8"))
            if not isinstance(payload, dict) or set(payload) != {
                "folder_id",
                "id",
                "position",
            }:
                raise ValueError
            cursor = cls.model_validate(payload)
            if cursor.encode() != value:
                raise ValueError
            return cursor
        except (
            UnicodeDecodeError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise ValueError("invalid bookmark cursor") from error


class BookmarkPage(_Strict):
    items: list[Bookmark] = Field(default_factory=list, max_length=100)
    next_cursor: str | None = Field(default=None, max_length=512)

    @field_validator("next_cursor")
    @classmethod
    def next_cursor_is_opaque_and_valid(cls, value: str | None) -> str | None:
        if value is not None:
            BookmarkCursor.decode(value)
        return value


class KnowledgeOpenDescriptor(_Strict):
    document_id: KnowledgeDocumentId
    space_id: KnowledgeSpaceId
    authority_kind: AuthorityKind
    source_kind: SourceKind
    title: str = Field(min_length=1, max_length=4096)
    relative_locator: str = Field(min_length=1, max_length=4096)
    legacy_note_id: str = Field(min_length=1, max_length=128)
    legacy_container_id: str = Field(min_length=1, max_length=128)

    @field_validator("relative_locator")
    @classmethod
    def locator_is_relative(cls, value: str) -> str:
        if (
            _ABSOLUTE_PATH.match(value)
            or "\\" in value
            or "\x00" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("relative locator must be canonical and relative")
        return value


class HydratedKnowledgeTarget(_Strict):
    target: KnowledgeTarget
    state: TargetState
    document: KnowledgeOpenDescriptor | None = None


class HydratedBookmark(Bookmark):
    target_state: TargetState
    target_document: KnowledgeOpenDescriptor | None = None


class HydratedBookmarkPage(_Strict):
    items: list[HydratedBookmark] = Field(default_factory=list, max_length=100)
    next_cursor: str | None = Field(default=None, max_length=512)

    @field_validator("next_cursor")
    @classmethod
    def next_cursor_is_opaque_and_valid(cls, value: str | None) -> str | None:
        if value is not None:
            BookmarkCursor.decode(value)
        return value


class CreateWorkspace(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    name: str = Field(min_length=1, max_length=256)
    snapshot: NamedWorkspaceSnapshot
    name_key: str = Field(default="", min_length=0, max_length=256)

    @model_validator(mode="after")
    def normalized_name(self) -> "CreateWorkspace":
        name, name_key = normalize_name(self.name)
        if self.name_key and self.name_key != name_key:
            raise ValueError("name_key must match normalized name")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "name_key", name_key)
        return self


class UpdateWorkspace(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=256)
    snapshot: NamedWorkspaceSnapshot | None = None
    name_key: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def normalized_name(self) -> "UpdateWorkspace":
        if self.name is None:
            if self.name_key is not None:
                raise ValueError("name_key requires a name")
            return self
        name, name_key = normalize_name(self.name)
        if self.name_key is not None and self.name_key != name_key:
            raise ValueError("name_key must match normalized name")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "name_key", name_key)
        return self


class DuplicateWorkspace(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    name: str = Field(min_length=1, max_length=256)
    name_key: str = Field(default="", min_length=0, max_length=256)

    @model_validator(mode="after")
    def normalized_name(self) -> "DuplicateWorkspace":
        name, name_key = normalize_name(self.name)
        if self.name_key and self.name_key != name_key:
            raise ValueError("name_key must match normalized name")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "name_key", name_key)
        return self


class DeleteWorkspace(_Strict):
    operation_id: str = Field(pattern=_OPERATION_ID)
    expected_revision: int = Field(ge=1)


class NamedKnowledgeWorkspace(_Strict):
    schema_version: Literal[1] = 1
    id: NamedWorkspaceId
    name: str = Field(min_length=1, max_length=256)
    name_key: str = Field(min_length=1, max_length=256)
    snapshot_version: Literal[1] = 1
    snapshot: NamedWorkspaceSnapshot
    capacity_slot: int = Field(ge=0, le=255)
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class NamedKnowledgeWorkspaceSummary(_Strict):
    id: NamedWorkspaceId
    name: str = Field(min_length=1, max_length=256)
    revision: int = Field(ge=1)
    updated_at: datetime


class HydratedWorkspaceTab(_Strict):
    id: NavigationLocalId
    display_label: str = Field(min_length=1, max_length=512)
    view_mode: Literal["reading", "source", "live-preview", "graph"]
    target: KnowledgeTarget
    target_state: TargetState
    target_document: KnowledgeOpenDescriptor | None = None

    _display_label = field_validator("display_label")(
        lambda value: _display_text(value, label="display label", limit=512)
    )


class WorkspaceRestorePane(_Strict):
    id: NavigationLocalId
    active_tab_id: NavigationLocalId | None = None
    tabs: list[HydratedWorkspaceTab] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def tab_selection_is_consistent(self) -> "WorkspaceRestorePane":
        tab_ids = [tab.id for tab in self.tabs]
        if len(tab_ids) != len(set(tab_ids)):
            raise ValueError("tab IDs must be unique within each pane")
        if self.active_tab_id is not None and self.active_tab_id not in tab_ids:
            raise ValueError("active tab must exist in its pane")
        return self


class WorkspaceRestorePlan(_Strict):
    workspace_id: NamedWorkspaceId
    revision: int = Field(ge=1)
    active_pane_id: NavigationLocalId
    next_id: int = Field(ge=1)
    panes: dict[NavigationLocalId, WorkspaceRestorePane] = Field(max_length=32)
    layout: KnowledgeLayoutNode
    navigation: NamedWorkspaceNavigation = Field(
        default_factory=NamedWorkspaceNavigation
    )
    summary: dict[TargetState, Annotated[int, Field(ge=0)]]

    @model_validator(mode="after")
    def summary_is_complete(self) -> "WorkspaceRestorePlan":
        expected = {"available", "stale", "unavailable", "missing"}
        if set(self.summary) != expected:
            raise ValueError("restore summary must contain every target state")
        if self.active_pane_id not in self.panes:
            raise ValueError("active pane must exist in the workspace")

        total_tabs = 0
        target_state_counts = {
            "available": 0,
            "stale": 0,
            "unavailable": 0,
            "missing": 0,
        }
        for pane_key, pane in self.panes.items():
            if pane_key != pane.id:
                raise ValueError("pane dictionary keys must match pane IDs")
            total_tabs += len(pane.tabs)
            for tab in pane.tabs:
                target_state_counts[tab.target_state] += 1
        if total_tabs > 128:
            raise ValueError("workspace cannot contain more than 128 tabs")
        if sum(self.summary.values()) != total_tabs:
            raise ValueError("restore summary total must match restored tabs")
        if self.summary != target_state_counts:
            raise ValueError("restore summary must match restored target states")
        _validate_layout_references(self.layout, set(self.panes))
        return self


class RandomNoteFilters(_Strict):
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    authority_kinds: list[AuthorityKind] = Field(default_factory=list, max_length=2)
    tags: list[str] = Field(default_factory=list, max_length=32)

    _tags = field_validator("tags")(normalize_tags)


class RandomNoteResult(_Strict):
    state: Literal["selected", "empty"]
    document: KnowledgeOpenDescriptor | None = None

    @model_validator(mode="after")
    def selection_matches_document(self) -> "RandomNoteResult":
        if (self.state == "selected") != (self.document is not None):
            raise ValueError("selected state requires a document")
        return self


class NavigationReceipt(_Strict):
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=_OPERATION_ID)
    operation_kind: str = Field(min_length=1, max_length=128)
    entity_kind: str = Field(min_length=1, max_length=128)
    entity_id: str | None = Field(default=None, min_length=1, max_length=128)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_status: Literal["succeeded", "conflict"]
    result_revision: int | None = Field(default=None, ge=1)
    result_code: str = Field(min_length=1, max_length=128)
    created_at: datetime
    completed_at: datetime


__all__ = [
    "BlockTarget",
    "Bookmark",
    "BookmarkCursor",
    "BookmarkFilters",
    "BookmarkFolder",
    "BookmarkFolderId",
    "BookmarkId",
    "BookmarkPage",
    "CreateBookmark",
    "CreateFolder",
    "CreateWorkspace",
    "DeleteBookmark",
    "DeleteFolder",
    "DeleteWorkspace",
    "DocumentTarget",
    "DuplicateWorkspace",
    "GraphTarget",
    "GraphViewport",
    "HydratedBookmark",
    "HydratedBookmarkPage",
    "HydratedKnowledgeTarget",
    "HydratedWorkspaceTab",
    "KnowledgeBlockId",
    "KnowledgeDocumentId",
    "KnowledgeOpenDescriptor",
    "KnowledgeRevisionId",
    "KnowledgeSpaceId",
    "KnowledgeTarget",
    "NamedKnowledgeWorkspace",
    "NamedKnowledgeWorkspaceSummary",
    "NamedWorkspaceId",
    "NamedWorkspaceNavigation",
    "NamedWorkspacePane",
    "NamedWorkspaceSnapshot",
    "NamedWorkspaceTab",
    "NavigationLocalId",
    "NavigationReceipt",
    "RandomNoteFilters",
    "RandomNoteResult",
    "SearchTarget",
    "TargetState",
    "UpdateBookmark",
    "UpdateFolder",
    "UpdateWorkspace",
    "WorkspaceRestorePane",
    "WorkspaceRestorePlan",
    "WorkspaceTarget",
    "WORKSPACE_CAPACITY_ALLOCATOR_ID",
    "normalize_name",
    "normalize_tags",
]
