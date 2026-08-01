from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from deeper_notebook.knowledge_engine.navigation_contracts import (
    WORKSPACE_CAPACITY_ALLOCATOR_ID,
    BlockTarget,
    Bookmark,
    BookmarkCursor,
    BookmarkFilters,
    BookmarkFolder,
    CreateBookmark,
    CreateFolder,
    DocumentTarget,
    HydratedBookmarkPage,
    HydratedWorkspaceTab,
    KnowledgeOpenDescriptor,
    NamedKnowledgeWorkspace,
    NamedWorkspaceTab,
    NamedWorkspaceSnapshot,
    NavigationReceipt,
    WorkspaceRestorePane,
    WorkspaceRestorePlan,
    WorkspaceTarget,
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
    with pytest.raises(ValidationError):
        WorkspaceTarget(workspace_id=WORKSPACE_CAPACITY_ALLOCATOR_ID)


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


def test_named_snapshot_round_trips_a_bounded_search_mode():
    payload = _named_snapshot_payload()
    navigation = payload["navigation"]
    assert isinstance(navigation, dict)
    navigation["search_mode"] = "exact"

    snapshot = NamedWorkspaceSnapshot.model_validate(payload)

    assert snapshot.navigation.search_mode == "exact"
    assert NamedWorkspaceSnapshot.model_validate(snapshot.model_dump()) == snapshot
    navigation["search_mode"] = "unsupported"
    with pytest.raises(ValidationError):
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


def _open_descriptor() -> dict[str, str]:
    return {
        "document_id": "knowledge_engine_document:plan",
        "space_id": "knowledge_engine_space:research",
        "authority_kind": "external_read_only",
        "source_kind": "markdown",
        "title": "Research plan",
        "relative_locator": "plans/research.md",
        "legacy_note_id": "note:plan",
        "legacy_container_id": "vault_mount:research",
    }


def test_restore_plan_preserves_reconstructable_workspace_tab_state():
    tab = HydratedWorkspaceTab(
        id="tab-1",
        display_label="Research plan",
        view_mode="reading",
        target={"kind": "document", "document_id": "knowledge_engine_document:plan"},
        target_state="available",
        target_document=_open_descriptor(),
    )
    plan = WorkspaceRestorePlan(
        workspace_id="named_knowledge_workspace:desk",
        revision=3,
        active_pane_id="pane-1",
        next_id=2,
        panes={
            "pane-1": WorkspaceRestorePane(
                id="pane-1",
                active_tab_id="tab-1",
                tabs=[tab],
            )
        },
        layout={"type": "pane", "pane_id": "pane-1"},
        summary={"available": 1, "stale": 0, "unavailable": 0, "missing": 0},
    )

    assert plan.active_pane_id == "pane-1"
    assert plan.next_id == 2
    assert plan.panes["pane-1"].tabs[0].id == "tab-1"
    assert plan.panes["pane-1"].tabs[0].display_label == "Research plan"
    with pytest.raises(ValidationError, match="target states"):
        WorkspaceRestorePlan.model_validate(
            plan.model_dump()
            | {"summary": {"available": 0, "stale": 1, "unavailable": 0, "missing": 0}}
        )
    with pytest.raises(ValidationError, match="every pane exactly once"):
        WorkspaceRestorePlan.model_validate(
            plan.model_dump() | {"layout": {"type": "pane", "pane_id": "other-pane"}}
        )


def test_legacy_named_workspace_tab_derives_its_research_mode():
    document = NamedWorkspaceTab(
        id="tab-document",
        display_label="Plan",
        view_mode="reading",
        target={"kind": "document", "document_id": "knowledge_engine_document:plan"},
    )
    graph = NamedWorkspaceTab(
        id="tab-graph",
        display_label="Graph",
        view_mode="graph",
        target={"kind": "graph"},
    )

    assert document.mode == "read"
    assert graph.mode == "graph"
    incompatible = NamedWorkspaceTab(
        id="tab-incompatible",
        display_label="Plan",
        view_mode="reading",
        mode="podcast",
        target={"kind": "document", "document_id": "knowledge_engine_document:plan"},
    )
    assert incompatible.mode == "read"


def test_persistence_rows_match_migration_39_fields_and_target_kind():
    now = datetime.now(timezone.utc)
    bookmark = Bookmark(
        schema_version=1,
        id="knowledge_bookmark:plan",
        target_kind="document",
        target={"kind": "document", "document_id": "knowledge_engine_document:plan"},
        display_label="Research plan",
        position=0,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    folder = BookmarkFolder(
        schema_version=1,
        id="knowledge_bookmark_folder:research",
        name="Research",
        name_key="research",
        position=0,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    workspace = NamedKnowledgeWorkspace(
        schema_version=1,
        id="named_knowledge_workspace:desk",
        name="Desk",
        name_key="desk",
        capacity_slot=0,
        snapshot={
            "version": 1,
            "active_pane_id": "pane-1",
            "next_id": 2,
            "panes": {"pane-1": {"id": "pane-1", "active_tab_id": None, "tabs": []}},
            "layout": {"type": "pane", "pane_id": "pane-1"},
        },
        revision=1,
        created_at=now,
        updated_at=now,
    )
    receipt = NavigationReceipt(
        schema_version=1,
        operation_id="bookmark-create-1",
        operation_kind="create_bookmark",
        entity_kind="bookmark",
        payload_hash="0" * 64,
        result_status="succeeded",
        result_code="created",
        created_at=now,
        completed_at=now,
    )

    assert [item.schema_version for item in (folder, bookmark, workspace, receipt)] == [
        1,
        1,
        1,
        1,
    ]
    with pytest.raises(ValidationError, match="target_kind"):
        Bookmark.model_validate(bookmark.model_dump() | {"target_kind": "block"})


def _named_snapshot_payload() -> dict[str, object]:
    return {
        "version": 1,
        "active_pane_id": "pane-1",
        "next_id": 2,
        "panes": {
            "pane-1": {
                "id": "pane-1",
                "active_tab_id": "tab-1",
                "tabs": [
                    {
                        "id": "tab-1",
                        "display_label": "Plan",
                        "target": {
                            "kind": "document",
                            "document_id": "knowledge_engine_document:plan",
                        },
                    }
                ],
            }
        },
        "layout": {"type": "pane", "pane_id": "pane-1"},
        "navigation": {"active_draft_id": "draft-1"},
    }


@pytest.mark.parametrize(
    "field",
    [
        "active_pane_id",
        "pane_key",
        "pane_id",
        "active_tab_id",
        "tab_id",
        "layout_pane_id",
        "split_id",
        "active_draft_id",
    ],
)
def test_named_snapshot_rejects_paths_in_all_navigation_identifiers(field: str):
    path_snapshot = deepcopy(_named_snapshot_payload())
    panes = path_snapshot["panes"]
    assert isinstance(panes, dict)
    pane = panes["pane-1"]
    assert isinstance(pane, dict)
    tabs = pane["tabs"]
    assert isinstance(tabs, list)
    tab = tabs[0]
    assert isinstance(tab, dict)
    navigation = path_snapshot["navigation"]
    assert isinstance(navigation, dict)
    layout = path_snapshot["layout"]
    assert isinstance(layout, dict)

    if field == "active_pane_id":
        path_snapshot["active_pane_id"] = "/pane-1"
    elif field == "pane_key":
        panes["/pane-1"] = panes.pop("pane-1")
    elif field == "pane_id":
        pane["id"] = "/pane-1"
    elif field == "active_tab_id":
        pane["active_tab_id"] = "../tab-1"
    elif field == "tab_id":
        tab["id"] = "../tab-1"
    elif field == "layout_pane_id":
        layout["pane_id"] = "/pane-1"
    elif field == "split_id":
        path_snapshot["layout"] = {
            "type": "split",
            "id": "C:\\split-1",
            "direction": "horizontal",
            "first": {"type": "pane", "pane_id": "pane-1"},
            "second": {"type": "pane", "pane_id": "pane-1"},
        }
    else:
        navigation["active_draft_id"] = "/draft-1"

    with pytest.raises(ValidationError, match="path-free"):
        NamedWorkspaceSnapshot.model_validate(path_snapshot)


def test_named_snapshot_rejects_deep_raw_layout_before_recursive_validation():
    layout: dict[str, object] = {"type": "pane", "pane_id": "pane-1"}
    for index in range(1_100):
        layout = {
            "type": "split",
            "id": f"split-{index}",
            "direction": "horizontal",
            "first": layout,
            "second": {"type": "pane", "pane_id": "pane-1"},
        }
    payload = _named_snapshot_payload() | {"layout": layout}

    with pytest.raises(ValidationError, match="depth 64"):
        NamedWorkspaceSnapshot.model_validate(payload)


def test_cursors_must_be_canonical_and_hydrated_pages_use_the_same_decoder():
    cursor = BookmarkCursor(folder_id=None, position=0, id="knowledge_bookmark:plan")
    noncanonical = f"{cursor.encode()}=="

    with pytest.raises(ValueError, match="invalid bookmark cursor"):
        BookmarkCursor.decode(noncanonical)
    with pytest.raises(ValidationError, match="invalid bookmark cursor"):
        HydratedBookmarkPage(items=[], next_cursor=noncanonical)
