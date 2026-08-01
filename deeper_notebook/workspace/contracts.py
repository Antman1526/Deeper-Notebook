"""Durable contracts for the local knowledge workspace."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

KnowledgeViewMode = Literal["reading", "source", "live-preview", "graph", "canvas"]
KnowledgeSourceAuthority = Literal["external-vault", "overlay"]
SplitDirection = Literal["horizontal", "vertical"]
NavigationLocalId = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"),
]
KnowledgeDocumentId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^knowledge_engine_document:[A-Za-z0-9_-]+$",
    ),
]
KnowledgeSpaceId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^knowledge_engine_space:[A-Za-z0-9_-]+$",
    ),
]


class KnowledgeTabState(BaseModel):
    """A tab reference that never contains an absolute vault path."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    vault_id: str = Field(min_length=1, max_length=128)
    note_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    relative_path: str = Field(min_length=1, max_length=4096)
    view_mode: KnowledgeViewMode
    source_authority: KnowledgeSourceAuthority = "external-vault"
    knowledge_document_id: str | None = Field(default=None, max_length=128)
    graph_viewport: "GraphViewport | None" = None

    @field_validator("relative_path")
    @classmethod
    def path_must_be_vault_relative(cls, value: str) -> str:
        if (
            not value
            or value.startswith(("/", "\\"))
            or value.startswith(("//", "\\\\"))
            or re.match(r"^[A-Za-z]:", value)
        ):
            raise ValueError("note path must be relative to its vault")

        parts = value.replace("\\", "/").split("/")
        if ".." in parts:
            raise ValueError("note path must not escape its vault")
        return value


class KnowledgePaneState(BaseModel):
    """Tabs and selection state for one workspace pane."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    active_tab_id: str | None = Field(default=None, min_length=1, max_length=128)
    tabs: list[KnowledgeTabState] = Field(
        default_factory=list,
        max_length=128,
    )


class PaneLayoutNode(BaseModel):
    """A leaf in the workspace layout."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["pane"] = "pane"
    pane_id: str = Field(min_length=1, max_length=128)


