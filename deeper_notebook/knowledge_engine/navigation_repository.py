"""Transactional persistence for content-free navigation metadata."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from deeper_notebook.database.repository import (
    db_connection,
    ensure_record_id,
    parse_record_ids,
)
from deeper_notebook.knowledge_engine.navigation_contracts import (
    Bookmark,
    BookmarkCursor,
    BookmarkFilters,
    BookmarkFolder,
    BookmarkPage,
    CreateBookmark,
    CreateFolder,
    CreateWorkspace,
    DeleteBookmark,
    DeleteFolder,
    DeleteWorkspace,
    DuplicateWorkspace,
    KnowledgeOpenDescriptor,
    NamedKnowledgeWorkspace,
    NamedKnowledgeWorkspaceSummary,
    NavigationReceipt,
    RandomNoteFilters,
    UpdateBookmark,
    UpdateFolder,
    UpdateWorkspace,
)

_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_TABLES = {
    "bookmark": "knowledge_bookmark",
    "folder": "knowledge_bookmark_folder",
    "workspace": "named_knowledge_workspace",
}
MAX_NAMED_WORKSPACES = 256
_WORKSPACE_ALLOCATOR_ID = "named_knowledge_workspace:capacity_allocator"
_OPEN_DESCRIPTOR_FIELDS = (
    "id AS document_id, space_id, authority_kind, "
    "(SELECT VALUE source_kind FROM knowledge_engine_space "
    "WHERE type::string(id) = $parent.space_id LIMIT 1)[0] AS source_kind, title, "
    "relative_locator, source_native_id AS legacy_note_id, "
    "(SELECT VALUE source_ref FROM knowledge_engine_space "
    "WHERE type::string(id) = $parent.space_id LIMIT 1)[0] AS legacy_container_id"
)


class _Connection(Protocol):
    async def query(
        self, statement: str, variables: dict[str, Any] | None = None
    ) -> Any: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[_Connection]]


class KnowledgeNavigationRepositoryError(RuntimeError):
    """Stable, scrubbed failure from navigation metadata persistence."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_id(table: str, value: str):
    pattern = re.compile(rf"^{re.escape(table)}:[A-Za-z0-9_-]+$")
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"invalid_{table}_id")
    return ensure_record_id(value)


def _operation(value: str) -> str:
    if not isinstance(value, str) or _OPERATION_ID.fullmatch(value) is None:
        raise ValueError("invalid_knowledge_navigation_operation_id")
    return value


