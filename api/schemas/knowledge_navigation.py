"""Strict, content-free HTTP schemas for global knowledge navigation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.knowledge_engine.navigation_contracts import (
    Bookmark,
    BookmarkFolder,
    CreateBookmark,
    CreateFolder,
    DeleteBookmark,
    DeleteFolder,
    HydratedBookmarkPage,
    NavigationReceipt,
    UpdateBookmark,
    UpdateFolder,
)


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BookmarkCreateRequest(CreateBookmark):
    pass


class BookmarkUpdateRequest(UpdateBookmark):
    pass


class BookmarkDeleteRequest(DeleteBookmark):
    pass


class BookmarkFolderCreateRequest(CreateFolder):
    pass


class BookmarkFolderUpdateRequest(UpdateFolder):
    pass


class BookmarkFolderDeleteRequest(DeleteFolder):
    pass


class BookmarkResponse(Bookmark):
    pass


class BookmarkListResponse(HydratedBookmarkPage):
    pass


class BookmarkFolderNode(BookmarkFolder):
    children: list["BookmarkFolderNode"] = Field(default_factory=list, max_length=256)


class BookmarkFolderTreeResponse(_StrictResponse):
    items: list[BookmarkFolderNode] = Field(default_factory=list, max_length=256)


class NavigationReceiptResponse(NavigationReceipt):
    pass


class KnowledgeNavigationErrorDetail(_StrictResponse):
    code: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )


class KnowledgeNavigationErrorResponse(_StrictResponse):
    detail: KnowledgeNavigationErrorDetail


__all__ = [
    "BookmarkCreateRequest",
    "BookmarkDeleteRequest",
    "BookmarkFolderCreateRequest",
    "BookmarkFolderDeleteRequest",
    "BookmarkFolderNode",
    "BookmarkFolderTreeResponse",
    "BookmarkFolderUpdateRequest",
    "BookmarkListResponse",
    "BookmarkResponse",
    "BookmarkUpdateRequest",
    "KnowledgeNavigationErrorResponse",
    "NavigationReceiptResponse",
]