class SplitLayoutNode(BaseModel):
    """A recursive split in the workspace layout."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["split"] = "split"
    id: str = Field(min_length=1, max_length=128)
    direction: SplitDirection
    first: "KnowledgeLayoutNode"
    second: "KnowledgeLayoutNode"
    first_size: float = Field(default=50.0, ge=10.0, le=90.0)

    @model_validator(mode="after")
    def layout_depth_is_bounded(self) -> "SplitLayoutNode":
        stack: list[tuple[PaneLayoutNode | SplitLayoutNode, int]] = [(self, 1)]
        while stack:
            node, depth = stack.pop()
            if depth > 64:
                raise ValueError("workspace layout cannot exceed depth 64")
            if isinstance(node, SplitLayoutNode):
                stack.append((node.first, depth + 1))
                stack.append((node.second, depth + 1))
        return self


KnowledgeLayoutNode = Annotated[
    PaneLayoutNode | SplitLayoutNode,
    Field(discriminator="type"),
]


class GraphViewport(BaseModel):
    """Persisted viewport state for an optional local graph tab."""

    model_config = ConfigDict(extra="forbid")

    x: float = 0.0
    y: float = 0.0
    zoom: float = Field(default=1.0, ge=0.1, le=10.0)


class KnowledgeWorkspaceNavigation(BaseModel):
    """Version-one-compatible navigation preferences for Current Session."""

    model_config = ConfigDict(extra="forbid")

    utility_mode: Literal["sources", "bookmarks", "workspaces"] = "sources"
    sidebar_visible: bool = True
    sidebar_width: int = Field(default=320, ge=240, le=640)
    active_bookmark_folder_id: str | None = Field(default=None, max_length=128)
    bookmark_tags: list[str] = Field(default_factory=list, max_length=32)
    source_tree_query: str = Field(default="", max_length=256)
    search_query: str = Field(default="", max_length=512)
    search_mode: Literal["exact", "text", "semantic"] = "text"
    active_draft_id: str | None = Field(default=None, max_length=128)
    selected_space_ids: list[KnowledgeSpaceId] = Field(
        default_factory=list, max_length=32
    )
    authority_filters: list[Literal["app_owned", "external_read_only"]] = Field(
        default_factory=list, max_length=2
    )
    metrics_visible: bool = True


class KnowledgeWorkspaceDocument(BaseModel):
    """The complete, validated local knowledge-workspace state."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    active_pane_id: str = Field(min_length=1, max_length=128)
    next_id: int = Field(ge=1)
    panes: dict[str, KnowledgePaneState] = Field(max_length=32)
    layout: KnowledgeLayoutNode
    navigation: KnowledgeWorkspaceNavigation = Field(
        default_factory=KnowledgeWorkspaceNavigation
    )

    @model_validator(mode="before")
    @classmethod
    def workspace_shape_is_bounded_before_nested_validation(
        cls,
        value: object,
    ) -> object:
        if not isinstance(value, dict):
            return value

        panes = value.get("panes")
        if isinstance(panes, dict):
            if len(panes) > 32:
                raise ValueError("workspace cannot contain more than 32 panes")
            total_tabs = 0
            for pane in panes.values():
                if not isinstance(pane, dict):
                    continue
                tabs = pane.get("tabs")
                if not isinstance(tabs, list):
                    continue
                total_tabs += len(tabs)
                if total_tabs > 128:
                    raise ValueError("workspace cannot contain more than 128 tabs")

        stack: list[tuple[object, int]] = [(value.get("layout"), 1)]
        while stack:
            node, depth = stack.pop()
            if depth > 64:
                raise ValueError("workspace layout cannot exceed depth 64")
            if not isinstance(node, dict) or node.get("type") != "split":
                continue
            stack.append((node.get("first"), depth + 1))
            stack.append((node.get("second"), depth + 1))
        return value

    @model_validator(mode="after")
    def workspace_references_are_consistent(self) -> "KnowledgeWorkspaceDocument":
        if len(self.panes) > 32:
            raise ValueError("workspace cannot contain more than 32 panes")

        total_tabs = 0
        for pane_key, pane in self.panes.items():
            if pane_key != pane.id:
                raise ValueError("pane dictionary keys must match pane IDs")

            tab_ids = [tab.id for tab in pane.tabs]
            total_tabs += len(tab_ids)
            if len(tab_ids) != len(set(tab_ids)):
                raise ValueError("tab IDs must be unique within each pane")
            if pane.active_tab_id is not None and pane.active_tab_id not in tab_ids:
                raise ValueError("active tab must exist in its pane")

        if total_tabs > 128:
            raise ValueError("workspace cannot contain more than 128 tabs")
        if self.active_pane_id not in self.panes:
            raise ValueError("active pane must exist in the workspace")

        layout_panes: list[str] = []
        split_ids: set[str] = set()
        stack: list[tuple[KnowledgeLayoutNode, int]] = [(self.layout, 1)]
        while stack:
            node, depth = stack.pop()
            if depth > 64:
                raise ValueError("workspace layout cannot exceed depth 64")
            if isinstance(node, PaneLayoutNode):
                layout_panes.append(node.pane_id)
                continue
            if node.id in split_ids:
                raise ValueError("split IDs must be unique")
            split_ids.add(node.id)
            stack.append((node.first, depth + 1))
            stack.append((node.second, depth + 1))

        if len(layout_panes) != len(set(layout_panes)):
            raise ValueError("workspace layout cannot duplicate panes")
        if set(layout_panes) != set(self.panes):
            raise ValueError("workspace layout must reference every pane exactly once")
        return self


def default_knowledge_workspace() -> KnowledgeWorkspaceDocument:
    """Return the initial one-pane knowledge workspace."""

    return KnowledgeWorkspaceDocument(
        active_pane_id="pane-1",
        next_id=2,
        panes={
            "pane-1": KnowledgePaneState(
                id="pane-1",
                active_tab_id=None,
                tabs=[],
            )
        },
        layout=PaneLayoutNode(pane_id="pane-1"),
    )


# Version two keeps an interaction mode separate from its content-free target.
ResearchMode = Literal["read", "write", "ask", "search", "graph", "podcast"]
DocumentRenderMode = Literal["reading", "source", "live-preview", "canvas"]


class _StrictWorkspaceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DocumentTabTarget(_StrictWorkspaceModel):
    kind: Literal["document"] = "document"
    container_id: str = Field(min_length=1, max_length=128)
    note_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    relative_locator: str = Field(min_length=1, max_length=4096)
    authority: KnowledgeSourceAuthority
    knowledge_document_id: str | None = Field(default=None, max_length=128)
    render_mode: DocumentRenderMode = "reading"

    @field_validator("relative_locator")
    @classmethod
    def locator_must_be_vault_relative(cls, value: str) -> str:
        if (
            not value
            or value.strip() != value
            or value.startswith(("/", "\\"))
            or value.startswith(("//", "\\\\"))
            or re.match(r"^[A-Za-z]:", value)
            or "\\" in value
            or "\x00" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))
        ):
            raise ValueError("note path must be relative to its vault")
        return value


