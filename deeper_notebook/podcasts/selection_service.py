"""Read-only, bounded preview assembly for Phase-2 podcast selections."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.knowledge_engine.capabilities import AuthorityKind
from deeper_notebook.knowledge_engine.contracts import KnowledgeDocument
from deeper_notebook.podcasts.selection_contracts import (
    AppNoteSelection,
    GraphSelection,
    KnowledgeDocumentSelection,
    NotebookSelection,
    PodcastSelection,
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


class KnowledgeEnginePodcastSelectionResolver:
    """Resolve unified document references through the engine projection only.

    This adapter deliberately receives a service-like reader rather than a vault
    path or a filesystem handle. External material therefore remains governed by
    the authority and provenance already recorded by the knowledge engine.
    """

    def __init__(self, *, engine: KnowledgeDocumentProjectionReader) -> None:
        self._engine = engine

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

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        if isinstance(selection, KnowledgeDocumentSelection):
            return [
                self._resolved_document(
                    await self._engine.get_document(selection.document_id),
                    expected_revision_id=selection.expected_revision_id,
                )
            ]
        if isinstance(selection, GraphSelection):
            return [
                self._resolved_document(await self._engine.get_document(document_id))
                for document_id in selection.document_ids
            ]
        raise ValueError("podcast_selection_kind_unavailable")


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
    "CompositePodcastSelectionResolver",
    "KnowledgeDocumentProjectionReader",
    "KnowledgeEnginePodcastSelectionResolver",
    "NotebookLoader",
    "NoteLoader",
    "PodcastSelectionPreparation",
    "PodcastSelectionPreview",
    "PodcastSelectionResolver",
    "PodcastSelectionService",
    "ResolvedSelectionItem",
    "SelectionPreviewEntry",
]
