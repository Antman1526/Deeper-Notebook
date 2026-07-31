"""Safe hydration and orchestration for global navigation metadata."""

from __future__ import annotations

from typing import Any

from deeper_notebook.knowledge_engine.navigation_contracts import (
    Bookmark,
    BookmarkFilters,
    BookmarkFolder,
    BookmarkPage,
    CreateBookmark,
    CreateFolder,
    DeleteBookmark,
    DeleteFolder,
    DocumentTarget,
    HydratedBookmark,
    HydratedBookmarkPage,
    HydratedKnowledgeTarget,
    KnowledgeTarget,
    NavigationReceipt,
    UpdateBookmark,
    UpdateFolder,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepository,
    KnowledgeNavigationRepositoryError,
)
from deeper_notebook.knowledge_engine.repository import KnowledgeRepositoryError


class KnowledgeNavigationService:
    """Keep durable metadata useful when optional engine hydration is absent."""

    def __init__(
        self,
        *,
        metadata_repository: KnowledgeNavigationRepository,
        engine_repository: Any | None = None,
    ) -> None:
        self.metadata_repository = metadata_repository
        self.engine_repository = engine_repository

    async def _engine_call(
        self, method: str, *args: object, **kwargs: object
    ) -> Any:
        repository = self.engine_repository
        function = getattr(repository, method, None)
        if not callable(function):
            raise KnowledgeNavigationRepositoryError("knowledge_engine_unavailable")
        try:
            return await function(*args, **kwargs)
        except LookupError:
            raise
        except (KnowledgeNavigationRepositoryError, KnowledgeRepositoryError):
            raise KnowledgeNavigationRepositoryError("knowledge_engine_unavailable") from None
        except Exception:
            raise KnowledgeNavigationRepositoryError("knowledge_engine_unavailable") from None

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


__all__ = ["KnowledgeNavigationService"]
