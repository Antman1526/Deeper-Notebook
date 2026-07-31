from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from surrealdb import AsyncSurreal, RecordID

from deeper_notebook.knowledge_engine.navigation_contracts import (
    BookmarkCursor,
    BookmarkFilters,
    CreateBookmark,
    CreateFolder,
    CreateWorkspace,
    DeleteBookmark,
    DeleteFolder,
    DeleteWorkspace,
    DuplicateWorkspace,
    RandomNoteFilters,
    UpdateBookmark,
    UpdateFolder,
    UpdateWorkspace,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepository,
    KnowledgeNavigationRepositoryError,
)


async def seed_workspace_rows(database: AsyncSurreal, count: int) -> None:
    """Insert synthetic metadata-only rows to exercise repository cap guards."""
    statements = []
    for index in range(count):
        statements.append(
            "CREATE named_knowledge_workspace:seed_"
            + str(index)
            + " CONTENT { schema_version: 1, name: 'Seed "
            + str(index)
            + "', name_key: 'seed "
            + str(index)
            + "', snapshot_version: 1, snapshot: {}, revision: 1, "
            "created_at: time::now(), updated_at: time::now() };"
        )
    await database.query("\n".join(statements))


def create_bookmark_command(*, operation_id: str = "bookmark-create") -> CreateBookmark:
    return CreateBookmark(
        operation_id=operation_id,
        target={"kind": "document", "document_id": "knowledge_engine_document:plan"},
        display_label="Research plan",
        tags=["Research"],
    )


def update_bookmark_command(*, expected_revision: int) -> UpdateBookmark:
    return UpdateBookmark(
        operation_id="bookmark-update",
        expected_revision=expected_revision,
        display_label="Updated research plan",
    )


def create_folder_command(
    *,
    operation_id: str = "folder-create",
    name: str = "Research",
    parent_folder_id: str | None = None,
) -> CreateFolder:
    return CreateFolder(
        operation_id=operation_id,
        name=name,
        parent_folder_id=parent_folder_id,
    )


def workspace_snapshot() -> dict:
    return {
        "version": 1,
        "active_pane_id": "pane-1",
        "next_id": 2,
        "panes": {"pane-1": {"id": "pane-1", "active_tab_id": None, "tabs": []}},
        "layout": {"type": "pane", "pane_id": "pane-1"},
    }