class AskTabTarget(_StrictWorkspaceModel):
    kind: Literal["ask"] = "ask"
    thread_id: NavigationLocalId | None = None
    selected_document_ids: list[KnowledgeDocumentId] = Field(
        default_factory=list, max_length=128
    )


class SearchTabTarget(_StrictWorkspaceModel):
    kind: Literal["search"] = "search"
    query: str = Field(default="", max_length=512)
    search_mode: Literal["exact", "text", "semantic"] = "text"
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    authority_kinds: list[Literal["app_owned", "external_read_only"]] = Field(
        default_factory=list, max_length=2
    )


class GraphTabTarget(_StrictWorkspaceModel):
    kind: Literal["graph"] = "graph"
    root_document_id: KnowledgeDocumentId | None = None
    space_ids: list[KnowledgeSpaceId] = Field(default_factory=list, max_length=32)
    relation_kinds: list[str] = Field(default_factory=list, max_length=32)
    viewport: GraphViewport = Field(default_factory=GraphViewport)
    origin: DocumentTabTarget | None = None


class PodcastTabTarget(_StrictWorkspaceModel):
    kind: Literal["podcast"] = "podcast"
    production_id: NavigationLocalId | None = None
    seed_document_ids: list[KnowledgeDocumentId] = Field(
        default_factory=list, max_length=128
    )


KnowledgeTabTarget = Annotated[
    DocumentTabTarget
    | AskTabTarget
    | SearchTabTarget
    | GraphTabTarget
    | PodcastTabTarget,
    Field(discriminator="kind"),
]


class KnowledgeTabStateV2(_StrictWorkspaceModel):
    id: str = Field(min_length=1, max_length=128)
    mode: ResearchMode
    title: str = Field(min_length=1, max_length=512)
    target: KnowledgeTabTarget

    @model_validator(mode="after")
    def mode_matches_target(self) -> "KnowledgeTabStateV2":
        expected_kind = {
            "read": "document",
            "write": "document",
            "ask": "ask",
            "search": "search",
            "graph": "graph",
            "podcast": "podcast",
        }[self.mode]
        if self.target.kind != expected_kind:
            raise PydanticCustomError(
                "workspace_mode_target_mismatch",
                "workspace_mode_target_mismatch",
            )
        if self.mode == "write" and self.target.authority != "overlay":
            raise PydanticCustomError(
                "workspace_mode_target_mismatch",
                "workspace_mode_target_mismatch",
            )
        return self


class KnowledgePaneStateV2(_StrictWorkspaceModel):
    id: str = Field(min_length=1, max_length=128)
    active_tab_id: str | None = Field(default=None, min_length=1, max_length=128)
    tabs: list[KnowledgeTabStateV2] = Field(default_factory=list, max_length=128)

    @model_validator(mode="after")
    def tab_selection_is_consistent(self) -> "KnowledgePaneStateV2":
        tab_ids = [tab.id for tab in self.tabs]
        if len(tab_ids) != len(set(tab_ids)):
            raise ValueError("tab IDs must be unique within each pane")
        if self.active_tab_id is not None and self.active_tab_id not in tab_ids:
            raise ValueError("active tab must exist in its pane")
        return self


class KnowledgeWorkspaceDocumentV2(_StrictWorkspaceModel):
    """Validated version-two Current Session state."""

    version: Literal[2] = 2
    active_pane_id: str = Field(min_length=1, max_length=128)
    next_id: int = Field(ge=1)
    panes: dict[str, KnowledgePaneStateV2] = Field(max_length=32)
    layout: KnowledgeLayoutNode
    navigation: KnowledgeWorkspaceNavigation = Field(
        default_factory=KnowledgeWorkspaceNavigation
    )

    @model_validator(mode="before")
    @classmethod
    def workspace_shape_is_bounded_before_nested_validation(
        cls, value: object
    ) -> object:
        return _bounded_workspace_shape(value)

    @model_validator(mode="after")
    def workspace_references_are_consistent(self) -> "KnowledgeWorkspaceDocumentV2":
        _validate_workspace_references(self.active_pane_id, self.panes, self.layout)
        return self


def _bounded_workspace_shape(value: object) -> object:
    if not isinstance(value, dict):
        return value
    panes = value.get("panes")
    if isinstance(panes, dict):
        if len(panes) > 32:
            raise ValueError("workspace cannot contain more than 32 panes")
        total_tabs = 0
        for pane in panes.values():
            if not isinstance(pane, dict):
                continue
            tabs = pane.get("tabs")
            if isinstance(tabs, list):
                total_tabs += len(tabs)
                if total_tabs > 128:
                    raise ValueError("workspace cannot contain more than 128 tabs")
    stack: list[tuple[object, int]] = [(value.get("layout"), 1)]
    while stack:
        node, depth = stack.pop()
        if depth > 64:
            raise ValueError("workspace layout cannot exceed depth 64")
        if isinstance(node, dict) and node.get("type") == "split":
            stack.append((node.get("first"), depth + 1))
            stack.append((node.get("second"), depth + 1))
    return value


