import pytest
from pydantic import ValidationError

from deeper_notebook.knowledge_engine.navigation_contracts import (
    BlockTarget,
    BookmarkCursor,
    BookmarkFilters,
    CreateBookmark,
    CreateFolder,
    DocumentTarget,
    NamedWorkspaceSnapshot,
    normalize_name,
    normalize_tags,
)


def test_targets_accept_stable_ids_and_reject_paths():
    assert DocumentTarget(
        kind="document",
        document_id="knowledge_engine_document:plan",
    ).document_id.endswith(":plan")
    with pytest.raises(ValidationError):
        DocumentTarget(kind="document", document_id="/Users/Antman/Plan.md")
    with pytest.raises(ValidationError):
        BlockTarget(
            kind="block",
            document_id="knowledge_engine_document:plan",
            block_id="../block",
        )


def test_name_and_tag_normalization_preserves_first_display_value():
    assert normalize_name("  Research   Desk  ") == (
        "Research Desk",
        "research desk",
    )
    assert normalize_tags([" Research ", "research", "RÉSUMÉ"]) == [
        "Research",
        "RÉSUMÉ",
    ]


def test_snapshot_bounds_are_preflighted():
    payload = {
        "version": 1,
        "active_pane_id": "pane-1",
        "next_id": 2,
        "panes": {
            f"pane-{index}": {"id": f"pane-{index}", "active_tab_id": None, "tabs": []}
            for index in range(33)
        },
        "layout": {"type": "pane", "pane_id": "pane-1"},
        "navigation": {},
    }
    with pytest.raises(ValidationError, match="32 panes"):
        NamedWorkspaceSnapshot.model_validate(payload)


def test_snapshot_layout_must_reference_every_pane_exactly_once():
    payload = {
        "version": 1,
        "active_pane_id": "pane-1",
        "next_id": 2,
        "panes": {"pane-1": {"id": "pane-1", "active_tab_id": None, "tabs": []}},
        "layout": {"type": "pane", "pane_id": "other-pane"},
        "navigation": {},
    }

    with pytest.raises(ValidationError, match="every pane exactly once"):
        NamedWorkspaceSnapshot.model_validate(payload)


def test_bookmark_cursor_round_trips_only_the_stable_order_tuple():
    cursor = BookmarkCursor(
        folder_id="knowledge_bookmark_folder:research",
        position=7,
        id="knowledge_bookmark:plan",
    )
    decoded = BookmarkCursor.decode(cursor.encode())

    assert decoded == cursor
    with pytest.raises(ValueError):
        BookmarkCursor.decode("a" * 513)
    with pytest.raises(ValueError):
        BookmarkCursor.decode("not-a-cursor")


def test_commands_normalize_metadata_and_filters_remain_bounded():
    folder = CreateFolder(
        operation_id="folder-create-1",
        name="  Research   Desk ",
    )
    bookmark = CreateBookmark(
        operation_id="bookmark-create-1",
        target={"kind": "document", "document_id": "knowledge_engine_document:plan"},
        display_label="  Research   Plan ",
        tags=[" Research ", "research"],
        position=0,
    )

    assert folder.name == "Research Desk"
    assert folder.name_key == "research desk"
    assert bookmark.display_label == "Research Plan"
    assert bookmark.tags == ["Research"]
    with pytest.raises(ValidationError):
        BookmarkFilters(tags=[str(index) for index in range(33)])
