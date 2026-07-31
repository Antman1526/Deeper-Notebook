"""Hydration behavior for global, content-free navigation metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from deeper_notebook.knowledge_engine.navigation_contracts import (
    BlockTarget,
    Bookmark,
    BookmarkFilters,
    BookmarkPage,
    CreateWorkspace,
    DeleteWorkspace,
    DocumentTarget,
    DuplicateWorkspace,
    GraphTarget,
    KnowledgeOpenDescriptor,
    NamedKnowledgeWorkspace,
    NamedKnowledgeWorkspaceSummary,
    NamedWorkspaceSnapshot,
    UpdateWorkspace,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepositoryError,
)
from deeper_notebook.knowledge_engine.navigation_service import (
    KnowledgeNavigationService,
)


class _MetadataRepository:
    async def list_bookmarks(self, _filters, _cursor, _limit):
        timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
        return BookmarkPage(
            items=[
                Bookmark(
                    id="knowledge_bookmark:plan",
                    target_kind="document",
                    target={
                        "kind": "document",
                        "document_id": "knowledge_engine_document:plan",
                    },
                    display_label="Research plan",
                    tags=["Research"],
                    position=0,
                    revision=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            ]
        )


class _WorkspaceMetadataRepository:
    def __init__(self, workspace: NamedKnowledgeWorkspace) -> None:
        self.workspace = workspace

    async def get_workspace(self, workspace_id: str) -> NamedKnowledgeWorkspace:
        if workspace_id != self.workspace.id:
            raise LookupError(workspace_id)
        return self.workspace


class _WorkspaceCrudMetadataRepository(_WorkspaceMetadataRepository):
    def __init__(self, workspace: NamedKnowledgeWorkspace) -> None:
        super().__init__(workspace)
        self.create_commands: list[object] = []
        self.update_commands: list[object] = []
        self.deleted: list[str] = []

    async def list_workspaces(self) -> list[NamedKnowledgeWorkspaceSummary]:
        return [
            NamedKnowledgeWorkspaceSummary(
                id=self.workspace.id,
                name=self.workspace.name,
                revision=self.workspace.revision,
                updated_at=self.workspace.updated_at,
            )
        ]

    async def create_workspace(self, command):
        self.create_commands.append(command)
        return self.workspace

    async def update_workspace(self, _workspace_id: str, command):
        self.update_commands.append(command)
        return self.workspace

    async def duplicate_workspace(self, _workspace_id: str, _command):
        return self.workspace.model_copy(
            update={"id": "named_knowledge_workspace:copy", "revision": 1}
        )

    async def delete_workspace(self, workspace_id: str, _command):
        self.deleted.append(workspace_id)
        return None


def _workspace_snapshot() -> NamedWorkspaceSnapshot:
    return NamedWorkspaceSnapshot.model_validate(
        {
            "active_pane_id": "pane-one",
            "next_id": 4,
            "panes": {
                "pane-one": {
                    "id": "pane-one",
                    "active_tab_id": "tab-document",
                    "tabs": [
                        {
                            "id": "tab-document",
                            "display_label": "Plan",
                            "target": {
                                "kind": "document",
                                "document_id": "knowledge_engine_document:plan",
                            },
                        },
                        {
                            "id": "tab-block",
                            "display_label": "Stale block",
                            "target": {
                                "kind": "block",
                                "document_id": "knowledge_engine_document:plan",
                                "block_id": "knowledge_engine_block:plan",
                                "source_revision_id": "knowledge_engine_revision:stale",
                            },
                        },
                        {
                            "id": "tab-search",
                            "display_label": "Research",
                            "target": {"kind": "search", "query": "research"},
                        },
                    ],
                }
            },
            "layout": {"type": "pane", "pane_id": "pane-one"},
        }
    )


def _named_workspace(revision: int = 3) -> NamedKnowledgeWorkspace:
    timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)
    return NamedKnowledgeWorkspace(
        id="named_knowledge_workspace:desk",
        name="Desk",
        name_key="desk",
        snapshot=_workspace_snapshot(),
        revision=revision,
        created_at=timestamp,
        updated_at=timestamp,
    )


class UnavailableEngineRepository:
    async def get_document(self, _document_id):
        raise KnowledgeNavigationRepositoryError("knowledge_engine_unavailable")


class _Engine:
    def __init__(self) -> None:
        self.document: object | Exception = SimpleNamespace(
            source_revision_id="knowledge_engine_revision:current"
        )
        self.descriptor: object | Exception | None = KnowledgeOpenDescriptor(
            document_id="knowledge_engine_document:plan",
            space_id="knowledge_engine_space:primary",
            authority_kind="external_read_only",
            source_kind="markdown",
            title="Plan",
            relative_locator="Plans/Research.md",
            legacy_note_id="note:plan",
            legacy_container_id="vault_mount:primary",
        )
        self.current_block: object | Exception | None = SimpleNamespace(
            block_id="knowledge_engine_block:plan",
            document_id="knowledge_engine_document:plan",
            source_revision_id="knowledge_engine_revision:current",
        )

    async def get_document(self, _document_id: str):
        if isinstance(self.document, Exception):
            raise self.document
        return self.document

    async def open_descriptor(self, _document_id: str):
        if isinstance(self.descriptor, Exception):
            raise self.descriptor
        return self.descriptor

    async def get_current_block(self, **_kwargs):
        if isinstance(self.current_block, Exception):
            raise self.current_block
        return self.current_block


@pytest.fixture()
def service() -> KnowledgeNavigationService:
    return KnowledgeNavigationService(metadata_repository=_MetadataRepository())


@pytest.mark.asyncio
async def test_bookmark_collection_keeps_unavailable_metadata(
    service: KnowledgeNavigationService,
) -> None:
    service.engine_repository = UnavailableEngineRepository()

    page = await service.list_bookmarks(BookmarkFilters(), cursor=None, limit=50)

    assert page.items[0].display_label == "Research plan"
    assert page.items[0].target_state == "unavailable"
    assert page.items[0].target_document is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("document", "current_block", "revision_hint", "expected"),
    [
        ("current", "matching", None, "available"),
        ("current", None, None, "stale"),
        ("current", "wrong-document", None, "stale"),
        ("current", "wrong-revision", None, "stale"),
        ("current", "matching", "knowledge_engine_revision:stale", "stale"),
        ("missing", "matching", None, "missing"),
        ("unavailable", "matching", None, "unavailable"),
    ],
)
async def test_block_hydration_has_a_complete_current_revision_state_matrix(
    service: KnowledgeNavigationService,
    document: str,
    current_block: str | None,
    revision_hint: str | None,
    expected: str,
) -> None:
    engine = _Engine()
    if document == "missing":
        engine.document = LookupError("private document detail")
    elif document == "unavailable":
        engine.document = KnowledgeNavigationRepositoryError(
            "private repository detail"
        )
    engine.current_block = engine.current_block if current_block == "matching" else None
    if current_block == "wrong-document":
        engine.current_block = SimpleNamespace(
            document_id="knowledge_engine_document:other",
            source_revision_id="knowledge_engine_revision:current",
        )
    elif current_block == "wrong-revision":
        engine.current_block = SimpleNamespace(
            document_id="knowledge_engine_document:plan",
            source_revision_id="knowledge_engine_revision:stale",
        )
    service.engine_repository = engine

    hydrated = await service.hydrate_target(
        BlockTarget(
            document_id="knowledge_engine_document:plan",
            block_id="knowledge_engine_block:plan",
            source_revision_id=revision_hint,
        )
    )

    assert hydrated.state == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("descriptor", "document", "expected"),
    [
        ("present", "current", "available"),
        ("missing", "current", "stale"),
        ("present", "missing", "missing"),
        ("present", "unavailable", "unavailable"),
    ],
)
async def test_rooted_graph_hydration_preserves_the_graph_target_and_root_state(
    service: KnowledgeNavigationService,
    descriptor: str,
    document: str,
    expected: str,
) -> None:
    engine = _Engine()
    engine.descriptor = None if descriptor == "missing" else engine.descriptor
    if document == "missing":
        engine.document = LookupError("private document detail")
    elif document == "unavailable":
        engine.document = KnowledgeNavigationRepositoryError(
            "private repository detail"
        )
    service.engine_repository = engine

    graph = GraphTarget(root_document_id="knowledge_engine_document:plan")
    hydrated = await service.hydrate_target(graph)

    assert hydrated.target == graph
    assert hydrated.state == expected


@pytest.mark.asyncio
async def test_global_graph_is_available_without_engine_hydration(
    service: KnowledgeNavigationService,
) -> None:
    assert (await service.hydrate_target(GraphTarget())).state == "available"


@pytest.mark.asyncio
async def test_rooted_graph_uses_a_real_document_target(
    service: KnowledgeNavigationService,
) -> None:
    graph = GraphTarget(root_document_id="knowledge_engine_document:plan")

    async def hydrate_document(target):
        assert isinstance(target, DocumentTarget)
        return await KnowledgeNavigationService._hydrate_document(service, target)

    service.engine_repository = _Engine()
    service._hydrate_document = hydrate_document  # type: ignore[method-assign]

    assert (await service.hydrate_target(graph)).state == "available"


@pytest.mark.asyncio
async def test_one_hydration_failure_does_not_poison_other_bookmark_metadata(
    service: KnowledgeNavigationService,
) -> None:
    timestamp = datetime(2026, 7, 31, tzinfo=timezone.utc)

    async def list_bookmarks(*_args):
        return BookmarkPage(
            items=[
                Bookmark(
                    id="knowledge_bookmark:unavailable",
                    target_kind="document",
                    target={
                        "kind": "document",
                        "document_id": "knowledge_engine_document:plan",
                    },
                    display_label="Unavailable",
                    position=0,
                    revision=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
                Bookmark(
                    id="knowledge_bookmark:available",
                    target_kind="search",
                    target={"kind": "search", "query": "research"},
                    display_label="Available",
                    position=1,
                    revision=1,
                    created_at=timestamp,
                    updated_at=timestamp,
                ),
            ]
        )

    service.metadata_repository.list_bookmarks = list_bookmarks  # type: ignore[method-assign]
    service.engine_repository = UnavailableEngineRepository()

    page = await service.list_bookmarks(BookmarkFilters(), cursor=None, limit=50)

    assert [item.target_state for item in page.items] == ["unavailable", "available"]


@pytest.mark.asyncio
async def test_restore_plan_hydrates_every_target_without_mutating_current_session(
    tmp_path,
) -> None:
    current_session_path = tmp_path / "knowledge-workspace-v1.json"
    current_session_path.write_bytes(b'{"synthetic":true}')
    before = current_session_path.read_bytes()
    service = KnowledgeNavigationService(
        metadata_repository=_WorkspaceMetadataRepository(_named_workspace()),
        engine_repository=_Engine(),
    )

    plan = await service.workspace_restore_plan("named_knowledge_workspace:desk", 3)

    assert plan.workspace_id == "named_knowledge_workspace:desk"
    assert plan.revision == 3
    assert plan.summary == {
        "available": 2,
        "stale": 1,
        "unavailable": 0,
        "missing": 0,
    }
    assert [tab.id for tab in plan.panes["pane-one"].tabs] == [
        "tab-document",
        "tab-block",
        "tab-search",
    ]
    assert (
        plan.panes["pane-one"].tabs[0].target_document.relative_locator
        == "Plans/Research.md"
    )
    assert current_session_path.read_bytes() == before


@pytest.mark.asyncio
async def test_workspace_service_enforces_rename_replace_boundaries_without_current_session(
    tmp_path,
) -> None:
    current_session_path = tmp_path / "knowledge-workspace-v1.json"
    current_session_path.write_bytes(b'{"synthetic":true}')
    before = current_session_path.read_bytes()
    metadata = _WorkspaceCrudMetadataRepository(_named_workspace())
    service = KnowledgeNavigationService(metadata_repository=metadata)
    snapshot = _workspace_snapshot()

    created = await service.create_workspace(
        CreateWorkspace(
            operation_id="service-create",
            name="Desk",
            snapshot=snapshot,
        )
    )
    renamed = await service.update_workspace(
        created.id,
        UpdateWorkspace(
            operation_id="service-rename",
            expected_revision=created.revision,
            name="  Research Desk  ",
        ),
    )
    replaced = await service.update_workspace(
        created.id,
        UpdateWorkspace(
            operation_id="service-replace",
            expected_revision=renamed.revision,
            snapshot=snapshot,
        ),
    )
    with pytest.raises(ValueError, match="rename or replace"):
        await service.update_workspace(
            created.id,
            UpdateWorkspace(
                operation_id="service-both",
                expected_revision=replaced.revision,
                name="Both",
                snapshot=snapshot,
            ),
        )
    copied = await service.duplicate_workspace(
        created.id,
        DuplicateWorkspace(operation_id="service-copy", name="Copy"),
    )
    await service.delete_workspace(
        created.id,
        DeleteWorkspace(
            operation_id="service-delete", expected_revision=created.revision
        ),
    )

    assert len(await service.list_workspaces()) == 1
    assert metadata.create_commands[0].snapshot == snapshot
    assert (
        metadata.update_commands[0].name,
        metadata.update_commands[0].name_key,
        metadata.update_commands[0].snapshot,
    ) == ("Research Desk", "research desk", None)
    assert metadata.update_commands[1].name is None
    assert metadata.update_commands[1].snapshot == snapshot
    assert copied.id != created.id
    assert copied.revision == 1
    assert metadata.deleted == [created.id]
    assert current_session_path.read_bytes() == before