def _validate_workspace_references(
    active_pane_id: str,
    panes: dict[str, KnowledgePaneState | KnowledgePaneStateV2],
    layout: KnowledgeLayoutNode,
) -> None:
    if len(panes) > 32:
        raise ValueError("workspace cannot contain more than 32 panes")
    total_tabs = 0
    for pane_key, pane in panes.items():
        if pane_key != pane.id:
            raise ValueError("pane dictionary keys must match pane IDs")
        total_tabs += len(pane.tabs)
    if total_tabs > 128:
        raise ValueError("workspace cannot contain more than 128 tabs")
    if active_pane_id not in panes:
        raise ValueError("active pane must exist in the workspace")
    layout_panes: list[str] = []
    split_ids: set[str] = set()
    stack: list[tuple[KnowledgeLayoutNode, int]] = [(layout, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > 64:
            raise ValueError("workspace layout cannot exceed depth 64")
        if isinstance(node, PaneLayoutNode):
            layout_panes.append(node.pane_id)
            continue
        if node.id in split_ids:
            raise ValueError("split IDs must be unique")
        split_ids.add(node.id)
        stack.append((node.first, depth + 1))
        stack.append((node.second, depth + 1))
    if len(layout_panes) != len(set(layout_panes)):
        raise ValueError("workspace layout cannot duplicate panes")
    if set(layout_panes) != set(panes):
        raise ValueError("workspace layout must reference every pane exactly once")


def migrate_workspace_v1(
    document: KnowledgeWorkspaceDocument,
) -> KnowledgeWorkspaceDocumentV2:
    """Losslessly translate a validated v1 session into the v2 surface."""

    panes: dict[str, KnowledgePaneStateV2] = {}
    for pane_id, pane in document.panes.items():
        tabs: list[KnowledgeTabStateV2] = []
        for tab in pane.tabs:
            relative_locator = tab.relative_path.replace("\\", "/")
            if tab.view_mode == "graph":
                target: KnowledgeTabTarget = GraphTabTarget(
                    root_document_id=tab.knowledge_document_id,
                    viewport=tab.graph_viewport or GraphViewport(),
                    origin=DocumentTabTarget(
                        container_id=tab.vault_id,
                        note_id=tab.note_id,
                        title=tab.title,
                        relative_locator=relative_locator,
                        authority=tab.source_authority,
                        knowledge_document_id=tab.knowledge_document_id,
                        render_mode="reading",
                    ),
                )
                mode: ResearchMode = "graph"
            else:
                target = DocumentTabTarget(
                    container_id=tab.vault_id,
                    note_id=tab.note_id,
                    title=tab.title,
                    relative_locator=relative_locator,
                    authority=tab.source_authority,
                    knowledge_document_id=tab.knowledge_document_id,
                    render_mode=tab.view_mode,
                )
                mode = "write" if tab.source_authority == "overlay" else "read"
            tabs.append(
                KnowledgeTabStateV2(
                    id=tab.id,
                    mode=mode,
                    title=tab.title,
                    target=target,
                )
            )
        panes[pane_id] = KnowledgePaneStateV2(
            id=pane.id, active_tab_id=pane.active_tab_id, tabs=tabs
        )
    return KnowledgeWorkspaceDocumentV2(
        active_pane_id=document.active_pane_id,
        next_id=document.next_id,
        panes=panes,
        layout=document.layout,
        navigation=document.navigation,
    )


def parse_workspace_document(
    value: object,
) -> KnowledgeWorkspaceDocument | KnowledgeWorkspaceDocumentV2:
    """Dispatch strictly by persisted version without silently accepting unknown data."""

    if not isinstance(value, dict):
        raise ValueError("workspace state must be an object")
    if value.get("version") == 1:
        return KnowledgeWorkspaceDocument.model_validate(value)
    if value.get("version") == 2:
        return KnowledgeWorkspaceDocumentV2.model_validate(value)
    raise ValueError("workspace version is unsupported")


def default_knowledge_workspace_v2() -> KnowledgeWorkspaceDocumentV2:
    return migrate_workspace_v1(default_knowledge_workspace())


SplitLayoutNode.model_rebuild(
    _types_namespace={
        "GraphViewport": GraphViewport,
        "KnowledgeLayoutNode": KnowledgeLayoutNode,
    }
)
