"""Read-only, bounded preview assembly for Phase-2 podcast selections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.knowledge_engine.capabilities import AuthorityKind
from deeper_notebook.knowledge_engine.contracts import KnowledgeDocument
from deeper_notebook.knowledge_engine.navigation_contracts import BookmarkFilters
from deeper_notebook.podcasts.selection_contracts import (
    AppNoteSelection,
    AppSourceSelection,
    GraphSelection,
    KnowledgeBlockSelection,
    KnowledgeCollectionSelection,
    KnowledgeDocumentSelection,
    NotebookSelection,
    PodcastSelection,
    SearchSelection,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ResolvedSelectionItem(_Strict):
    """Internal resolver result; source content is never serialized to a preview."""

    stable_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    authority_kind: AuthorityKind
    relative_locator: str | None = Field(default=None, max_length=1024)
    revision_id: str | None = Field(default=None, max_length=128)
    fingerprint: str | None = Field(default=None, max_length=128)
    content: str = Field(
        default="", max_length=10 * 1024 * 1024, exclude=True, repr=False
    )
    state: Literal[
        "included",
        "unavailable",
        "changed",
        "empty",
        "failed_parse",
        "oversize",
    ] = "included"
    reason: str = Field(default="included", min_length=1, max_length=128)


class SelectionPreviewEntry(_Strict):
    stable_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=512)
    authority_kind: AuthorityKind
    relative_locator: str | None = Field(default=None, max_length=1024)
    revision_id: str | None = Field(default=None, max_length=128)
    fingerprint: str | None = Field(default=None, max_length=128)
    state: Literal[
        "included",
        "duplicate",
        "unavailable",
        "changed",
        "empty",
        "failed_parse",
        "oversize",
    ]
    reason: str = Field(min_length=1, max_length=128)
    estimated_characters: int = Field(ge=0)


class PodcastSelectionPreview(_Strict):
    selection_fingerprint: str = Field(min_length=64, max_length=64)
    entries: list[SelectionPreviewEntry] = Field(max_length=10_000)
    included_characters: int = Field(ge=0)
    requires_batch_engine: bool
    current_worker_eligible: bool
    blocked_reasons: list[str] = Field(default_factory=list, max_length=128)


class PodcastSelectionPreparation(_Strict):
    """Ephemeral server-side input assembled from a confirmed selection."""

    preview: PodcastSelectionPreview
    content: str = Field(default="", exclude=True, repr=False)


class PodcastSelectionResolver(Protocol):
    async def resolve(
        self, selection: PodcastSelection
    ) -> list[ResolvedSelectionItem]: ...


class CompositePodcastSelectionResolver:
    """Dispatch a stable reference to the first capable read-only resolver."""

    def __init__(self, *, resolvers: tuple[PodcastSelectionResolver, ...]) -> None:
        if not resolvers:
            raise ValueError("podcast_selection_resolvers_required")
        self._resolvers = resolvers

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        for resolver in self._resolvers:
            try:
                return await resolver.resolve(selection)
            except ValueError as exc:
                if str(exc) != "podcast_selection_kind_unavailable":
                    raise
        raise ValueError("podcast_selection_kind_unavailable")


class AppNotebookContext(Protocol):
    id: str
    name: str

    async def get_context(self) -> str: ...


NotebookLoader = Callable[[str], Awaitable[AppNotebookContext | None]]


class AppNoteContext(Protocol):
    id: str
    title: str | None
    content: str | None
    canonical_external: bool | None


NoteLoader = Callable[[str], Awaitable[AppNoteContext | None]]


class AppSourceInsight(Protocol):
    content: str


class AppSourceContext(Protocol):
    id: str
    title: str | None
    full_text: str | None

    async def get_insights(self) -> list[AppSourceInsight]: ...


SourceLoader = Callable[[str], Awaitable[AppSourceContext | None]]


class AppNotePodcastSelectionResolver:
    """Resolve only app-owned notes; canonical external notes stay federated."""

    def __init__(self, *, note_loader: NoteLoader) -> None:
        self._note_loader = note_loader

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        if not isinstance(selection, AppNoteSelection):
            raise ValueError("podcast_selection_kind_unavailable")
        note = await self._note_loader(selection.note_id)
        if note is None:
            raise LookupError("podcast_note_not_found")
        if note.canonical_external:
            return [
                ResolvedSelectionItem(
                    stable_id=note.id,
                    title=note.title or "External note",
                    authority_kind="external_read_only",
                    state="unavailable",
                    reason="external_note_requires_knowledge_selection",
                )
            ]
        content = (note.content or "").strip()
        return [
            ResolvedSelectionItem(
                stable_id=note.id,
                title=note.title or "Untitled note",
                authority_kind="app_owned",
                fingerprint=hashlib.sha256(content.encode()).hexdigest(),
                content=content,
                state="included" if content else "empty",
                reason="included" if content else "note_content_empty",
            )
        ]


class AppSourcePodcastSelectionResolver:
    """Resolve app-owned source text or stored insights without asset access."""

    def __init__(self, *, source_loader: SourceLoader) -> None:
        self._source_loader = source_loader

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        if not isinstance(selection, AppSourceSelection):
            raise ValueError("podcast_selection_kind_unavailable")
        source = await self._source_loader(selection.source_id)
        if source is None:
            raise LookupError("podcast_source_not_found")
        if selection.inclusion_mode == "insights":
            content = "\n\n".join(
                insight.content.strip()
                for insight in await source.get_insights()
                if isinstance(insight.content, str) and insight.content.strip()
            )
            empty_reason = "source_insights_empty"
        else:
            content = (source.full_text or "").strip()
            empty_reason = "source_text_empty"
        return [
            ResolvedSelectionItem(
                stable_id=source.id,
                title=source.title or "Untitled source",
                authority_kind="app_owned",
                fingerprint=hashlib.sha256(content.encode()).hexdigest(),
                content=content,
                state="included" if content else "empty",
                reason="included" if content else empty_reason,
            )
        ]


class AppNotebookPodcastSelectionResolver:
    """Resolve app-owned notebooks through their existing context API only."""

    def __init__(self, *, notebook_loader: NotebookLoader) -> None:
        self._notebook_loader = notebook_loader

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        if not isinstance(selection, NotebookSelection):
            raise ValueError("podcast_selection_kind_unavailable")
        notebook = await self._notebook_loader(selection.notebook_id)
        if notebook is None:
            raise LookupError("podcast_notebook_not_found")
        content = await notebook.get_context()
        normalized_content = content.strip()
        return [
            ResolvedSelectionItem(
                stable_id=notebook.id,
                title=notebook.name,
                authority_kind="app_owned",
                fingerprint=hashlib.sha256(normalized_content.encode()).hexdigest(),
                content=normalized_content,
                state="included" if normalized_content else "empty",
                reason="included" if normalized_content else "notebook_context_empty",
            )
        ]


class KnowledgeDocumentProjectionReader(Protocol):
    """The narrow read-only projection needed for unified document selection."""

    async def get_document(self, document_id: str) -> KnowledgeDocument: ...

    async def list_documents(
        self, *, space_id: str | None, limit: int, offset: int
    ) -> list[KnowledgeDocument]: ...

    async def get_current_block_content(
        self,
        *,
        document_id: str,
        block_id: str,
        source_revision_id: str,
    ): ...


class KnowledgeEnginePodcastSelectionResolver:
    """Resolve unified document references through the engine projection only.

    This adapter deliberately receives a service-like reader rather than a vault
    path or a filesystem handle. External material therefore remains governed by
    the authority and provenance already recorded by the knowledge engine.
    """

    def __init__(self, *, engine: KnowledgeDocumentProjectionReader) -> None:
        self._engine = engine

    _SEARCH_PAGE_SIZE = 500
    _MAX_SEARCHED_DOCUMENTS = 10_000

    @staticmethod
    def _resolved_document(
        document: KnowledgeDocument, *, expected_revision_id: str | None = None
    ) -> ResolvedSelectionItem:
        revision_changed = (
            expected_revision_id is not None
            and document.source_revision_id != expected_revision_id
        )
        return ResolvedSelectionItem(
            stable_id=document.id,
            title=document.title,
            authority_kind=document.authority_kind,
            relative_locator=document.relative_locator,
            revision_id=document.source_revision_id,
            fingerprint=document.content_hash,
            content="" if revision_changed else document.normalized_body,
            state="changed" if revision_changed else "included",
            reason="source_revision_changed" if revision_changed else "included",
        )

    @staticmethod
    def _block_title(document: KnowledgeDocument) -> str:
        return f"{document.title[:480]} — selected block"

    @classmethod
    def _unavailable_block(
        cls,
        *,
        selection: KnowledgeBlockSelection,
        document: KnowledgeDocument,
        reason: str,
    ) -> ResolvedSelectionItem:
        return ResolvedSelectionItem(
            stable_id=selection.block_id,
            title=cls._block_title(document),
            authority_kind=document.authority_kind,
            relative_locator=document.relative_locator,
            revision_id=document.source_revision_id,
            fingerprint=document.content_hash,
            state="unavailable",
            reason=reason,
        )

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        if isinstance(selection, KnowledgeDocumentSelection):
            return [
                self._resolved_document(
                    await self._engine.get_document(selection.document_id),
                    expected_revision_id=selection.expected_revision_id,
                )
            ]
        if isinstance(selection, KnowledgeBlockSelection):
            document = await self._engine.get_document(selection.document_id)
            if (
                selection.expected_revision_id is not None
                and document.source_revision_id != selection.expected_revision_id
            ):
                return [
                    ResolvedSelectionItem(
                        stable_id=selection.block_id,
                        title=self._block_title(document),
                        authority_kind=document.authority_kind,
                        relative_locator=document.relative_locator,
                        revision_id=document.source_revision_id,
                        fingerprint=document.content_hash,
                        state="changed",
                        reason="source_revision_changed",
                    )
                ]
            if selection.source_start is not None:
                return [
                    self._unavailable_block(
                        selection=selection,
                        document=document,
                        reason="block_range_projection_unavailable",
                    )
                ]
            block = await self._engine.get_current_block_content(
                document_id=selection.document_id,
                block_id=selection.block_id,
                source_revision_id=document.source_revision_id,
            )
            if (
                block is None
                or getattr(block, "block_id", None) != selection.block_id
                or getattr(block, "document_id", None) != selection.document_id
                or getattr(block, "source_revision_id", None)
                != document.source_revision_id
            ):
                return [
                    self._unavailable_block(
                        selection=selection,
                        document=document,
                        reason="block_not_current",
                    )
                ]
            content = str(getattr(block, "plain_text", "")).strip()
            return [
                ResolvedSelectionItem(
                    stable_id=selection.block_id,
                    title=self._block_title(document),
                    authority_kind=document.authority_kind,
                    relative_locator=document.relative_locator,
                    revision_id=document.source_revision_id,
                    fingerprint=hashlib.sha256(content.encode()).hexdigest(),
                    content=content,
                    state="included" if content else "empty",
                    reason="included" if content else "block_content_empty",
                )
            ]
        if isinstance(selection, SearchSelection):
            if selection.search_mode == "semantic":
                raise ValueError("podcast_semantic_search_unavailable")
            space_ids = selection.space_ids or [None]
            needle = selection.query.casefold()
            results: list[ResolvedSelectionItem] = []
            searched = 0
            for space_id in sorted(space_ids, key=lambda value: value or ""):
                offset = 0
                while True:
                    documents = await self._engine.list_documents(
                        space_id=space_id,
                        limit=self._SEARCH_PAGE_SIZE,
                        offset=offset,
                    )
                    searched += len(documents)
                    if searched > self._MAX_SEARCHED_DOCUMENTS:
                        return [
                            ResolvedSelectionItem(
                                stable_id="podcast_search:bounded",
                                title="Saved search",
                                authority_kind="app_owned",
                                state="unavailable",
                                reason="search_scan_limit_exceeded",
                            )
                        ]
                    for document in documents:
                        if (
                            selection.authority_kinds
                            and document.authority_kind not in selection.authority_kinds
                        ):
                            continue
                        haystack = (
                            f"{document.title}\n{document.normalized_body}".casefold()
                        )
                        matched = (
                            document.title.casefold() == needle
                            if selection.search_mode == "exact"
                            else needle in haystack
                        )
                        if matched:
                            results.append(self._resolved_document(document))
                    if len(documents) < self._SEARCH_PAGE_SIZE:
                        break
                    offset += len(documents)
            if results:
                return results
            return [
                ResolvedSelectionItem(
                    stable_id="podcast_search:empty",
                    title="Saved search",
                    authority_kind="app_owned",
                    state="empty",
                    reason="search_no_results",
                )
            ]
        if isinstance(selection, GraphSelection):
            return [
                self._resolved_document(await self._engine.get_document(document_id))
                for document_id in selection.document_ids
            ]
        raise ValueError("podcast_selection_kind_unavailable")


class KnowledgeNavigationReader(Protocol):
    """Narrow durable-navigation read used for a saved bookmark selection."""

    async def get_bookmark(self, bookmark_id: str): ...

    async def list_folders(self): ...

    async def list_bookmarks(
        self, filters: BookmarkFilters, cursor: str | None, limit: int
    ): ...

    async def get_workspace(self, workspace_id: str): ...


class KnowledgeNavigationPodcastSelectionResolver:
    """Resolve a saved bookmark through its current unified target only."""

    _PAGE_SIZE = 100
    _MAX_COLLECTION_ITEMS = 10_000

    def __init__(
        self,
        *,
        navigation: KnowledgeNavigationReader,
        engine_resolver: KnowledgeEnginePodcastSelectionResolver,
    ) -> None:
        self._navigation = navigation
        self._engine_resolver = engine_resolver

    @staticmethod
    def _unavailable_bookmark(
        selection: KnowledgeCollectionSelection, reason: str
    ) -> list[ResolvedSelectionItem]:
        return [
            ResolvedSelectionItem(
                stable_id=selection.collection_id,
                title="Saved bookmark",
                authority_kind="app_owned",
                state="unavailable",
                reason=reason,
            )
        ]

    async def _resolve_target(
        self, selection: KnowledgeCollectionSelection, target: object
    ) -> list[ResolvedSelectionItem]:
        target_kind = getattr(target, "kind", None)
        if target_kind == "document":
            return await self._engine_resolver.resolve(
                KnowledgeDocumentSelection(document_id=target.document_id)
            )
        if target_kind == "block":
            return await self._engine_resolver.resolve(
                KnowledgeBlockSelection(
                    document_id=target.document_id,
                    block_id=target.block_id,
                    expected_revision_id=getattr(target, "source_revision_id", None),
                )
            )
        return self._unavailable_bookmark(selection, "bookmark_target_kind_unavailable")

    async def _resolve_folder(
        self, selection: KnowledgeCollectionSelection
    ) -> list[ResolvedSelectionItem]:
        folders = await self._navigation.list_folders()
        folder_ids = {getattr(folder, "id", None) for folder in folders}
        if selection.collection_id not in folder_ids:
            raise LookupError("knowledge_bookmark_folder_not_found")
        child_folders: dict[str, list[str]] = {}
        for folder in folders:
            folder_id = getattr(folder, "id", None)
            parent_id = getattr(folder, "parent_folder_id", None)
            if isinstance(folder_id, str) and isinstance(parent_id, str):
                child_folders.setdefault(parent_id, []).append(folder_id)
        folder_queue = [selection.collection_id]
        visited: set[str] = set()
        results: list[ResolvedSelectionItem] = []
        while folder_queue:
            folder_id = folder_queue.pop(0)
            if folder_id in visited:
                continue
            visited.add(folder_id)
            if len(visited) > 256:
                return self._unavailable_bookmark(
                    selection, "bookmark_folder_collection_too_large"
                )
            cursor: str | None = None
            while True:
                page = await self._navigation.list_bookmarks(
                    BookmarkFilters(folder_id=folder_id), cursor, self._PAGE_SIZE
                )
                for bookmark in page.items:
                    results.extend(
                        await self._resolve_target(
                            selection, getattr(bookmark, "target", None)
                        )
                    )
                    if len(results) > self._MAX_COLLECTION_ITEMS:
                        return self._unavailable_bookmark(
                            selection, "bookmark_collection_item_limit_exceeded"
                        )
                cursor = page.next_cursor
                if cursor is None:
                    break
            folder_queue.extend(sorted(child_folders.get(folder_id, [])))
        if results:
            return results
        return [
            ResolvedSelectionItem(
                stable_id=selection.collection_id,
                title="Saved folder",
                authority_kind="app_owned",
                state="empty",
                reason="bookmark_folder_empty",
            )
        ]

    async def _resolve_workspace(
        self, selection: KnowledgeCollectionSelection
    ) -> list[ResolvedSelectionItem]:
        workspace = await self._navigation.get_workspace(selection.collection_id)
        panes = getattr(getattr(workspace, "snapshot", None), "panes", {})
        if not isinstance(panes, dict):
            return self._unavailable_bookmark(
                selection, "workspace_snapshot_unavailable"
            )
        results: list[ResolvedSelectionItem] = []
        for pane_id in sorted(panes):
            for tab in getattr(panes[pane_id], "tabs", []):
                results.extend(
                    await self._resolve_target(selection, getattr(tab, "target", None))
                )
                if len(results) > self._MAX_COLLECTION_ITEMS:
                    return self._unavailable_bookmark(
                        selection, "workspace_collection_item_limit_exceeded"
                    )
        if results:
            return results
        return [
            ResolvedSelectionItem(
                stable_id=selection.collection_id,
                title="Saved workspace",
                authority_kind="app_owned",
                state="empty",
                reason="workspace_empty",
            )
        ]

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        if not isinstance(selection, KnowledgeCollectionSelection):
            raise ValueError("podcast_selection_kind_unavailable")
        if selection.collection_kind == "folder":
            return await self._resolve_folder(selection)
        if selection.collection_kind == "workspace":
            return await self._resolve_workspace(selection)
        if selection.collection_kind != "bookmark":
            raise ValueError("podcast_selection_kind_unavailable")
        bookmark = await self._navigation.get_bookmark(selection.collection_id)
        return await self._resolve_target(selection, getattr(bookmark, "target", None))


class PodcastSelectionService:
    """Normalize references and project resolver results without source mutation."""

    _CURRENT_WORKER_MAX_CHARACTERS = 500_000

    def __init__(self, *, resolver: PodcastSelectionResolver) -> None:
        self._resolver = resolver

    @staticmethod
    def _normalize_selection(selection: PodcastSelection) -> PodcastSelection:
        if isinstance(selection, GraphSelection):
            return selection.model_copy(
                update={"document_ids": sorted(set(selection.document_ids))}
            )
        return selection

    @staticmethod
    def _fingerprint(
        selections: Sequence[PodcastSelection],
        entries: Sequence[SelectionPreviewEntry],
    ) -> str:
        payload = {
            "selections": [
                selection.model_dump(mode="json") for selection in selections
            ],
            "resolved": [
                {
                    "stable_id": entry.stable_id,
                    "revision_id": entry.revision_id,
                    "fingerprint": entry.fingerprint,
                    "state": entry.state,
                    "reason": entry.reason,
                }
                for entry in entries
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    async def prepare(
        self, selections: Sequence[PodcastSelection]
    ) -> PodcastSelectionPreparation:
        if not isinstance(selections, Sequence) or not 1 <= len(selections) <= 128:
            raise ValueError("podcast_selection_count_invalid")

        normalized = [self._normalize_selection(selection) for selection in selections]
        entries: list[SelectionPreviewEntry] = []
        included_content: list[str] = []
        seen_fingerprints: set[str] = set()
        included_characters = 0
        for selection in normalized:
            for item in await self._resolver.resolve(selection):
                if item.state == "included":
                    duplicate = bool(
                        item.fingerprint and item.fingerprint in seen_fingerprints
                    )
                    if item.fingerprint:
                        seen_fingerprints.add(item.fingerprint)
                    state = "duplicate" if duplicate else "included"
                    reason = (
                        "duplicate_content_fingerprint" if duplicate else item.reason
                    )
                    if not duplicate:
                        included_characters += len(item.content)
                        included_content.append(item.content)
                else:
                    state = item.state
                    reason = item.reason
                entries.append(
                    SelectionPreviewEntry(
                        stable_id=item.stable_id,
                        title=item.title,
                        authority_kind=item.authority_kind,
                        relative_locator=item.relative_locator,
                        revision_id=item.revision_id,
                        fingerprint=item.fingerprint,
                        state=state,
                        reason=reason,
                        estimated_characters=len(item.content),
                    )
                )

        requires_batch_engine = (
            included_characters > self._CURRENT_WORKER_MAX_CHARACTERS
        )
        has_non_current_entry = any(
            entry.state not in {"included", "duplicate"} for entry in entries
        )
        blocked_reasons = (
            ["podcast_batch_engine_required"] if requires_batch_engine else []
        )
        if has_non_current_entry:
            blocked_reasons.append("podcast_selection_requires_refresh")
        return PodcastSelectionPreparation(
            preview=PodcastSelectionPreview(
                selection_fingerprint=self._fingerprint(normalized, entries),
                entries=entries,
                included_characters=included_characters,
                requires_batch_engine=requires_batch_engine,
                current_worker_eligible=(
                    bool(entries)
                    and not requires_batch_engine
                    and not has_non_current_entry
                ),
                blocked_reasons=blocked_reasons,
            ),
            content="\n\n".join(included_content),
        )

    async def preview(
        self, selections: Sequence[PodcastSelection]
    ) -> PodcastSelectionPreview:
        return (await self.prepare(selections)).preview


__all__ = [
    "AppNotebookContext",
    "AppNotebookPodcastSelectionResolver",
    "AppNoteContext",
    "AppNotePodcastSelectionResolver",
    "AppSourceContext",
    "AppSourceInsight",
    "AppSourcePodcastSelectionResolver",
    "CompositePodcastSelectionResolver",
    "KnowledgeDocumentProjectionReader",
    "KnowledgeEnginePodcastSelectionResolver",
    "KnowledgeNavigationPodcastSelectionResolver",
    "KnowledgeNavigationReader",
    "NotebookLoader",
    "NoteLoader",
    "SourceLoader",
    "PodcastSelectionPreparation",
    "PodcastSelectionPreview",
    "PodcastSelectionResolver",
    "PodcastSelectionService",
    "ResolvedSelectionItem",
    "SelectionPreviewEntry",
]