def _payload_hash(
    command: BaseModel,
    *,
    entity_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> str:
    payload = command.model_dump(mode="json", exclude={"operation_id"})
    if entity_id is not None:
        payload["entity_id"] = entity_id
    if context:
        payload.update(context)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _generated_id(table: str, operation_id: str) -> str:
    return f"{table}:{sha256(operation_id.encode()).hexdigest()}"


def _content(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="python", exclude={"id"})


def _workspace_create_transaction() -> str:
    """Create a workspace only when its unique capacity slot is free."""
    return """
        BEGIN TRANSACTION;
        LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt
            WHERE operation_id = $operation_id LIMIT 1);
        IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash {
            RETURN { code: 'operation_conflict' };
        };
        IF array::len($prior) > 0 {
            RETURN { code: 'replayed', prior: $prior,
                entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $prior[0] };
        };
        LET $allocator = (SELECT id FROM $workspace_allocator_id LIMIT 1);
        IF array::len($allocator) = 0 {
            RETURN { code: 'workspace_allocator_unavailable' };
        };
        UPDATE $workspace_allocator_id SET revision = revision + 1,
            updated_at = time::now();
        LET $slot = (SELECT id FROM named_knowledge_workspace
            WHERE capacity_slot = $capacity_slot LIMIT 1);
        IF array::len($slot) > 0 {
            RETURN { code: 'workspace_slot_taken' };
        };
        CREATE $receipt_id CONTENT $receipt;
        UPSERT $entity_id CONTENT $entity;
        RETURN { code: 'succeeded', prior: $prior,
            entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $receipt };
        COMMIT TRANSACTION;
    """


def _workspace_delete_transaction() -> str:
    """Delete a workspace while contending on the shared capacity allocator."""
    return """
        BEGIN TRANSACTION;
        LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt
            WHERE operation_id = $operation_id LIMIT 1);
        IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash {
            RETURN { code: 'operation_conflict' };
        };
        IF array::len($prior) > 0 {
            RETURN { code: 'replayed', prior: $prior, receipt: $prior[0] };
        };
        LET $current = (SELECT * FROM $entity_id LIMIT 1);
        IF array::len($current) = 0 OR $current[0].revision != $expected_revision {
            RETURN { code: 'revision_conflict' };
        };
        LET $allocator = (SELECT id FROM $workspace_allocator_id LIMIT 1);
        IF array::len($allocator) = 0 {
            RETURN { code: 'workspace_allocator_unavailable' };
        };
        UPDATE $workspace_allocator_id SET revision = revision + 1,
            updated_at = time::now();
        CREATE $receipt_id CONTENT $receipt;
        DELETE $entity_id;
        RETURN { code: 'succeeded', prior: $prior, receipt: $receipt };
        COMMIT TRANSACTION;
    """


def _folder_reparent_transaction() -> str:
    """Build fixed-depth, data-bound atomic checks for a folder reparent."""
    parents = ["LET $parent_0 = $new_parent_relation_id;"]
    parents.extend(
        "LET $parent_" + str(index) + " = (SELECT VALUE parent_folder_id "
        "FROM knowledge_bookmark_folder WHERE type::string(id) = $parent_"
        + str(index - 1)
        + " LIMIT 1)[0];"
        for index in range(1, 16)
    )
    cycle = " OR ".join(f"$parent_{index} = $entity_relation_id" for index in range(16))
    depth = " ".join(
        "IF $subtree_height = "
        + str(height)
        + " AND $parent_"
        + str(16 - height)
        + " != NONE { RETURN { code: 'folder_depth_exceeded' }; };"
        for height in range(1, 17)
    )
    subtree = ["LET $subtree_0 = [$entity_relation_id];"]
    subtree.extend(
        "LET $subtree_" + str(index) + " = (SELECT VALUE type::string(id) "
        "FROM knowledge_bookmark_folder WHERE parent_folder_id IN $subtree_"
        + str(index - 1)
        + ");"
        for index in range(1, 16)
    )
    combined_depth = " ".join(
        "IF array::len($subtree_"
        + str(level)
        + ") > 0 AND $parent_"
        + str(15 - level)
        + " != NONE { RETURN { code: 'folder_depth_exceeded' }; };"
        for level in range(16)
    )
    return f"""
        BEGIN TRANSACTION;
        LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt
            WHERE operation_id = $operation_id LIMIT 1);
        IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash {{
            RETURN {{ code: 'operation_conflict' }};
        }};
        IF array::len($prior) > 0 {{
            RETURN {{ code: 'replayed', prior: $prior,
                entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $prior[0] }};
        }};
        LET $current = (SELECT * FROM $entity_id LIMIT 1);
        IF array::len($current) = 0 OR $current[0].revision != $expected_revision {{
            RETURN {{ code: 'revision_conflict' }};
        }};
        IF array::len((SELECT id FROM knowledge_bookmark_folder
            WHERE type::string(id) = $new_parent_relation_id LIMIT 1)) = 0 {{
            RETURN {{ code: 'folder_parent_not_found' }};
        }};
        {" ".join(parents)}
        IF {cycle} {{ RETURN {{ code: 'folder_cycle' }}; }};
        {depth}
        {" ".join(subtree)}
        {combined_depth}
        CREATE $receipt_id CONTENT $receipt;
        UPSERT $entity_id CONTENT $entity;
        RETURN {{ code: 'succeeded', prior: $prior,
            entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $receipt }};
        COMMIT TRANSACTION;
    """


def _folder_create_transaction() -> str:
    """Build a receipt-first, transaction-local max-depth guard for creates."""
    parents = ["LET $parent_0 = $new_parent_relation_id;"]
    parents.extend(
        "LET $parent_" + str(index) + " = (SELECT VALUE parent_folder_id "
        "FROM knowledge_bookmark_folder WHERE type::string(id) = $parent_"
        + str(index - 1)
        + " LIMIT 1)[0];"
        for index in range(1, 16)
    )
    return f"""
        BEGIN TRANSACTION;
        LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt
            WHERE operation_id = $operation_id LIMIT 1);
        IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash {{
            RETURN {{ code: 'operation_conflict' }};
        }};
        IF array::len($prior) > 0 {{
            RETURN {{ code: 'replayed', prior: $prior,
                entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $prior[0] }};
        }};
        IF array::len((SELECT id FROM knowledge_bookmark_folder
            WHERE type::string(id) = $new_parent_relation_id LIMIT 1)) = 0 {{
            RETURN {{ code: 'folder_parent_not_found' }};
        }};
        {" ".join(parents)}
        IF $parent_15 != NONE {{ RETURN {{ code: 'folder_depth_exceeded' }}; }};
        CREATE $receipt_id CONTENT $receipt;
        UPSERT $entity_id CONTENT $entity;
        RETURN {{ code: 'succeeded', prior: $prior,
            entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $receipt }};
        COMMIT TRANSACTION;
    """


def _model(model: type[BaseModel], value: Any, *, code: str) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError:
        raise KnowledgeNavigationRepositoryError(code) from None


def _receipt_model(value: Any) -> NavigationReceipt:
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key != "id"}
    return _model(NavigationReceipt, value, code="knowledge_navigation_receipt_invalid")


