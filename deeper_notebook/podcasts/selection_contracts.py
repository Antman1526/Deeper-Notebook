"""Path-free, user-confirmed podcast selection descriptors.

Phase 2 transports stable application and unified-knowledge references only.
Resolution is deliberately deferred to the read-only selection service so a
browser payload can never introduce an external filesystem location or source
body into podcast generation.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deeper_notebook.knowledge_engine.capabilities import AuthorityKind
from deeper_notebook.knowledge_engine.navigation_contracts import (
    BookmarkFolderId,
    BookmarkId,
    KnowledgeBlockId,
    KnowledgeDocumentId,
    KnowledgeRevisionId,
    KnowledgeSpaceId,
    NamedWorkspaceId,
)

_LEGACY_ID = r"[A-Za-z0-9_-]+"
_VISIBLE_TEXT = re.compile(r"^(?:[\\/]|[A-Za-z]:[\\/])")
_EMBEDDED_FILE_URL = re.compile(r"\bfile://[^\s,;\)\]}>]*", re.IGNORECASE)
_EMBEDDED_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/][^\s,;\)\]}>]*")
_EMBEDDED_UNC_PATH = re.compile(r"(?:^|(?<=[\s(\"'=]))(?:\\\\|//)[^\s,;\)\]}>]*")
_EMBEDDED_POSIX_PATH = re.compile(r"(?:^|(?<=[\s(\"'=:]))/(?!/)[^\s,;\)\]}>]*")

NotebookId = Annotated[
    str, Field(min_length=1, max_length=128, pattern=rf"^notebook:{_LEGACY_ID}$")
]
NoteId = Annotated[
    str, Field(min_length=1, max_length=128, pattern=rf"^note:{_LEGACY_ID}$")
]
SourceId = Annotated[
    str, Field(min_length=1, max_length=128, pattern=rf"^source:{_LEGACY_ID}$")
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _visible_query(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("query must be a string")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 512:
        raise ValueError("query must contain visible text")
    if _VISIBLE_TEXT.match(normalized) or _contains_absolute_filesystem_path(
        normalized
    ):
        raise ValueError("query must not contain an absolute path")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError("query must not contain control characters")
    return normalized


def _contains_absolute_filesystem_path(value: str) -> bool:
    return bool(
        _EMBEDDED_FILE_URL.search(value)
        or _EMBEDDED_WINDOWS_PATH.search(value)
        or _EMBEDDED_UNC_PATH.search(value)
        or _EMBEDDED_POSIX_PATH.search(value)
    )


class NotebookSelection(_Strict):
    kind: Literal["notebook"] = "notebook"
    notebook_id: NotebookId


class AppNoteSelection(_Strict):
    kind: Literal["app_note"] = "app_note"
    note_id: NoteId


class AppSourceSelection(_Strict):
    kind: Literal["app_source"] = "app_source"
    source_id: SourceId
    inclusion_mode: Literal["insights", "full"] = "full"


class KnowledgeDocumentSelection(_Strict):
    kind: Literal["knowledge_document"] = "knowledge_document"
    document_id: KnowledgeDocumentId
    expected_revision_id: KnowledgeRevisionId | None = None


class KnowledgeBlockSelection(_Strict):
    kind: Literal["knowledge_block"] = "knowledge_block"
    document_id: KnowledgeDocumentId
    block_id: KnowledgeBlockId
    expected_revision_id: KnowledgeRevisionId | None = None
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def selected_span_is_complete_and_ordered(self) -> "KnowledgeBlockSelection":
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("selected text range must include both offsets")
        if (
            self.source_start is not None
            and self.source_end is not None
            and self.source_end <= self.source_start
        ):
            raise ValueError("selected text range must have positive length")
        return self


class KnowledgeCollectionSelection(_Strict):
    kind: Literal["knowledge_collection"] = "knowledge_collection"
    collection_kind: Literal["folder", "bookmark", "workspace"]
    collection_id: BookmarkFolderId | BookmarkId | NamedWorkspaceId

    @model_validator(mode="after")
    def collection_id_matches_collection_kind(self) -> "KnowledgeCollectionSelection":
        expected_prefix = {
            "folder": "knowledge_bookmark_folder:",
            "bookmark": "knowledge_bookmark:",
            "workspace": "named_knowledge_workspace:",
        }[self.collection_kind]
        if not self.collection_id.startswith(expected_prefix):
            raise ValueError("collection_id must match collection_kind")
        return self


class SearchSelection(_Strict):
    kind: Literal["saved_search"] = "saved_search"
    query: str
    search_mode: Literal["exact", "text", "semantic"]
    space_ids: list[KnowledgeSpaceId] = Field(max_length=32)
    authority_kinds: list[AuthorityKind] = Field(max_length=2)

    @field_validator("query")
    @classmethod
    def query_is_visible(cls, value: str) -> str:
        return _visible_query(value)


class GraphSelection(_Strict):
    kind: Literal["graph_selection"] = "graph_selection"
    document_ids: list[KnowledgeDocumentId] = Field(min_length=1, max_length=128)


PodcastSelection = Annotated[
    NotebookSelection
    | AppNoteSelection
    | AppSourceSelection
    | KnowledgeDocumentSelection
    | KnowledgeBlockSelection
    | KnowledgeCollectionSelection
    | SearchSelection
    | GraphSelection,
    Field(discriminator="kind"),
]


__all__ = [
    "AppNoteSelection",
    "AppSourceSelection",
    "GraphSelection",
    "KnowledgeBlockSelection",
    "KnowledgeCollectionSelection",
    "KnowledgeDocumentSelection",
    "NotebookSelection",
    "PodcastSelection",
    "SearchSelection",
]