class FakeConnection:
    """Synthetic transaction oracle for the repository's bound query variables."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, dict]] = {
            "knowledge_bookmark": {},
            "knowledge_bookmark_folder": {},
            "named_knowledge_workspace": {},
        }
        self.receipts: dict[str, dict] = {}
        self.fail_after_receipt = False
        self.remove_parent_before_mutation: str | None = None
        self.statements: list[str] = []

    @property
    def committed_receipts(self) -> list[dict]:
        return list(self.receipts.values())

    @asynccontextmanager
    async def factory(self):
        yield self

    async def query(self, statement: str, variables: dict | None = None):
        self.statements.append(statement)
        variables = variables or {}
        if variables.get("mutation"):
            return self._mutation(variables)
        if (
            "FROM knowledge_navigation_operation_receipt WHERE operation_id"
            in statement
        ):
            receipt = self.receipts.get(variables["operation_id"])
            return [deepcopy(receipt)] if receipt is not None else []
        if variables.get("read") == "folder_parent":
            return [
                self.rows["knowledge_bookmark_folder"].get(str(variables["folder_id"]))
            ]
        if (
            statement.strip()
            == "SELECT id, parent_folder_id FROM knowledge_bookmark_folder;"
        ):
            return list(self.rows["knowledge_bookmark_folder"].values())
        if "SELECT * FROM $entity_id LIMIT 1" in statement:
            entity_id = str(variables["entity_id"])
            for table in self.rows.values():
                if entity_id in table:
                    return [deepcopy(table[entity_id])]
            return []
        raise AssertionError(f"unexpected fake query: {statement}")

    def _mutation(self, variables: dict):
        staged_rows = deepcopy(self.rows)
        staged_receipts = deepcopy(self.receipts)
        if self.remove_parent_before_mutation is not None:
            staged_rows["knowledge_bookmark_folder"].pop(
                self.remove_parent_before_mutation, None
            )
            self.remove_parent_before_mutation = None
        operation_id = variables["operation_id"]
        prior = staged_receipts.get(operation_id)
        if prior is not None:
            if prior["payload_hash"] != variables["payload_hash"]:
                return [{"error": "operation_conflict"}]
            return [
                {
                    "prior": prior,
                    "entity": self._entity_for(prior, staged_rows),
                    "receipt": prior,
                }
            ]

        table = variables["table"]
        entity_id = str(variables["entity_id"])
        workspace_limit = variables.get("workspace_limit")
        if (
            table == "named_knowledge_workspace"
            and workspace_limit is not None
            and len(staged_rows[table]) >= workspace_limit
        ):
            return [{"error": "workspace_limit_reached"}]
        current = staged_rows[table].get(entity_id)
        expected = variables.get("expected_revision")
        if expected is not None and (
            current is None or current["revision"] != expected
        ):
            return [{"error": "revision_conflict"}]
        folder_relation_id = variables.get("folder_relation_id")
        if (
            folder_relation_id is not None
            and folder_relation_id not in staged_rows["knowledge_bookmark_folder"]
        ):
            return [{"error": "folder_parent_not_found"}]

        entity = deepcopy(variables.get("entity") or current)
        if variables["mutation"] == "delete":
            if current is None:
                return [{"error": "not_found"}]
            del staged_rows[table][entity_id]
            entity = None
        else:
            entity["id"] = entity_id
            staged_rows[table][entity_id] = entity

        receipt = deepcopy(variables["receipt"])
        staged_receipts[operation_id] = receipt
        if self.fail_after_receipt:
            raise RuntimeError("simulated database failure after receipt staging")
        self.rows = staged_rows
        self.receipts = staged_receipts
        return [{"prior": [], "entity": entity, "receipt": receipt}]

    @staticmethod
    def _entity_for(receipt: dict, rows: dict[str, dict[str, dict]]) -> dict | None:
        table = {
            "bookmark": "knowledge_bookmark",
            "folder": "knowledge_bookmark_folder",
            "workspace": "named_knowledge_workspace",
        }.get(receipt["entity_kind"])
        return rows[table].get(receipt["entity_id"]) if table else None

    def _ancestry(self, folder_id: str) -> list[str]:
        result: list[str] = []
        current = folder_id
        while current:
            result.append(current)
            row = self.rows["knowledge_bookmark_folder"].get(current)
            current = row["parent_folder_id"] if row else None
        return result


@pytest.fixture
def fake_connection() -> FakeConnection:
    return FakeConnection()


@pytest.fixture
async def memory_connection():
    database = AsyncSurreal("mem://")
    await database.connect()
    await database.use("navigation", "navigation")
    await database.query(
        """
        DEFINE TABLE knowledge_bookmark_folder SCHEMAFULL;
        DEFINE FIELD schema_version ON TABLE knowledge_bookmark_folder TYPE int;
        DEFINE FIELD name ON TABLE knowledge_bookmark_folder TYPE string;
        DEFINE FIELD name_key ON TABLE knowledge_bookmark_folder TYPE string;
        DEFINE FIELD parent_folder_id ON TABLE knowledge_bookmark_folder TYPE option<string>;
        DEFINE FIELD position ON TABLE knowledge_bookmark_folder TYPE int;
        DEFINE FIELD revision ON TABLE knowledge_bookmark_folder TYPE int;
        DEFINE FIELD created_at ON TABLE knowledge_bookmark_folder TYPE datetime;
        DEFINE FIELD updated_at ON TABLE knowledge_bookmark_folder TYPE datetime;
        DEFINE TABLE knowledge_bookmark SCHEMAFULL;
        DEFINE FIELD schema_version ON TABLE knowledge_bookmark TYPE int;
        DEFINE FIELD target_kind ON TABLE knowledge_bookmark TYPE string;
        DEFINE FIELD target ON TABLE knowledge_bookmark FLEXIBLE TYPE object;
        DEFINE FIELD display_label ON TABLE knowledge_bookmark TYPE string;
        DEFINE FIELD authority_kind ON TABLE knowledge_bookmark TYPE option<string>;
        DEFINE FIELD space_id ON TABLE knowledge_bookmark TYPE option<string>;
        DEFINE FIELD folder_id ON TABLE knowledge_bookmark TYPE option<string>;
        DEFINE FIELD tags ON TABLE knowledge_bookmark TYPE array<string>;
        DEFINE FIELD position ON TABLE knowledge_bookmark TYPE int;
        DEFINE FIELD revision ON TABLE knowledge_bookmark TYPE int;
        DEFINE FIELD created_at ON TABLE knowledge_bookmark TYPE datetime;
        DEFINE FIELD updated_at ON TABLE knowledge_bookmark TYPE datetime;
        DEFINE TABLE named_knowledge_workspace SCHEMAFULL;
        DEFINE FIELD schema_version ON TABLE named_knowledge_workspace TYPE int;
        DEFINE FIELD name ON TABLE named_knowledge_workspace TYPE string;
        DEFINE FIELD name_key ON TABLE named_knowledge_workspace TYPE string;
        DEFINE FIELD snapshot_version ON TABLE named_knowledge_workspace TYPE int;
        DEFINE FIELD snapshot ON TABLE named_knowledge_workspace FLEXIBLE TYPE object;
        DEFINE FIELD revision ON TABLE named_knowledge_workspace TYPE int;
        DEFINE FIELD created_at ON TABLE named_knowledge_workspace TYPE datetime;
        DEFINE FIELD updated_at ON TABLE named_knowledge_workspace TYPE datetime;
        DEFINE TABLE knowledge_navigation_operation_receipt SCHEMAFULL;
        DEFINE FIELD schema_version ON TABLE knowledge_navigation_operation_receipt TYPE int;
        DEFINE FIELD operation_id ON TABLE knowledge_navigation_operation_receipt TYPE string;
        DEFINE FIELD operation_kind ON TABLE knowledge_navigation_operation_receipt TYPE string;
        DEFINE FIELD entity_kind ON TABLE knowledge_navigation_operation_receipt TYPE string;
        DEFINE FIELD entity_id ON TABLE knowledge_navigation_operation_receipt TYPE option<string>;
        DEFINE FIELD payload_hash ON TABLE knowledge_navigation_operation_receipt TYPE string;
        DEFINE FIELD result_status ON TABLE knowledge_navigation_operation_receipt TYPE string;
        DEFINE FIELD result_revision ON TABLE knowledge_navigation_operation_receipt TYPE option<int>;
        DEFINE FIELD result_code ON TABLE knowledge_navigation_operation_receipt TYPE string;
        DEFINE FIELD created_at ON TABLE knowledge_navigation_operation_receipt TYPE datetime;
        DEFINE FIELD completed_at ON TABLE knowledge_navigation_operation_receipt TYPE datetime;
        """
    )

    @asynccontextmanager
    async def factory():
        yield database

    try:
        yield type("MemoryConnection", (), {"factory": factory, "database": database})
    finally:
        await database.close()


@pytest.fixture
async def migrated_memory_connection():
    database = AsyncSurreal("mem://")
    await database.connect()
    await database.use("navigation_migrated", "navigation_migrated")
    root = Path(__file__).resolve().parents[1]
    await database.query(
        (root / "deeper_notebook/database/migrations/38.surrealql").read_text()
    )
    await database.query(
        (root / "deeper_notebook/database/migrations/39.surrealql").read_text()
    )

    @asynccontextmanager
    async def factory():
        yield database

    try:
        yield type(
            "MigratedMemoryConnection", (), {"factory": factory, "database": database}
        )
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_create_bookmark_replays_same_operation_and_rejects_new_payload(
    fake_connection: FakeConnection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=fake_connection.factory
    )
    command = create_bookmark_command(operation_id="bookmark-create-1")

    first = await repository.create_bookmark(command)
    replay = await repository.create_bookmark(command)

    assert replay == first
    with pytest.raises(KnowledgeNavigationRepositoryError, match="operation_conflict"):
        await repository.create_bookmark(
            command.model_copy(update={"display_label": "Changed"})
        )
    transaction = next(
        statement
        for statement in fake_connection.statements
        if "BEGIN TRANSACTION;" in statement
    )
    assert "$display_label" not in transaction


@pytest.mark.asyncio
async def test_update_requires_exact_revision_and_rolls_back_receipt(
    fake_connection: FakeConnection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=fake_connection.factory
    )
    existing = await repository.create_bookmark(create_bookmark_command())
    receipt_count = len(fake_connection.committed_receipts)
    fake_connection.fail_after_receipt = True

    with pytest.raises(
        KnowledgeNavigationRepositoryError,
        match="knowledge_navigation_repository_unavailable",
    ):
        await repository.update_bookmark(
            existing.id,
            update_bookmark_command(expected_revision=existing.revision),
        )

    assert len(fake_connection.committed_receipts) == receipt_count
    assert fake_connection.rows["knowledge_bookmark"][existing.id]["revision"] == 1


@pytest.mark.asyncio
async def test_folder_reparent_rejects_cycle_and_depth_seventeen(
    fake_connection: FakeConnection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=fake_connection.factory
    )
    parent = None
    for index in range(16):
        parent = await repository.create_folder(
            create_folder_command(
                operation_id=f"folder-create-{index}",
                name=f"Level {index}",
                parent_folder_id=parent.id if parent else None,
            )
        )

    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="folder_depth_exceeded"
    ):
        await repository.create_folder(
            create_folder_command(
                operation_id="folder-create-16",
                name="Level 16",
                parent_folder_id=parent.id,
            )
        )

    root_id = next(
        key
        for key, value in fake_connection.rows["knowledge_bookmark_folder"].items()
        if value["parent_folder_id"] is None
    )
    with pytest.raises(KnowledgeNavigationRepositoryError, match="folder_cycle"):
        await repository.update_folder(
            root_id,
            UpdateFolder(
                operation_id="folder-reparent-cycle",
                expected_revision=1,
                parent_folder_id=parent.id,
            ),
        )


@pytest.mark.asyncio
async def test_real_surreal_mutation_returns_receipt_replays_and_conflicts(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    command = create_bookmark_command(operation_id="native-bookmark-create")

    created = await repository.create_bookmark(command)
    replayed = await repository.create_bookmark(command)

    assert replayed == created
    with pytest.raises(KnowledgeNavigationRepositoryError, match="operation_conflict"):
        await repository.create_bookmark(
            command.model_copy(update={"display_label": "Conflict"})
        )
    receipts = await memory_connection.database.query(
        "SELECT operation_id, entity_id, payload_hash FROM knowledge_navigation_operation_receipt;"
    )
    assert len(receipts) == 1
    assert receipts[0]["entity_id"] == created.id


@pytest.mark.asyncio
async def test_real_surreal_folder_move_and_keyset_cursor_use_string_relationships(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    parent = await repository.create_folder(
        create_folder_command(operation_id="native-parent", name="Parent")
    )
    child = await repository.create_folder(
        create_folder_command(
            operation_id="native-child", name="Child", parent_folder_id=parent.id
        )
    )
    bookmark = await repository.create_bookmark(
        create_bookmark_command(operation_id="native-folder-bookmark").model_copy(
            update={"folder_id": child.id, "position": 4}
        )
    )
    direct_bookmark = await repository.create_bookmark(
        create_bookmark_command(operation_id="native-direct-bookmark").model_copy(
            update={"folder_id": parent.id, "position": 4}
        )
    )

    await repository.delete_folder(
        parent.id,
        DeleteFolder(
            operation_id="native-delete-parent",
            expected_revision=parent.revision,
            child_disposition="move_children",
        ),
    )
    moved = await repository.list_bookmarks(BookmarkFilters(), None, 10)

    assert [item.id for item in moved.items] == [direct_bookmark.id, bookmark.id]
    assert moved.items[0].folder_id is None
    assert moved.items[0].revision == direct_bookmark.revision + 1
    assert moved.items[1] == bookmark
    assert (
        await memory_connection.database.query(
            "SELECT parent_folder_id FROM knowledge_bookmark_folder WHERE id = $id;",
            {"id": RecordID.parse(child.id)},
        )
    )[0]["parent_folder_id"] is None

    await repository.create_bookmark(
        create_bookmark_command(operation_id="native-root-tie").model_copy(
            update={"display_label": "Root", "position": 4}
        )
    )
    first = await repository.list_bookmarks(BookmarkFilters(), None, 1)
    second = await repository.list_bookmarks(BookmarkFilters(), first.next_cursor, 1)
    assert first.next_cursor is not None
    assert second.items[0].id != first.items[0].id
    assert BookmarkCursor.decode(first.next_cursor).id == first.items[0].id


@pytest.mark.asyncio
async def test_real_surreal_random_note_filters_and_safe_descriptor(memory_connection):
    await memory_connection.database.query(
        """
        CREATE knowledge_engine_space:research CONTENT {
            source_kind: 'markdown', source_ref: 'vault:research'
        };
        CREATE knowledge_engine_document:eligible CONTENT {
            space_id: 'knowledge_engine_space:research', authority_kind: 'external_read_only',
            relative_locator: 'pages/eligible.md', source_native_id: 'note:eligible',
            document_kind: 'note', title: 'Eligible', availability: 'available',
            parse_state: 'ready', capabilities: ['read'], tags: ['Research', 'Project'],
            normalized_body: 'private body must never be projected'
        };
        CREATE knowledge_engine_document:later CONTENT {
            space_id: 'knowledge_engine_space:research', authority_kind: 'external_read_only',
            relative_locator: 'pages/later.md', source_native_id: 'note:later',
            document_kind: 'journal', title: 'Later', availability: 'available',
            parse_state: 'ready', capabilities: ['read'], tags: ['Research']
        };
        CREATE knowledge_engine_document:unreadable CONTENT {
            space_id: 'knowledge_engine_space:research', authority_kind: 'external_read_only',
            relative_locator: 'pages/unreadable.md', source_native_id: 'note:unreadable',
            document_kind: 'page', title: 'Unreadable', availability: 'available',
            parse_state: 'ready', capabilities: [], tags: ['Research']
        };
        CREATE knowledge_engine_document:stale CONTENT {
            space_id: 'knowledge_engine_space:research', authority_kind: 'external_read_only',
            relative_locator: 'pages/stale.md', source_native_id: 'note:stale',
            document_kind: 'note', title: 'Stale', availability: 'missing',
            parse_state: 'ready', capabilities: ['read'], tags: ['Research', 'Project']
        };
        CREATE knowledge_engine_document:pending CONTENT {
            space_id: 'knowledge_engine_space:research', authority_kind: 'external_read_only',
            relative_locator: 'pages/pending.md', source_native_id: 'note:pending',
            document_kind: 'note', title: 'Pending', availability: 'available',
            parse_state: 'pending', capabilities: ['read'], tags: ['Research', 'Project']
        };
        CREATE knowledge_engine_document:unsupported CONTENT {
            space_id: 'knowledge_engine_space:research', authority_kind: 'external_read_only',
            relative_locator: 'pages/unsupported.md', source_native_id: 'note:unsupported',
            document_kind: 'book', title: 'Unsupported', availability: 'available',
            parse_state: 'ready', capabilities: ['read'], tags: ['Research', 'Project']
        };
        CREATE knowledge_engine_document:other_space CONTENT {
            space_id: 'knowledge_engine_space:elsewhere', authority_kind: 'app_owned',
            relative_locator: 'pages/elsewhere.md', source_native_id: 'note:elsewhere',
            document_kind: 'note', title: 'Elsewhere', availability: 'available',
            parse_state: 'ready', capabilities: ['read'], tags: ['Research', 'Project']
        };
        """
    )
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    filters = RandomNoteFilters(
        space_ids=["knowledge_engine_space:research"], tags=["Research"]
    )

    assert await repository.random_candidate_count(filters) == 2
    selected = await repository.random_candidate_at(filters, 0)
    second = await repository.random_candidate_at(filters, 1)

    assert selected is not None
    assert second is not None
    assert {selected.document_id, second.document_id} == {
        "knowledge_engine_document:eligible",
        "knowledge_engine_document:later",
    }
    assert selected.document_id != second.document_id
    assert "/Users/" not in selected.model_dump_json()
    assert "private body" not in selected.model_dump_json()
    assert (
        await repository.random_candidate_count(
            RandomNoteFilters(
                space_ids=["knowledge_engine_space:research"],
                tags=["Research", "Project"],
            )
        )
        == 1
    )
    assert (
        await repository.random_candidate_count(
            RandomNoteFilters(authority_kinds=["app_owned"])
        )
        == 1
    )


@pytest.mark.asyncio
async def test_real_surreal_workspace_duplicate_receipt_is_bound_to_source(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    first = await repository.create_workspace(
        CreateWorkspace(
            operation_id="workspace-one", name="One", snapshot=workspace_snapshot()
        )
    )
    second = await repository.create_workspace(
        CreateWorkspace(
            operation_id="workspace-two", name="Two", snapshot=workspace_snapshot()
        )
    )
    duplicate = DuplicateWorkspace(operation_id="duplicate-once", name="Copy")

    copied = await repository.duplicate_workspace(first.id, duplicate)

    assert copied.snapshot == first.snapshot
    assert [workspace.name for workspace in await repository.list_workspaces()] == [
        "Copy",
        "One",
        "Two",
    ]
    updated = await repository.update_workspace(
        first.id,
        UpdateWorkspace(
            operation_id="workspace-one-update",
            expected_revision=first.revision,
            name="One revised",
        ),
    )
    assert (await repository.get_workspace(first.id)).revision == updated.revision
    deleted = await repository.delete_workspace(
        second.id,
        DeleteWorkspace(
            operation_id="workspace-two-delete", expected_revision=second.revision
        ),
    )
    assert (
        await repository.delete_workspace(
            second.id,
            DeleteWorkspace(
                operation_id="workspace-two-delete", expected_revision=second.revision
            ),
        )
    ) == deleted
    with pytest.raises(KnowledgeNavigationRepositoryError, match="operation_conflict"):
        await repository.duplicate_workspace(second.id, duplicate)


@pytest.mark.asyncio
async def test_real_surreal_workspace_rename_and_replace_preserve_their_other_fields(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    created = await repository.create_workspace(
        CreateWorkspace(
            operation_id="workspace-rename-create",
            name="Desk",
            snapshot=workspace_snapshot(),
        )
    )
    original_snapshot = created.snapshot

    renamed = await repository.update_workspace(
        created.id,
        UpdateWorkspace(
            operation_id="workspace-rename-only",
            expected_revision=created.revision,
            name="  Research Desk  ",
        ),
    )

    assert (renamed.name, renamed.name_key, renamed.revision) == (
        "Research Desk",
        "research desk",
        2,
    )
    assert renamed.snapshot == original_snapshot

    replacement = {**workspace_snapshot(), "next_id": 7}
    replaced = await repository.update_workspace(
        created.id,
        UpdateWorkspace(
            operation_id="workspace-replace-only",
            expected_revision=renamed.revision,
            snapshot=replacement,
        ),
    )

    assert (replaced.name, replaced.name_key, replaced.revision) == (
        "Research Desk",
        "research desk",
        3,
    )
    assert replaced.snapshot.next_id == 7
    with pytest.raises(ValueError, match="rename or replace"):
        await repository.update_workspace(
            created.id,
            UpdateWorkspace(
                operation_id="workspace-rename-and-replace",
                expected_revision=replaced.revision,
                name="Both",
                snapshot=workspace_snapshot(),
            ),
        )


@pytest.mark.asyncio
async def test_real_surreal_workspace_cap_is_atomic_for_create_and_duplicate(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    source = await repository.create_workspace(
        CreateWorkspace(
            operation_id="workspace-cap-source",
            name="Source",
            snapshot=workspace_snapshot(),
        )
    )
    await seed_workspace_rows(memory_connection.database, 255)

    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="workspace_limit_reached"
    ):
        await repository.create_workspace(
            CreateWorkspace(
                operation_id="workspace-cap-create",
                name="Overflow",
                snapshot=workspace_snapshot(),
            )
        )
    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="workspace_limit_reached"
    ):
        await repository.duplicate_workspace(
            source.id,
            DuplicateWorkspace(operation_id="workspace-cap-duplicate", name="Copy"),
        )
    assert len(await repository.list_workspaces()) == 256


@pytest.mark.asyncio
async def test_real_surreal_workspace_list_rejects_preexisting_overflow(
    memory_connection,
):
    await seed_workspace_rows(memory_connection.database, 257)
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )

    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="workspace_collection_too_large"
    ):
        await repository.list_workspaces()


@pytest.mark.asyncio
async def test_reparent_rejects_a_subtree_that_would_exceed_depth_sixteen(
    memory_connection, monkeypatch
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    parent = None
    for index in range(15):
        parent = await repository.create_folder(
            create_folder_command(
                operation_id=f"depth-parent-{index}",
                name=f"Depth parent {index}",
                parent_folder_id=parent.id if parent else None,
            )
        )
    moving = await repository.create_folder(
        create_folder_command(operation_id="moving-root", name="Moving root")
    )
    await repository.create_folder(
        create_folder_command(
            operation_id="moving-child", name="Moving child", parent_folder_id=moving.id
        )
    )

    async def understate_subtree_height(_: str) -> int:
        return 1

    # The mutation's own SurrealQL guard must catch the real two-level tree.
    monkeypatch.setattr(repository, "_folder_subtree_height", understate_subtree_height)

    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="folder_depth_exceeded"
    ):
        await repository.update_folder(
            moving.id,
            UpdateFolder(
                operation_id="move-too-deep",
                expected_revision=moving.revision,
                parent_folder_id=parent.id,
            ),
        )
    moved = await memory_connection.database.query(
        "SELECT parent_folder_id FROM $id;", {"id": RecordID.parse(moving.id)}
    )
    receipt = await memory_connection.database.query(
        "SELECT * FROM knowledge_navigation_operation_receipt WHERE operation_id = $operation_id;",
        {"operation_id": "move-too-deep"},
    )
    assert moved[0].get("parent_folder_id") is None
    assert receipt == []


@pytest.mark.asyncio
async def test_real_surreal_delete_tree_removes_navigation_rows_but_keeps_receipts(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    root = await repository.create_folder(
        create_folder_command(operation_id="tree-root", name="Tree root")
    )
    child = await repository.create_folder(
        create_folder_command(
            operation_id="tree-child", name="Tree child", parent_folder_id=root.id
        )
    )
    await repository.create_bookmark(
        create_bookmark_command(operation_id="tree-bookmark").model_copy(
            update={"folder_id": child.id}
        )
    )

    receipt = await repository.delete_folder(
        root.id,
        DeleteFolder(
            operation_id="tree-delete",
            expected_revision=root.revision,
            child_disposition="delete_tree",
        ),
    )

    assert receipt.result_code == "deleted"
    assert await repository.list_folders() == []
    assert (await repository.list_bookmarks(BookmarkFilters(), None, 10)).items == []
    receipts = await memory_connection.database.query(
        "SELECT * FROM knowledge_navigation_operation_receipt;"
    )
    assert len(receipts) == 4


@pytest.mark.asyncio
async def test_real_surreal_bookmark_revision_conflict_and_delete_replay(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    bookmark = await repository.create_bookmark(
        create_bookmark_command(operation_id="revision-bookmark")
    )
    updated = await repository.update_bookmark(
        bookmark.id,
        UpdateBookmark(
            operation_id="revision-bookmark-update",
            expected_revision=bookmark.revision,
            display_label="Revision two",
        ),
    )
    assert updated.revision == 2
    with pytest.raises(KnowledgeNavigationRepositoryError, match="revision_conflict"):
        await repository.update_bookmark(
            bookmark.id,
            UpdateBookmark(
                operation_id="revision-bookmark-stale",
                expected_revision=bookmark.revision,
                display_label="Stale",
            ),
        )
    delete = DeleteBookmark(
        operation_id="revision-bookmark-delete", expected_revision=updated.revision
    )
    first = await repository.delete_bookmark(bookmark.id, delete)
    replay = await repository.delete_bookmark(bookmark.id, delete)
    assert replay == first


@pytest.mark.asyncio
async def test_replay_is_receipt_first_and_refuses_changed_or_missing_results(
    memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=memory_connection.factory
    )
    create = create_bookmark_command(operation_id="replay-create")
    bookmark = await repository.create_bookmark(create)
    updated = await repository.update_bookmark(
        bookmark.id,
        UpdateBookmark(
            operation_id="replay-update",
            expected_revision=bookmark.revision,
            display_label="Changed after create",
        ),
    )
    with pytest.raises(
        KnowledgeNavigationRepositoryError,
        match="knowledge_navigation_replay_result_unavailable",
    ):
        await repository.create_bookmark(create)

    await repository.delete_bookmark(
        bookmark.id,
        DeleteBookmark(
            operation_id="replay-delete", expected_revision=updated.revision
        ),
    )
    with pytest.raises(
        KnowledgeNavigationRepositoryError,
        match="knowledge_navigation_replay_result_unavailable",
    ):
        await repository.update_bookmark(
            bookmark.id,
            UpdateBookmark(
                operation_id="replay-update",
                expected_revision=bookmark.revision,
                display_label="Changed after create",
            ),
        )

    folder = await repository.create_folder(
        create_folder_command(operation_id="replay-folder", name="Replay folder")
    )
    folder_bookmark_command = create_bookmark_command(
        operation_id="replay-folder-bookmark"
    ).model_copy(update={"folder_id": folder.id})
    await repository.create_bookmark(folder_bookmark_command)
    await repository.delete_folder(
        folder.id,
        DeleteFolder(
            operation_id="replay-folder-delete",
            expected_revision=folder.revision,
            child_disposition="move_children",
        ),
    )
    with pytest.raises(
        KnowledgeNavigationRepositoryError,
        match="knowledge_navigation_replay_result_unavailable",
    ):
        await repository.create_bookmark(folder_bookmark_command)


@pytest.mark.asyncio
async def test_parent_removal_after_preflight_rolls_back_folder_and_bookmark_mutations(
    fake_connection: FakeConnection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=fake_connection.factory
    )
    parent = await repository.create_folder(
        create_folder_command(operation_id="race-parent", name="Race parent")
    )
    fake_connection.remove_parent_before_mutation = parent.id
    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="folder_parent_not_found"
    ):
        await repository.create_folder(
            create_folder_command(
                operation_id="race-child", name="Race child", parent_folder_id=parent.id
            )
        )
    assert "race-child" not in str(fake_connection.committed_receipts)

    replacement = await repository.create_folder(
        create_folder_command(operation_id="race-replacement", name="Replacement")
    )
    moving = await repository.create_folder(
        create_folder_command(operation_id="race-moving", name="Moving")
    )
    fake_connection.remove_parent_before_mutation = replacement.id
    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="folder_parent_not_found"
    ):
        await repository.update_folder(
            moving.id,
            UpdateFolder(
                operation_id="race-reparent",
                expected_revision=moving.revision,
                parent_folder_id=replacement.id,
            ),
        )

    bookmark = await repository.create_bookmark(
        create_bookmark_command(operation_id="race-bookmark")
    )
    destination = await repository.create_folder(
        create_folder_command(operation_id="race-destination", name="Destination")
    )
    fake_connection.remove_parent_before_mutation = destination.id
    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="folder_parent_not_found"
    ):
        await repository.update_bookmark(
            bookmark.id,
            UpdateBookmark(
                operation_id="race-bookmark-move",
                expected_revision=bookmark.revision,
                folder_id=destination.id,
            ),
        )
    assert fake_connection.rows["knowledge_bookmark"][bookmark.id]["folder_id"] is None


@pytest.mark.asyncio
async def test_repository_runs_against_exact_migrations_thirty_eight_and_thirty_nine(
    migrated_memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=migrated_memory_connection.factory
    )
    folder = await repository.create_folder(
        create_folder_command(operation_id="migrated-folder", name="Migrated folder")
    )
    bookmark = await repository.create_bookmark(
        create_bookmark_command(operation_id="migrated-bookmark").model_copy(
            update={"folder_id": folder.id}
        )
    )
    info = await migrated_memory_connection.database.query(
        "INFO FOR TABLE knowledge_navigation_operation_receipt;"
    )

    assert bookmark.folder_id == folder.id
    assert "idx_kn_operation_id" in str(info)


@pytest.mark.asyncio
async def test_exact_schema_create_folder_checks_depth_inside_its_transaction(
    migrated_memory_connection,
):
    repository = KnowledgeNavigationRepository(
        connection_factory=migrated_memory_connection.factory
    )
    parent = None
    root = None
    for index in range(15):
        parent = await repository.create_folder(
            create_folder_command(
                operation_id=f"create-depth-{index}",
                name=f"Create depth {index}",
                parent_folder_id=parent.id if parent else None,
            )
        )
        root = root or parent
    extra_root = await repository.create_folder(
        create_folder_command(operation_id="create-depth-extra", name="Extra root")
    )
    armed = True

    class AncestorRaceConnection:
        async def query(self, statement, variables=None):
            nonlocal armed
            if armed and "BEGIN TRANSACTION;" in statement:
                armed = False
                await migrated_memory_connection.database.query(
                    "UPDATE $id SET parent_folder_id = $parent;",
                    {"id": RecordID.parse(root.id), "parent": extra_root.id},
                )
            return await migrated_memory_connection.database.query(statement, variables)

    @asynccontextmanager
    async def factory():
        yield AncestorRaceConnection()

    racing_repository = KnowledgeNavigationRepository(connection_factory=factory)
    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="folder_depth_exceeded"
    ):
        await racing_repository.create_folder(
            create_folder_command(
                operation_id="create-depth-race",
                name="Must not commit",
                parent_folder_id=parent.id,
            )
        )
    assert "Must not commit" not in [
        folder.name for folder in await repository.list_folders()
    ]
    receipts = await migrated_memory_connection.database.query(
        "SELECT * FROM knowledge_navigation_operation_receipt WHERE operation_id = $operation_id;",
        {"operation_id": "create-depth-race"},
    )
    assert receipts == []
