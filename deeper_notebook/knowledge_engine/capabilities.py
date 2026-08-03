"""Server-derived, fail-closed knowledge-engine capabilities."""

from __future__ import annotations

from typing import Literal

AuthorityKind = Literal["app_owned", "external_read_only"]
KnowledgeCapability = Literal[
    "read",
    "copy_content",
    "edit_body",
    "append_body",
    "edit_properties",
    "toggle_task",
    "rename",
    "move",
    "merge",
    "archive",
    "create_child",
    "create_link",
    "bookmark",
    "cite",
]

_EXTERNAL = frozenset[KnowledgeCapability](
    {"read", "copy_content", "bookmark", "cite"}
)
_OVERLAY_NOTE = frozenset[KnowledgeCapability](
    {
        "read",
        "copy_content",
        "edit_body",
        "append_body",
        "edit_properties",
        "toggle_task",
        "rename",
        "move",
        "merge",
        "archive",
        "create_child",
        "create_link",
        "bookmark",
        "cite",
    }
)


def capabilities_for(
    authority_kind: AuthorityKind,
    document_kind: str,
) -> frozenset[KnowledgeCapability]:
    """Derive capabilities without trusting a caller-provided capability list."""
    if authority_kind == "external_read_only":
        return _EXTERNAL
    if authority_kind == "app_owned" and document_kind in {
        "note",
        "daily",
        "unique",
        "template",
    }:
        return _OVERLAY_NOTE
    if authority_kind == "app_owned":
        return _EXTERNAL
    return frozenset()
