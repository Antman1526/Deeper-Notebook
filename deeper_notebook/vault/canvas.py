"""Strict, read-only parser for externally owned Obsidian Canvas documents."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal

from deeper_notebook.vault.security import (
    VaultSecurityError,
    canonical_vault_relative_path,
    classify_vault_path,
)

_MAX_NODES = 500
_MAX_EDGES = 500
_MAX_TEXT_LENGTH = 16 * 1024

CanvasNodeType = Literal["text", "file", "group", "unsupported"]


class CanvasDocumentError(ValueError):
    """A Canvas document is malformed or unsafe to render."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CanvasNode:
    id: str
    type: CanvasNodeType
    x: float
    y: float
    width: float
    height: float
    text: str | None = None
    file_path: str | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class CanvasEdge:
    id: str
    from_node: str
    to_node: str
    label: str | None = None


@dataclass(frozen=True, slots=True)
class CanvasDocument:
    nodes: tuple[CanvasNode, ...]
    edges: tuple[CanvasEdge, ...]


def _required_string(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value or len(value) > _MAX_TEXT_LENGTH:
        raise CanvasDocumentError("canvas_invalid")
    return value


def _optional_string(item: dict[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > _MAX_TEXT_LENGTH:
        raise CanvasDocumentError("canvas_invalid")
    return value


def _number(item: dict[str, Any], key: str, *, positive: bool = False) -> float:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CanvasDocumentError("canvas_invalid")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        raise CanvasDocumentError("canvas_invalid")
    return number


def _canvas_file_path(item: dict[str, Any]) -> str:
    path = _required_string(item, "file")
    try:
        path = canonical_vault_relative_path(path)
    except VaultSecurityError as exc:
        raise CanvasDocumentError("canvas_invalid") from exc
    if classify_vault_path(path).kind != "markdown":
        raise CanvasDocumentError("canvas_invalid")
    return path


def _parse_node(raw: Any) -> CanvasNode:
    if not isinstance(raw, dict):
        raise CanvasDocumentError("canvas_invalid")
    node_id = _required_string(raw, "id")
    node_type = raw.get("type")
    if not isinstance(node_type, str):
        raise CanvasDocumentError("canvas_invalid")
    safe_type: CanvasNodeType = (
        node_type if node_type in {"text", "file", "group"} else "unsupported"
    )
    text = _optional_string(raw, "text") if safe_type == "text" else None
    file_path = _canvas_file_path(raw) if safe_type == "file" else None
    return CanvasNode(
        id=node_id,
        type=safe_type,
        x=_number(raw, "x"),
        y=_number(raw, "y"),
        width=_number(raw, "width", positive=True),
        height=_number(raw, "height", positive=True),
        text=text,
        file_path=file_path,
        label=_optional_string(raw, "label"),
    )


def _parse_edge(raw: Any, node_ids: set[str]) -> CanvasEdge:
    if not isinstance(raw, dict):
        raise CanvasDocumentError("canvas_invalid")
    from_node = _required_string(raw, "fromNode")
    to_node = _required_string(raw, "toNode")
    if from_node not in node_ids or to_node not in node_ids:
        raise CanvasDocumentError("canvas_invalid")
    return CanvasEdge(
        id=_required_string(raw, "id"),
        from_node=from_node,
        to_node=to_node,
        label=_optional_string(raw, "label"),
    )


def parse_canvas_document(content: bytes, *, relative_path: str) -> CanvasDocument:
    """Parse a bounded Canvas source into a safe display-only view model."""

    try:
        path = canonical_vault_relative_path(relative_path)
    except VaultSecurityError as exc:
        raise CanvasDocumentError("canvas_path_invalid") from exc
    if not path.casefold().endswith(".canvas") or classify_vault_path(path).kind != "metadata":
        raise CanvasDocumentError("canvas_path_invalid")
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanvasDocumentError("canvas_invalid") from exc
    if not isinstance(raw, dict):
        raise CanvasDocumentError("canvas_invalid")
    raw_nodes = raw.get("nodes")
    raw_edges = raw.get("edges")
    if (
        not isinstance(raw_nodes, list)
        or not isinstance(raw_edges, list)
        or len(raw_nodes) > _MAX_NODES
        or len(raw_edges) > _MAX_EDGES
    ):
        raise CanvasDocumentError("canvas_invalid")
    nodes = tuple(_parse_node(node) for node in raw_nodes)
    node_ids = {node.id for node in nodes}
    if len(node_ids) != len(nodes):
        raise CanvasDocumentError("canvas_invalid")
    edges = tuple(_parse_edge(edge, node_ids) for edge in raw_edges)
    if len({edge.id for edge in edges}) != len(edges):
        raise CanvasDocumentError("canvas_invalid")
    return CanvasDocument(nodes=nodes, edges=edges)


__all__ = [
    "CanvasDocument",
    "CanvasDocumentError",
    "CanvasEdge",
    "CanvasNode",
    "parse_canvas_document",
]
