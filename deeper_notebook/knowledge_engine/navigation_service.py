"""Safe hydration and orchestration for global navigation metadata."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Any

from deeper_notebook.knowledge_engine.navigation_contracts import (
    WORKSPACE_CAPACITY_ALLOCATOR_ID,
    Bookmark,
    BookmarkFilters,
    BookmarkFolder,
    BookmarkPage,
    CreateBookmark,
    CreateFolder,
    CreateWorkspace,
    DeleteBookmark,
    DeleteFolder,
    DeleteWorkspace,
    DocumentTarget,
    DuplicateWorkspace,
    HydratedBookmark,
    HydratedBookmarkPage,
    HydratedKnowledgeTarget,
    HydratedWorkspaceTab,
    KnowledgeTarget,
    NamedKnowledgeWorkspace,
    NamedKnowledgeWorkspaceSummary,
    NavigationReceipt,
    RandomNoteFilters,
    RandomNoteResult,
    UpdateBookmark,
    UpdateFolder,
    UpdateWorkspace,
    WorkspaceRestorePane,
    WorkspaceRestorePlan,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepository,
    KnowledgeNavigationRepositoryError,
)
from deeper_notebook.knowledge_engine.repository import KnowledgeRepositoryError


class KnowledgeNavigationServiceError(RuntimeError):
    """Stable, scrubbed service validation or availability failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class KnowledgeNavigationService:
    """Keep durable metadata useful when optional engine hydration is absent."""

    def __init__(
        self,
        *,
        metadata_repository: KnowledgeNavigationRepository,
        engine_repository: Any | None = None,
        random_index: Callable[[int], int] = secrets.randbelow,
    ) -> None:
        self.metadata_repository = metadata_repository
        self.engine_repository = engine_repository
        self._random_index = random_index

    async def random_note(self, filters: RandomNoteFilters) -> RandomNoteResult:
        if self.engine_repository is None:
            raise KnowledgeNavigationServiceError("knowledge_engine_unavailable")
        count = await self.metadata_repository.random_candidate_count(filters)
        if count == 0:
            return RandomNoteResult(state="empty", document=None)
        offset = self._random_index(count)
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset < count
        ):
            raise KnowledgeNavigationServiceError("random_selector_invalid")
        document = await self.metadata_repository.random_candidate_at(filters, offset)
        if document is None:
            count = await self.metadata_repository.random_candidate_count(filters)
            if count == 0:
                return RandomNoteResult(state="empty", document=None)
            document = await self.metadata_repository.random_candidate_at(
                filters, min(offset, count - 1)
            )
        if document is None:
            raise KnowledgeNavigationServiceError("knowledge_engine_unavailable")
        return RandomNoteResult(state="selected", document=document)

    async def _engine_call(self, method: str, *args: object, **kwargs: object) -> Any:
        repository = self.engine_repository
        function = getattr(repository, method, None)
        if not callable(function):
            raise KnowledgeNavigationRepositoryError("knowledge_engine_unavailable")
        try:
            return await function(*args, **kwargs)
        except LookupError:
            raise
        except (KnowledgeNavigationRepositoryError, KnowledgeRepositoryError):
            raise KnowledgeNavigationRepositoryError(
                "knowledge_engine_unavailable"
            ) from None
        except Exception:
            raise KnowledgeNavigationRepositoryError(
                "knowledge_engine_unavailable"
            ) from None

    async def _hydrate_document(self, target: Any) -> HydratedKnowledgeTarget:
        document = await self._engine_call("get_document", target.document_id)
        descriptor = await self._engine_call("open_descriptor", target.document_id)
        if descriptor is None:
            return HydratedKnowledgeTarget(target=target, state="stale")
        return HydratedKnowledgeTarget(
            target=target,
            state="available",
            document=descriptor,
        )

    async def _hydrate_block(self, target: Any) -> HydratedKnowledgeTarget:
        document = await self._engine_call("get_document", target.document_id)
        descriptor = await self._engine_call("open_descriptor", target.document_id)
        if descriptor is None:
            return HydratedKnowledgeTarget(target=target, state="stale")
        if (
            target.source_revision_id is not None
            and target.source_revision_id != document.source_revision_id
        ):
            return HydratedKnowledgeTarget(
                target=target,
                state="stale",
                document=descriptor,
            )
        block = await self._engine_call(
            "get_current_block",
            document_id=target.document_id,
            block_id=target.block_id,
            source_revision_id=document.source_revision_id,
        )
        if (
            block is None
            or getattr(block, "document_id", None) != target.document_id
            or getattr(block, "source_revision_id", None)
            != getattr(document, "source_revision_id", None)
        ):
            return HydratedKnowledgeTarget(
                target=target,
                state="stale",
                document=descriptor,
            )
        return HydratedKnowledgeTarget(
            target=target,
            state="available",
            document=descriptor,
        )

    async def _hydrate_graph(self, target: Any) -> HydratedKnowledgeTarget:
        if target.root_document_id is None:
            return HydratedKnowledgeTarget(target=target, state="available")
        root = await self._hydrate_document(
            DocumentTarget(document_id=target.root_document_id)
        )
        return HydratedKnowledgeTarget(
            target=target,
            state=root.state,
            document=root.document,
        )

    async def _hydrate_workspace(self, target: Any) -> HydratedKnowledgeTarget:
        self._require_public_workspace_id(target.workspace_id)
        await self.metadata_repository.get_workspace(target.workspace_id)
        return HydratedKnowledgeTarget(target=target, state="available")

    async def hydrate_target(self, target: KnowledgeTarget) -> HydratedKnowledgeTarget:
        try:
            if target.kind == "document":
                return await self._hydrate_document(target)
            if target.kind == "block":
                return await self._hydrate_block(target)
            if target.kind == "search":
                return HydratedKnowledgeTarget(target=target, state="available")
            if target.kind == "graph":
                return await self._hydrate_graph(target)
            return await self._hydrate_workspace(target)
        except LookupError:
            return HydratedKnowledgeTarget(target=target, state="missing")
        except KnowledgeNavigationRepositoryError:
            return HydratedKnowledgeTarget(target=target, state="unavailable")

    async def list_bookmarks(
        self, filters: BookmarkFilters, cursor: str | None, limit: int
    ) -> HydratedBookmarkPage:
        page: BookmarkPage = await self.metadata_repository.list_bookmarks(
            filters, cursor, limit
        )
        items: list[HydratedBookmark] = []
        for bookmark in page.items:
            hydrated = await self.hydrate_target(bookmark.target)
            items.append(
                HydratedBookmark(
                    **bookmark.model_dump(),
                    target_state=hydrated.state,
                    target_document=hydrated.document,
                )
            )
        return HydratedBookmarkPage(items=items, next_cursor=page.next_cursor)

    async def create_bookmark(self, command: CreateBookmark) -> Bookmark:
        return await self.metadata_repository.create_bookmark(command)

    async def update_bookmark(
        self, bookmark_id: str, command: UpdateBookmark
    ) -> Bookmark:
        return await self.metadata_repository.update_bookmark(bookmark_id, command)

    async def delete_bookmark(
        self, bookmark_id: str, command: DeleteBookmark
    ) -> NavigationReceipt:
        return await self.metadata_repository.delete_bookmark(bookmark_id, command)

    async def list_folders(self) -> list[BookmarkFolder]:
        return await self.metadata_repository.list_folders()

    async def create_folder(self, command: CreateFolder) -> BookmarkFolder:
        return await self.metadata_repository.create_folder(command)

    async def update_folder(
        self, folder_id: str, command: UpdateFolder
    ) -> BookmarkFolder:
        return await self.metadata_repository.update_folder(folder_id, command)

    async def delete_folder(
        self, folder_id: str, command: DeleteFolder
    ) -> NavigationReceipt:
        return await self.metadata_repository.delete_folder(folder_id, command)

    async def list_workspaces(self) -> list[NamedKnowledgeWorkspaceSummary]:
        return await self.metadata_repository.list_workspaces()

    async def create_workspace(
        self, command: CreateWorkspace
    ) -> NamedKnowledgeWorkspace:
        self._validate_workspace_snapshot(command.snapshot)
        return await self.metadata_repository.create_workspace(command)

    async def get_workspace(self, workspace_id: str) -> NamedKnowledgeWorkspace:
        self._require_public_workspace_id(workspace_id)
        return await self.metadata_repository.get_workspace(workspace_id)

    async def update_workspace(
        self, workspace_id: str, command: UpdateWorkspace
    ) -> NamedKnowledgeWorkspace:
        self._require_public_workspace_id(workspace_id)
        has_name = "name" in command.model_fields_set
        has_snapshot = "snapshot" in command.model_fields_set
        if has_name == has_snapshot:
            raise ValueError("workspace updates must rename or replace a snapshot")
        if command.snapshot is not None:
            self._validate_workspace_snapshot(command.snapshot)
        return await self.metadata_repository.update_workspace(workspace_id, command)

    async def duplicate_workspace(
        self, workspace_id: str, command: DuplicateWorkspace
    ) -> NamedKnowledgeWorkspace:
        self._require_public_workspace_id(workspace_id)
        return await self.metadata_repository.duplicate_workspace(workspace_id, command)

    async def delete_workspace(
        self, workspace_id: str, command: DeleteWorkspace
    ) -> NavigationReceipt:
        self._require_public_workspace_id(workspace_id)
        return await self.metadata_repository.delete_workspace(workspace_id, command)

    async def workspace_restore_plan(
        self, workspace_id: str, revision: int
    ) -> WorkspaceRestorePlan:
        self._require_public_workspace_id(workspace_id)
        workspace = await self.metadata_repository.get_workspace(workspace_id)
        if workspace.revision != revision:
            raise KnowledgeNavigationRepositoryError("workspace_revision_conflict")

        summary = {"available": 0, "stale": 0, "unavailable": 0, "missing": 0}
        panes: dict[str, WorkspaceRestorePane] = {}
        for pane_id, pane in workspace.snapshot.panes.items():
            tabs: list[HydratedWorkspaceTab] = []
            for tab in pane.tabs:
                hydrated = await self.hydrate_target(tab.target)
                summary[hydrated.state] += 1
                tabs.append(
                    HydratedWorkspaceTab(
                        id=tab.id,
                        display_label=tab.display_label,
                        view_mode=tab.view_mode,
                        target=tab.target,
                        target_state=hydrated.state,
                        target_document=hydrated.document,
                    )
                )
            panes[pane_id] = WorkspaceRestorePane(
                id=pane.id, active_tab_id=pane.active_tab_id, tabs=tabs
            )
        return WorkspaceRestorePlan(
            workspace_id=workspace.id,
            revision=workspace.revision,
            active_pane_id=workspace.snapshot.active_pane_id,
            next_id=workspace.snapshot.next_id,
            panes=panes,
            layout=workspace.snapshot.layout,
            navigation=workspace.snapshot.navigation,
            summary=summary,
        )

    @staticmethod
    def _require_public_workspace_id(workspace_id: str) -> None:
        if workspace_id == WORKSPACE_CAPACITY_ALLOCATOR_ID:
            raise LookupError("named_knowledge_workspace_not_found")

    @staticmethod
    def _validate_workspace_snapshot(snapshot: object) -> None:
        """Assert document and block tabs retain strict, unified targets."""
        panes = getattr(snapshot, "panes", {})
        for pane in panes.values():
            for tab in pane.tabs:
                target = tab.target
                if target.kind == "document" and not target.document_id:
                    raise ValueError("workspace document target is required")
                if target.kind == "block" and (
                    not target.document_id or not target.block_id
                ):
                    raise ValueError("workspace block target is required")


__all__ = ["KnowledgeNavigationService", "KnowledgeNavigationServiceError"]
