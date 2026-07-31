from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy

import pytest

from deeper_notebook.knowledge_engine.navigation_contracts import (
    CreateBookmark,
    CreateFolder,
    UpdateBookmark,
    UpdateFolder,
)
from deeper_notebook.knowledge_engine.navigation_repository import (
    KnowledgeNavigationRepository,
    KnowledgeNavigationRepositoryError,
)


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
        if variables.get("read") == "folder_parent":
            return [
                self.rows["knowledge_bookmark_folder"].get(
                    str(variables["folder_id"])
                )
            ]
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
        operation_id = variables["operation_id"]
        prior = staged_receipts.get(operation_id)
        if prior is not None:
            if prior["payload_hash"] != variables["payload_hash"]:
                return [{"error": "operation_conflict"}]
            return [{"prior": prior, "entity": self._entity_for(prior, staged_rows), "receipt": prior}]

        table = variables["table"]
        entity_id = str(variables["entity_id"])
        current = staged_rows[table].get(entity_id)
        expected = variables.get("expected_revision")
        if expected is not None and (current is None or current["revision"] != expected):
            return [{"error": "revision_conflict"}]

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


@pytest.mark.asyncio
async def test_create_bookmark_replays_same_operation_and_rejects_new_payload(
    fake_connection: FakeConnection,
):
    repository = KnowledgeNavigationRepository(connection_factory=fake_connection.factory)
    command = create_bookmark_command(operation_id="bookmark-create-1")

    first = await repository.create_bookmark(command)
    replay = await repository.create_bookmark(command)

    assert replay == first
    with pytest.raises(KnowledgeNavigationRepositoryError, match="operation_conflict"):
        await repository.create_bookmark(
            command.model_copy(update={"display_label": "Changed"})
        )
    assert "BEGIN TRANSACTION;" in fake_connection.statements[0]
    assert "$display_label" not in fake_connection.statements[0]


@pytest.mark.asyncio
async def test_update_requires_exact_revision_and_rolls_back_receipt(
    fake_connection: FakeConnection,
):
    repository = KnowledgeNavigationRepository(connection_factory=fake_connection.factory)
    existing = await repository.create_bookmark(create_bookmark_command())
    receipt_count = len(fake_connection.committed_receipts)
    fake_connection.fail_after_receipt = True

    with pytest.raises(
        KnowledgeNavigationRepositoryError, match="knowledge_navigation_repository_unavailable"
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
    repository = KnowledgeNavigationRepository(connection_factory=fake_connection.factory)
    parent = None
    for index in range(16):
        parent = await repository.create_folder(
            create_folder_command(
                operation_id=f"folder-create-{index}",
                name=f"Level {index}",
                parent_folder_id=parent.id if parent else None,
            )
        )

    with pytest.raises(KnowledgeNavigationRepositoryError, match="folder_depth_exceeded"):
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