class KnowledgeNavigationRepository:
    """Persist navigation metadata with durable operation receipts."""

    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._connection_factory = connection_factory or db_connection
        self._clock = clock

    async def _query(
        self,
        connection: _Connection,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> list[Any]:
        try:
            result = await connection.query(statement, variables)
        except KnowledgeNavigationRepositoryError:
            raise
        except Exception:
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_repository_unavailable"
            ) from None
        if isinstance(result, str):
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_repository_unavailable"
            )
        parsed = parse_record_ids(result)
        return parsed if isinstance(parsed, list) else [parsed]

    async def _folder_ancestry(self, folder_id: str) -> list[str]:
        ancestry: list[str] = []
        current_id: str | None = folder_id
        while current_id is not None:
            if current_id in ancestry:
                raise KnowledgeNavigationRepositoryError("folder_cycle")
            if len(ancestry) >= 16:
                raise KnowledgeNavigationRepositoryError("folder_depth_exceeded")
            ancestry.append(current_id)
            async with self._connection_factory() as connection:
                rows = await self._query(
                    connection,
                    """
                    SELECT id, parent_folder_id FROM knowledge_bookmark_folder
                    WHERE id = $folder_id LIMIT 1;
                    """,
                    {
                        "read": "folder_parent",
                        "folder_id": _record_id(
                            "knowledge_bookmark_folder", current_id
                        ),
                    },
                )
            row = rows[0] if rows else None
            if not isinstance(row, dict):
                raise KnowledgeNavigationRepositoryError("folder_parent_not_found")
            current_id = row.get("parent_folder_id")
        return ancestry

    async def _validate_folder_parent(
        self,
        parent_folder_id: str | None,
        *,
        moving_folder_id: str | None = None,
        moving_subtree_height: int = 1,
    ) -> None:
        if parent_folder_id is None:
            return
        _record_id("knowledge_bookmark_folder", parent_folder_id)
        ancestry = await self._folder_ancestry(parent_folder_id)
        if moving_folder_id is not None and moving_folder_id in ancestry:
            raise KnowledgeNavigationRepositoryError("folder_cycle")
        if len(ancestry) + moving_subtree_height > 16:
            raise KnowledgeNavigationRepositoryError("folder_depth_exceeded")

    async def _folder_subtree_height(self, folder_id: str) -> int:
        """Return the bounded height of a folder subtree using string relations."""
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT id, parent_folder_id FROM knowledge_bookmark_folder;",
            )
        children: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            child_id = row.get("id")
            parent_id = row.get("parent_folder_id")
            if isinstance(child_id, str) and isinstance(parent_id, str):
                children.setdefault(parent_id, []).append(child_id)
        height = 1
        stack = [(folder_id, 1)]
        visited: set[str] = set()
        while stack:
            current_id, current_height = stack.pop()
            if current_id in visited:
                raise KnowledgeNavigationRepositoryError("folder_cycle")
            visited.add(current_id)
            height = max(height, current_height)
            if height > 16:
                raise KnowledgeNavigationRepositoryError("folder_depth_exceeded")
            stack.extend(
                (child_id, current_height + 1)
                for child_id in children.get(current_id, [])
            )
        return height

    def _receipt(
        self,
        *,
        operation_id: str,
        operation_kind: str,
        entity_kind: str,
        entity_id: str,
        payload_hash: str,
        revision: int | None,
        code: str,
    ) -> NavigationReceipt:
        timestamp = self._clock()
        return NavigationReceipt(
            operation_id=operation_id,
            operation_kind=operation_kind,
            entity_kind=entity_kind,
            entity_id=entity_id,
            payload_hash=payload_hash,
            result_status="succeeded",
            result_revision=revision,
            result_code=code,
            created_at=timestamp,
            completed_at=timestamp,
        )

    async def _mutate(
        self,
        *,
        table: str,
        entity_kind: str,
        entity_id: str,
        command: BaseModel,
        operation_kind: str,
        entity: BaseModel | None,
        expected_revision: int | None = None,
        mutation: str = "upsert",
        result_code: str,
        statement: str | None = None,
        extra_variables: dict[str, Any] | None = None,
        payload_context: dict[str, Any] | None = None,
    ) -> tuple[Any, NavigationReceipt, bool]:
        operation_id = _operation(command.operation_id)
        _record_id(table, entity_id)
        payload_hash = _payload_hash(
            command, entity_id=entity_id, context=payload_context
        )
        result_revision = getattr(entity, "revision", expected_revision)
        receipt = self._receipt(
            operation_id=operation_id,
            operation_kind=operation_kind,
            entity_kind=entity_kind,
            entity_id=entity_id,
            payload_hash=payload_hash,
            revision=result_revision,
            code=result_code,
        )
        transaction = (
            statement
            or """
            BEGIN TRANSACTION;
            LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt
                WHERE operation_id = $operation_id LIMIT 1);
            IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash {
                RETURN { code: 'operation_conflict' };
            };
            IF array::len($prior) > 0 {
                RETURN { code: 'replayed', prior: $prior,
                    entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $prior[0] };
            };
            LET $current = (SELECT * FROM $entity_id LIMIT 1);
            IF $expected_revision != NONE AND
                (array::len($current) = 0 OR $current[0].revision != $expected_revision) {
                RETURN { code: 'revision_conflict' };
            };
            LET $folder = (SELECT id FROM knowledge_bookmark_folder
                WHERE type::string(id) = $folder_relation_id LIMIT 1);
            IF $folder_relation_id != NONE AND array::len($folder) = 0 {
                RETURN { code: 'folder_parent_not_found' };
            };
            CREATE $receipt_id CONTENT $receipt;
            IF $mutation = 'delete' {
                DELETE $entity_id;
            } ELSE {
                UPSERT $entity_id CONTENT $entity;
            };
            RETURN { code: 'succeeded', prior: $prior,
                entity: (SELECT * FROM $entity_id LIMIT 1), receipt: $receipt };
            COMMIT TRANSACTION;
        """
        )
        variables = {
            "mutation": mutation,
            "table": table,
            "entity_id": _record_id(table, entity_id),
            "entity_relation_id": entity_id,
            "folder_relation_id": None,
            "receipt_id": _record_id(
                "knowledge_navigation_operation_receipt",
                _generated_id("knowledge_navigation_operation_receipt", operation_id),
            ),
            "operation_id": operation_id,
            "payload_hash": payload_hash,
            "expected_revision": expected_revision,
            "entity": _content(entity) if entity is not None else None,
            "receipt": _content(receipt),
        }
        if extra_variables:
            variables.update(extra_variables)
        async with self._connection_factory() as connection:
            try:
                rows = await self._query(connection, transaction, variables)
            except KnowledgeNavigationRepositoryError as error:
                if error.code != "knowledge_navigation_repository_unavailable":
                    raise
                rows = await self._reconcile_operation(operation_id, payload_hash)
        result = next((row for row in reversed(rows) if isinstance(row, dict)), None)
        if result is None:
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_commit_outcome_missing"
            )
        outcome = result.get("code", result.get("error"))
        if outcome in {
            "operation_conflict",
            "revision_conflict",
            "not_found",
            "folder_cycle",
            "folder_depth_exceeded",
            "folder_parent_not_found",
            "workspace_limit_reached",
            "workspace_slot_taken",
            "workspace_allocator_unavailable",
        }:
            raise KnowledgeNavigationRepositoryError(outcome)
        prior = result.get("prior")
        replayed = bool(prior)
        returned_entity = result.get("entity")
        if isinstance(returned_entity, list):
            returned_entity = returned_entity[0] if returned_entity else None
        returned_receipt = result.get("receipt")
        if isinstance(returned_receipt, list):
            returned_receipt = returned_receipt[0] if returned_receipt else None
        if returned_receipt is None:
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_receipt_missing"
            )
        receipt = _receipt_model(returned_receipt)
        if replayed and mutation != "delete":
            if (
                not isinstance(returned_entity, dict)
                or returned_entity.get("revision") != receipt.result_revision
            ):
                raise KnowledgeNavigationRepositoryError(
                    "knowledge_navigation_replay_result_unavailable"
                )
        return returned_entity, receipt, replayed

    async def _reconcile_operation(
        self, operation_id: str, payload_hash: str
    ) -> list[Any]:
        """Map an ambiguous transaction outcome to a durable operation result."""
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM knowledge_navigation_operation_receipt WHERE operation_id = $operation_id LIMIT 1;",
                {"operation_id": operation_id},
            )
        if not rows or not isinstance(rows[0], dict):
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_repository_unavailable"
            )
        receipt = _receipt_model(rows[0])
        if receipt.payload_hash != payload_hash:
            raise KnowledgeNavigationRepositoryError("operation_conflict")
        table = _TABLES.get(receipt.entity_kind)
        entity: Any = None
        if table is not None and receipt.entity_id is not None:
            async with self._connection_factory() as connection:
                entity_rows = await self._query(
                    connection,
                    "SELECT * FROM $entity_id LIMIT 1;",
                    {"entity_id": _record_id(table, receipt.entity_id)},
                )
            entity = entity_rows[0] if entity_rows else None
        return [
            {
                "prior": [receipt.model_dump(mode="python")],
                "entity": entity,
                "receipt": receipt.model_dump(mode="python"),
            }
        ]

    async def _operation_receipt(self, operation_id: str) -> NavigationReceipt | None:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM knowledge_navigation_operation_receipt WHERE operation_id = $operation_id LIMIT 1;",
                {"operation_id": operation_id},
            )
        return _receipt_model(rows[0]) if rows and isinstance(rows[0], dict) else None

    async def _replay_entity(
        self,
        *,
        table: str,
        entity_id: str,
        command: BaseModel,
        model: type[BaseModel],
        payload_context: dict[str, Any] | None = None,
    ) -> Any | None:
        """Return only the exact durable result of a matching prior mutation."""
        payload_hash = _payload_hash(
            command, entity_id=entity_id, context=payload_context
        )
        receipt = await self._operation_receipt(command.operation_id)
        if receipt is None:
            return None
        if receipt.payload_hash != payload_hash:
            raise KnowledgeNavigationRepositoryError("operation_conflict")
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM $entity_id LIMIT 1;",
                {"entity_id": _record_id(table, entity_id)},
            )
        if not rows or not isinstance(rows[0], dict):
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_replay_result_unavailable"
            )
        result = _model(model, rows[0], code=f"{table}_invalid")
        if getattr(result, "revision", None) != receipt.result_revision:
            raise KnowledgeNavigationRepositoryError(
                "knowledge_navigation_replay_result_unavailable"
            )
        return result

    async def _replay_receipt(
        self, *, entity_id: str, command: BaseModel
    ) -> NavigationReceipt | None:
        receipt = await self._operation_receipt(command.operation_id)
        if receipt is None:
            return None
        if receipt.payload_hash != _payload_hash(command, entity_id=entity_id):
            raise KnowledgeNavigationRepositoryError("operation_conflict")
        return receipt

    async def _existing(
        self, table: str, entity_id: str, model: type[BaseModel]
    ) -> Any:
        _record_id(table, entity_id)
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM $entity_id LIMIT 1;",
                {"entity_id": _record_id(table, entity_id)},
            )
        if not rows or not isinstance(rows[0], dict):
            raise LookupError(f"{table}_not_found")
        return _model(model, rows[0], code=f"{table}_invalid")

    async def create_folder(self, command: CreateFolder) -> BookmarkFolder:
        entity_id = _generated_id("knowledge_bookmark_folder", command.operation_id)
        replay = await self._replay_entity(
            table="knowledge_bookmark_folder",
            entity_id=entity_id,
            command=command,
            model=BookmarkFolder,
        )
        if replay is not None:
            return replay
        await self._validate_folder_parent(command.parent_folder_id)
        timestamp = self._clock()
        folder = BookmarkFolder(
            id=entity_id,
            name=command.name,
            name_key=command.name_key,
            parent_folder_id=command.parent_folder_id,
            position=command.position,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        row, _, _ = await self._mutate(
            table="knowledge_bookmark_folder",
            entity_kind="folder",
            entity_id=entity_id,
            command=command,
            operation_kind="create_folder",
            entity=folder,
            result_code="created",
            statement=_folder_create_transaction()
            if command.parent_folder_id is not None
            else None,
            extra_variables={
                "folder_relation_id": command.parent_folder_id,
                "new_parent_relation_id": command.parent_folder_id,
            }
            if command.parent_folder_id is not None
            else {"folder_relation_id": None},
        )
        return _model(BookmarkFolder, row, code="knowledge_navigation_folder_invalid")

    async def update_folder(
        self, folder_id: str, command: UpdateFolder
    ) -> BookmarkFolder:
        replay = await self._replay_entity(
            table="knowledge_bookmark_folder",
            entity_id=folder_id,
            command=command,
            model=BookmarkFolder,
        )
        if replay is not None:
            return replay
        existing = await self._existing(
            "knowledge_bookmark_folder", folder_id, BookmarkFolder
        )
        if "parent_folder_id" in command.model_fields_set:
            subtree_height = await self._folder_subtree_height(folder_id)
            await self._validate_folder_parent(
                command.parent_folder_id,
                moving_folder_id=folder_id,
                moving_subtree_height=subtree_height,
            )
        else:
            subtree_height = 1
        data = existing.model_dump(mode="python")
        for field in command.model_fields_set - {"operation_id", "expected_revision"}:
            data[field] = getattr(command, field)
        data.update(revision=existing.revision + 1, updated_at=self._clock())
        folder = BookmarkFolder.model_validate(data)
        row, _, _ = await self._mutate(
            table="knowledge_bookmark_folder",
            entity_kind="folder",
            entity_id=folder_id,
            command=command,
            operation_kind="update_folder",
            entity=folder,
            expected_revision=command.expected_revision,
            result_code="updated",
            statement=_folder_reparent_transaction()
            if "parent_folder_id" in command.model_fields_set
            and command.parent_folder_id is not None
            else None,
            extra_variables={
                "new_parent_relation_id": command.parent_folder_id,
                "subtree_height": subtree_height,
                "folder_relation_id": command.parent_folder_id,
            }
            if "parent_folder_id" in command.model_fields_set
            and command.parent_folder_id is not None
            else None,
        )
        return _model(BookmarkFolder, row, code="knowledge_navigation_folder_invalid")

    async def delete_folder(
        self, folder_id: str, command: DeleteFolder
    ) -> NavigationReceipt:
        _record_id("knowledge_bookmark_folder", folder_id)
        replay = await self._replay_receipt(entity_id=folder_id, command=command)
        if replay is not None:
            return replay
        tree_sql = """
            BEGIN TRANSACTION;
            LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt WHERE operation_id = $operation_id LIMIT 1);
            IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash { RETURN { code: 'operation_conflict' }; };
            IF array::len($prior) > 0 { RETURN { code: 'replayed', prior: $prior, receipt: $prior[0] }; };
            LET $current = (SELECT * FROM $entity_id LIMIT 1);
            IF array::len($current) = 0 OR $current[0].revision != $expected_revision { RETURN { code: 'revision_conflict' }; };
            CREATE $receipt_id CONTENT $receipt;
            IF $child_disposition = 'move_children' {
                    UPDATE knowledge_bookmark_folder SET parent_folder_id = $current[0].parent_folder_id, revision = revision + 1, updated_at = $mutation_time WHERE parent_folder_id = $entity_relation_id;
                    UPDATE knowledge_bookmark SET folder_id = $current[0].parent_folder_id, revision = revision + 1, updated_at = $mutation_time WHERE folder_id = $entity_relation_id;
                    DELETE $entity_id;
            } ELSE {
                    LET $level_0 = [$entity_relation_id];
                    LET $level_1 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_0);
                    LET $level_2 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_1);
                    LET $level_3 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_2);
                    LET $level_4 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_3);
                    LET $level_5 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_4);
                    LET $level_6 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_5);
                    LET $level_7 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_6);
                    LET $level_8 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_7);
                    LET $level_9 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_8);
                    LET $level_10 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_9);
                    LET $level_11 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_10);
                    LET $level_12 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_11);
                    LET $level_13 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_12);
                    LET $level_14 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_13);
                    LET $level_15 = (SELECT VALUE type::string(id) FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_14);
                    LET $tree = array::flatten([$level_0, $level_1, $level_2, $level_3, $level_4, $level_5, $level_6, $level_7, $level_8, $level_9, $level_10, $level_11, $level_12, $level_13, $level_14, $level_15]);
                    DELETE knowledge_bookmark WHERE folder_id IN $tree;
                    DELETE knowledge_bookmark_folder WHERE type::string(id) IN $tree;
            };
            RETURN { code: 'succeeded', prior: $prior, receipt: $receipt };
            COMMIT TRANSACTION;
        """
        _, receipt, _ = await self._mutate(
            table="knowledge_bookmark_folder",
            entity_kind="folder",
            entity_id=folder_id,
            command=command,
            operation_kind="delete_folder",
            entity=None,
            expected_revision=command.expected_revision,
            mutation="delete",
            result_code="deleted",
            statement=tree_sql,
            extra_variables={
                "child_disposition": command.child_disposition,
                "mutation_time": self._clock(),
            },
        )
        return receipt

    async def list_folders(self) -> list[BookmarkFolder]:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM knowledge_bookmark_folder ORDER BY parent_folder_id, position, name_key, id;",
            )
        return [
            _model(BookmarkFolder, row, code="knowledge_navigation_folder_invalid")
            for row in rows
        ]

    async def create_bookmark(self, command: CreateBookmark) -> Bookmark:
        entity_id = _generated_id("knowledge_bookmark", command.operation_id)
        replay = await self._replay_entity(
            table="knowledge_bookmark",
            entity_id=entity_id,
            command=command,
            model=Bookmark,
        )
        if replay is not None:
            return replay
        if command.folder_id is not None:
            await self._folder_ancestry(command.folder_id)
        timestamp = self._clock()
        bookmark = Bookmark(
            id=entity_id,
            target_kind=command.target.kind,
            target=command.target,
            display_label=command.display_label,
            authority_kind=command.authority_kind,
            space_id=command.space_id,
            folder_id=command.folder_id,
            tags=command.tags,
            position=command.position,
            revision=1,
            created_at=timestamp,
            updated_at=timestamp,
        )
        row, _, _ = await self._mutate(
            table="knowledge_bookmark",
            entity_kind="bookmark",
            entity_id=entity_id,
            command=command,
            operation_kind="create_bookmark",
            entity=bookmark,
            result_code="created",
            extra_variables={"folder_relation_id": command.folder_id},
        )
        return _model(Bookmark, row, code="knowledge_navigation_bookmark_invalid")

    async def update_bookmark(
        self, bookmark_id: str, command: UpdateBookmark
    ) -> Bookmark:
        replay = await self._replay_entity(
            table="knowledge_bookmark",
            entity_id=bookmark_id,
            command=command,
            model=Bookmark,
        )
        if replay is not None:
            return replay
        existing = await self._existing("knowledge_bookmark", bookmark_id, Bookmark)
        if "folder_id" in command.model_fields_set and command.folder_id is not None:
            await self._folder_ancestry(command.folder_id)
        data = existing.model_dump(mode="python")
        for field in command.model_fields_set - {"operation_id", "expected_revision"}:
            data[field] = getattr(command, field)
        if "target" in command.model_fields_set:
            data["target_kind"] = command.target.kind
        data.update(revision=existing.revision + 1, updated_at=self._clock())
        bookmark = Bookmark.model_validate(data)
        row, _, _ = await self._mutate(
            table="knowledge_bookmark",
            entity_kind="bookmark",
            entity_id=bookmark_id,
            command=command,
            operation_kind="update_bookmark",
            entity=bookmark,
            expected_revision=command.expected_revision,
            result_code="updated",
            extra_variables={"folder_relation_id": bookmark.folder_id},
        )
        return _model(Bookmark, row, code="knowledge_navigation_bookmark_invalid")

    async def delete_bookmark(
        self, bookmark_id: str, command: DeleteBookmark
    ) -> NavigationReceipt:
        replay = await self._replay_receipt(entity_id=bookmark_id, command=command)
        if replay is not None:
            return replay
        _, receipt, _ = await self._mutate(
            table="knowledge_bookmark",
            entity_kind="bookmark",
            entity_id=bookmark_id,
            command=command,
            operation_kind="delete_bookmark",
            entity=None,
            expected_revision=command.expected_revision,
            mutation="delete",
            result_code="deleted",
        )
        return receipt

    async def list_bookmarks(
        self, filters: BookmarkFilters, cursor: str | None, limit: int
    ) -> BookmarkPage:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise ValueError("invalid_bookmark_limit")
        parsed_cursor = BookmarkCursor.decode(cursor) if cursor is not None else None
        variables = {
            "folder_id": filters.folder_id,
            "tags": filters.tags,
            "target_kinds": filters.target_kinds,
            "space_ids": filters.space_ids,
            "authority_kinds": filters.authority_kinds,
            "limit": limit + 1,
            "cursor_folder_id": parsed_cursor.folder_id if parsed_cursor else None,
            "cursor_position": parsed_cursor.position if parsed_cursor else None,
            "cursor_id": _record_id("knowledge_bookmark", parsed_cursor.id)
            if parsed_cursor
            else None,
        }
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM knowledge_bookmark
                WHERE ($folder_id = NONE OR folder_id = $folder_id)
                    AND (array::len($tags) = 0 OR array::len(array::intersect(tags, $tags)) = array::len($tags))
                    AND (array::len($target_kinds) = 0 OR target_kind IN $target_kinds)
                    AND (array::len($space_ids) = 0 OR space_id IN $space_ids)
                    AND (array::len($authority_kinds) = 0 OR authority_kind IN $authority_kinds)
                    AND ($cursor_id = NONE OR folder_id > $cursor_folder_id
                        OR (folder_id = $cursor_folder_id AND position > $cursor_position)
                        OR (folder_id = $cursor_folder_id AND position = $cursor_position AND id > $cursor_id))
                ORDER BY folder_id, position, id LIMIT $limit;
                """,
                variables,
            )
        items = [
            _model(Bookmark, row, code="knowledge_navigation_bookmark_invalid")
            for row in rows[:limit]
        ]
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = BookmarkCursor(
                folder_id=last.folder_id, position=last.position, id=last.id
            ).encode()
        return BookmarkPage(items=items, next_cursor=next_cursor)

    async def create_workspace(
        self, command: CreateWorkspace
    ) -> NamedKnowledgeWorkspace:
        entity_id = _generated_id("named_knowledge_workspace", command.operation_id)
        replay = await self._replay_entity(
            table="named_knowledge_workspace",
            entity_id=entity_id,
            command=command,
            model=NamedKnowledgeWorkspace,
        )
        if replay is not None:
            return replay
        return await self._create_workspace_with_capacity(
            entity_id=entity_id,
            command=command,
            operation_kind="create_workspace",
            snapshot=command.snapshot,
        )

    async def update_workspace(
        self, workspace_id: str, command: UpdateWorkspace
    ) -> NamedKnowledgeWorkspace:
        replay = await self._replay_entity(
            table="named_knowledge_workspace",
            entity_id=workspace_id,
            command=command,
            model=NamedKnowledgeWorkspace,
        )
        if replay is not None:
            return replay
        existing = await self._existing(
            "named_knowledge_workspace", workspace_id, NamedKnowledgeWorkspace
        )
        has_name = "name" in command.model_fields_set
        has_snapshot = "snapshot" in command.model_fields_set
        if has_name == has_snapshot:
            raise ValueError("workspace updates must rename or replace a snapshot")
        data = existing.model_dump(mode="python")
        if has_name:
            data["name"] = command.name
            data["name_key"] = command.name_key
        else:
            data["snapshot"] = command.snapshot
        data.update(revision=existing.revision + 1, updated_at=self._clock())
        workspace = NamedKnowledgeWorkspace.model_validate(data)
        row, _, _ = await self._mutate(
            table="named_knowledge_workspace",
            entity_kind="workspace",
            entity_id=workspace_id,
            command=command,
            operation_kind="update_workspace",
            entity=workspace,
            expected_revision=command.expected_revision,
            result_code="updated",
        )
        return _model(
            NamedKnowledgeWorkspace, row, code="knowledge_navigation_workspace_invalid"
        )

    async def duplicate_workspace(
        self, workspace_id: str, command: DuplicateWorkspace
    ) -> NamedKnowledgeWorkspace:
        entity_id = _generated_id("named_knowledge_workspace", command.operation_id)
        replay = await self._replay_entity(
            table="named_knowledge_workspace",
            entity_id=entity_id,
            command=command,
            model=NamedKnowledgeWorkspace,
            payload_context={"source_workspace_id": workspace_id},
        )
        if replay is not None:
            return replay
        source = await self.get_workspace(workspace_id)
        return await self._create_workspace_with_capacity(
            entity_id=entity_id,
            command=command,
            operation_kind="duplicate_workspace",
            snapshot=source.snapshot,
            payload_context={"source_workspace_id": workspace_id},
        )

    async def delete_workspace(
        self, workspace_id: str, command: DeleteWorkspace
    ) -> NavigationReceipt:
        replay = await self._replay_receipt(entity_id=workspace_id, command=command)
        if replay is not None:
            return replay
        _, receipt, _ = await self._mutate(
            table="named_knowledge_workspace",
            entity_kind="workspace",
            entity_id=workspace_id,
            command=command,
            operation_kind="delete_workspace",
            entity=None,
            expected_revision=command.expected_revision,
            mutation="delete",
            result_code="deleted",
            statement=_workspace_delete_transaction(),
            extra_variables={
                "workspace_allocator_id": _record_id(
                    "named_knowledge_workspace", _WORKSPACE_ALLOCATOR_ID
                ),
            },
        )
        return receipt

    async def get_workspace(self, workspace_id: str) -> NamedKnowledgeWorkspace:
        return await self._existing(
            "named_knowledge_workspace", workspace_id, NamedKnowledgeWorkspace
        )

    async def list_workspaces(self) -> list[NamedKnowledgeWorkspaceSummary]:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT id, name, name_key, revision, updated_at "
                "FROM named_knowledge_workspace "
                "WHERE id != $workspace_allocator_id ORDER BY name_key, id "
                "LIMIT $limit;",
                {
                    "limit": MAX_NAMED_WORKSPACES + 1,
                    "workspace_allocator_id": _record_id(
                        "named_knowledge_workspace", _WORKSPACE_ALLOCATOR_ID
                    ),
                },
            )
        if len(rows) > MAX_NAMED_WORKSPACES:
            raise KnowledgeNavigationRepositoryError("workspace_collection_too_large")
        return [
            _model(
                NamedKnowledgeWorkspaceSummary,
                {key: value for key, value in row.items() if key != "name_key"},
                code="knowledge_navigation_workspace_invalid",
            )
            for row in rows
        ]

    async def _next_workspace_slot(self) -> int | None:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT id, capacity_slot FROM named_knowledge_workspace "
                "WHERE id != $workspace_allocator_id ORDER BY capacity_slot "
                "LIMIT $limit;",
                {
                    "limit": MAX_NAMED_WORKSPACES + 1,
                    "workspace_allocator_id": _record_id(
                        "named_knowledge_workspace", _WORKSPACE_ALLOCATOR_ID
                    ),
                },
            )
        if len(rows) > MAX_NAMED_WORKSPACES:
            raise KnowledgeNavigationRepositoryError("workspace_collection_too_large")
        occupied: set[int] = set()
        for row in rows:
            slot = row.get("capacity_slot") if isinstance(row, dict) else None
            if (
                isinstance(slot, bool)
                or not isinstance(slot, int)
                or not 0 <= slot < MAX_NAMED_WORKSPACES
            ):
                raise KnowledgeNavigationRepositoryError("workspace_collection_invalid")
            occupied.add(slot)
        if len(occupied) != len(rows):
            raise KnowledgeNavigationRepositoryError("workspace_collection_invalid")
        return next(
            (slot for slot in range(MAX_NAMED_WORKSPACES) if slot not in occupied),
            None,
        )

    async def _create_workspace_with_capacity(
        self,
        *,
        entity_id: str,
        command: CreateWorkspace | DuplicateWorkspace,
        operation_kind: str,
        snapshot: Any,
        payload_context: dict[str, Any] | None = None,
    ) -> NamedKnowledgeWorkspace:
        for _ in range(MAX_NAMED_WORKSPACES):
            slot = await self._next_workspace_slot()
            if slot is None:
                raise KnowledgeNavigationRepositoryError("workspace_limit_reached")
            timestamp = self._clock()
            workspace = NamedKnowledgeWorkspace(
                id=entity_id,
                name=command.name,
                name_key=command.name_key,
                snapshot=snapshot,
                capacity_slot=slot,
                revision=1,
                created_at=timestamp,
                updated_at=timestamp,
            )
            try:
                row, _, _ = await self._mutate(
                    table="named_knowledge_workspace",
                    entity_kind="workspace",
                    entity_id=entity_id,
                    command=command,
                    operation_kind=operation_kind,
                    entity=workspace,
                    result_code="created",
                    statement=_workspace_create_transaction(),
                    extra_variables={
                        "capacity_slot": slot,
                        "workspace_allocator_id": _record_id(
                            "named_knowledge_workspace",
                            _WORKSPACE_ALLOCATOR_ID,
                        ),
                    },
                    payload_context=payload_context,
                )
            except KnowledgeNavigationRepositoryError as error:
                if error.code not in {
                    "workspace_slot_taken",
                    "knowledge_navigation_repository_unavailable",
                }:
                    raise
                replay = await self._replay_entity(
                    table="named_knowledge_workspace",
                    entity_id=entity_id,
                    command=command,
                    model=NamedKnowledgeWorkspace,
                    payload_context=payload_context,
                )
                if replay is not None:
                    return replay
                continue
            return _model(
                NamedKnowledgeWorkspace,
                row,
                code="knowledge_navigation_workspace_invalid",
            )
        raise KnowledgeNavigationRepositoryError("workspace_limit_reached")

    async def random_candidate_count(self, filters: RandomNoteFilters) -> int:
        variables = {
            "space_ids": filters.space_ids,
            "authority_kinds": filters.authority_kinds,
            "tags": filters.tags,
        }
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection, self._random_where("count() AS count"), variables
            )
        return int(rows[0].get("count", 0)) if rows and isinstance(rows[0], dict) else 0

    async def random_candidate_at(
        self, filters: RandomNoteFilters, offset: int
    ) -> KnowledgeOpenDescriptor | None:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("invalid_random_candidate_offset")
        variables = {
            "space_ids": filters.space_ids,
            "authority_kinds": filters.authority_kinds,
            "tags": filters.tags,
            "offset": offset,
        }
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                self._random_where(_OPEN_DESCRIPTOR_FIELDS) + " LIMIT 1 START $offset;",
                variables,
            )
        return (
            _model(
                KnowledgeOpenDescriptor,
                rows[0],
                code="knowledge_navigation_descriptor_invalid",
            )
            if rows
            else None
        )

    @staticmethod
    def _random_where(fields: str) -> str:
        suffix = " GROUP ALL" if fields == "count() AS count" else " ORDER BY id"
        return f"""SELECT {fields} FROM knowledge_engine_document WHERE availability = "available" AND parse_state = "ready" AND document_kind IN ["note", "page", "journal"] AND "read" IN capabilities AND (array::len($space_ids) = 0 OR space_id IN $space_ids) AND (array::len($authority_kinds) = 0 OR authority_kind IN $authority_kinds) AND (array::len($tags) = 0 OR array::len(array::intersect(tags, $tags)) = array::len($tags)){suffix}"""


__all__ = ["KnowledgeNavigationRepository", "KnowledgeNavigationRepositoryError"]
