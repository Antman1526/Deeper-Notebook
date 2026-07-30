"""Durable contracts for the local knowledge workspace."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KnowledgeViewMode = Literal["reading", "source", "live-preview", "graph"]
KnowledgeSourceAuthority = Literal["external-vault", "overlay"]
SplitDirection = Literal["horizontal", "vertical"]


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


class KnowledgeWorkspaceDocument(BaseModel):
    """The complete, validated local knowledge-workspace state."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    active_pane_id: str = Field(min_length=1, max_length=128)
    next_id: int = Field(ge=1)
    panes: dict[str, KnowledgePaneState] = Field(max_length=32)
    layout: KnowledgeLayoutNode

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


SplitLayoutNode.model_rebuild(
    _types_namespace={"KnowledgeLayoutNode": KnowledgeLayoutNode}
)
