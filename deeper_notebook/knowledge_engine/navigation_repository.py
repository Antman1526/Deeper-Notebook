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
_OPEN_DESCRIPTOR_FIELDS = (
    "id AS document_id, space_id, authority_kind, "
    "(SELECT VALUE source_kind FROM knowledge_engine_space "
    "WHERE id = $parent.space_id LIMIT 1)[0] AS source_kind, title, "
    "relative_locator, source_native_id AS legacy_note_id, "
    "(SELECT VALUE source_ref FROM knowledge_engine_space "
    "WHERE id = $parent.space_id LIMIT 1)[0] AS legacy_container_id"
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


def _payload_hash(command: BaseModel, *, entity_id: str | None = None) -> str:
    payload = command.model_dump(mode="json", exclude={"operation_id"})
    if entity_id is not None:
        payload["entity_id"] = entity_id
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return sha256(encoded).hexdigest()


def _generated_id(table: str, operation_id: str) -> str:
    return f"{table}:{sha256(operation_id.encode()).hexdigest()}"


def _content(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="python", exclude={"id"})


def _model(model: type[BaseModel], value: Any, *, code: str) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError:
        raise KnowledgeNavigationRepositoryError(code) from None


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
                    {"read": "folder_parent", "folder_id": _record_id("knowledge_bookmark_folder", current_id)},
                )
            row = rows[0] if rows else None
            if not isinstance(row, dict):
                raise KnowledgeNavigationRepositoryError("folder_parent_not_found")
            current_id = row.get("parent_folder_id")
        return ancestry

    async def _validate_folder_parent(
        self, parent_folder_id: str | None, *, moving_folder_id: str | None = None
    ) -> None:
        if parent_folder_id is None:
            return
        _record_id("knowledge_bookmark_folder", parent_folder_id)
        ancestry = await self._folder_ancestry(parent_folder_id)
        if moving_folder_id is not None and moving_folder_id in ancestry:
            raise KnowledgeNavigationRepositoryError("folder_cycle")
        if len(ancestry) >= 16:
            raise KnowledgeNavigationRepositoryError("folder_depth_exceeded")

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
    ) -> tuple[Any, NavigationReceipt, bool]:
        operation_id = _operation(command.operation_id)
        _record_id(table, entity_id)
        payload_hash = _payload_hash(command, entity_id=entity_id)
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
        transaction = statement or """
            BEGIN TRANSACTION;
            LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt
                WHERE operation_id = $operation_id LIMIT 1);
            IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash {
                THROW 'operation_conflict';
            };
            LET $current = (SELECT * FROM $entity_id LIMIT 1);
            IF $expected_revision != NONE AND
                (array::len($current) = 0 OR $current[0].revision != $expected_revision) {
                THROW 'revision_conflict';
            };
            IF array::len($prior) = 0 {
                CREATE $receipt_id CONTENT $receipt;
                IF $mutation = 'delete' {
                    DELETE $entity_id;
                } ELSE {
                    UPSERT $entity_id CONTENT $entity;
                };
            };
            COMMIT TRANSACTION;
            RETURN { prior: $prior, entity: (SELECT * FROM $entity_id LIMIT 1),
                receipt: (SELECT * FROM $receipt_id LIMIT 1) };
        """
        variables = {
            "mutation": mutation,
            "table": table,
            "entity_id": _record_id(table, entity_id),
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
            raise KnowledgeNavigationRepositoryError("knowledge_navigation_commit_outcome_missing")
        error = result.get("error")
        if error in {"operation_conflict", "revision_conflict", "not_found"}:
            raise KnowledgeNavigationRepositoryError(error)
        prior = result.get("prior")
        replayed = bool(prior)
        returned_entity = result.get("entity")
        if isinstance(returned_entity, list):
            returned_entity = returned_entity[0] if returned_entity else None
        returned_receipt = result.get("receipt")
        if isinstance(returned_receipt, list):
            returned_receipt = returned_receipt[0] if returned_receipt else None
        if returned_receipt is None:
            raise KnowledgeNavigationRepositoryError("knowledge_navigation_receipt_missing")
        return returned_entity, _model(
            NavigationReceipt, returned_receipt, code="knowledge_navigation_receipt_invalid"
        ), replayed

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
        receipt = _model(
            NavigationReceipt,
            rows[0],
            code="knowledge_navigation_receipt_invalid",
        )
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
        return [{"prior": [receipt.model_dump(mode="python")], "entity": entity, "receipt": receipt.model_dump(mode="python")}]

    async def _existing(self, table: str, entity_id: str, model: type[BaseModel]) -> Any:
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
        await self._validate_folder_parent(command.parent_folder_id)
        entity_id = _generated_id("knowledge_bookmark_folder", command.operation_id)
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
            table="knowledge_bookmark_folder", entity_kind="folder", entity_id=entity_id,
            command=command, operation_kind="create_folder", entity=folder,
            result_code="created",
        )
        return _model(BookmarkFolder, row, code="knowledge_navigation_folder_invalid")

    async def update_folder(self, folder_id: str, command: UpdateFolder) -> BookmarkFolder:
        existing = await self._existing("knowledge_bookmark_folder", folder_id, BookmarkFolder)
        if "parent_folder_id" in command.model_fields_set:
            await self._validate_folder_parent(command.parent_folder_id, moving_folder_id=folder_id)
        data = existing.model_dump(mode="python")
        for field in command.model_fields_set - {"operation_id", "expected_revision"}:
            data[field] = getattr(command, field)
        data.update(revision=existing.revision + 1, updated_at=self._clock())
        folder = BookmarkFolder.model_validate(data)
        row, _, _ = await self._mutate(
            table="knowledge_bookmark_folder", entity_kind="folder", entity_id=folder_id,
            command=command, operation_kind="update_folder", entity=folder,
            expected_revision=command.expected_revision, result_code="updated",
        )
        return _model(BookmarkFolder, row, code="knowledge_navigation_folder_invalid")

    async def delete_folder(self, folder_id: str, command: DeleteFolder) -> NavigationReceipt:
        _record_id("knowledge_bookmark_folder", folder_id)
        tree_sql = """
            BEGIN TRANSACTION;
            LET $prior = (SELECT * FROM knowledge_navigation_operation_receipt WHERE operation_id = $operation_id LIMIT 1);
            IF array::len($prior) > 0 AND $prior[0].payload_hash != $payload_hash { THROW 'operation_conflict'; };
            LET $current = (SELECT * FROM $entity_id LIMIT 1);
            IF array::len($current) = 0 OR $current[0].revision != $expected_revision { THROW 'revision_conflict'; };
            IF array::len($prior) = 0 {
                CREATE $receipt_id CONTENT $receipt;
                IF $child_disposition = 'move_children' {
                    UPDATE knowledge_bookmark_folder SET parent_folder_id = $current[0].parent_folder_id WHERE parent_folder_id = $entity_id;
                    UPDATE knowledge_bookmark SET folder_id = $current[0].parent_folder_id WHERE folder_id = $entity_id;
                    DELETE $entity_id;
                } ELSE {
                    LET $level_0 = [$entity_id];
                    LET $level_1 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_0);
                    LET $level_2 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_1);
                    LET $level_3 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_2);
                    LET $level_4 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_3);
                    LET $level_5 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_4);
                    LET $level_6 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_5);
                    LET $level_7 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_6);
                    LET $level_8 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_7);
                    LET $level_9 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_8);
                    LET $level_10 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_9);
                    LET $level_11 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_10);
                    LET $level_12 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_11);
                    LET $level_13 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_12);
                    LET $level_14 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_13);
                    LET $level_15 = (SELECT VALUE id FROM knowledge_bookmark_folder WHERE parent_folder_id IN $level_14);
                    LET $tree = array::flatten([$level_0, $level_1, $level_2, $level_3, $level_4, $level_5, $level_6, $level_7, $level_8, $level_9, $level_10, $level_11, $level_12, $level_13, $level_14, $level_15]);
                    DELETE knowledge_bookmark WHERE folder_id = $entity_id OR folder_id IN $tree;
                    DELETE knowledge_bookmark_folder WHERE id IN $tree;
                };
            };
            COMMIT TRANSACTION;
            RETURN { prior: $prior, receipt: (SELECT * FROM $receipt_id LIMIT 1) };
        """
        _, receipt, _ = await self._mutate(
            table="knowledge_bookmark_folder", entity_kind="folder", entity_id=folder_id,
            command=command, operation_kind="delete_folder", entity=None,
            expected_revision=command.expected_revision, mutation="delete", result_code="deleted",
            statement=tree_sql, extra_variables={"child_disposition": command.child_disposition},
        )
        return receipt

    async def list_folders(self) -> list[BookmarkFolder]:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM knowledge_bookmark_folder ORDER BY parent_folder_id, position, name_key, id;",
            )
        return [_model(BookmarkFolder, row, code="knowledge_navigation_folder_invalid") for row in rows]

    async def create_bookmark(self, command: CreateBookmark) -> Bookmark:
        if command.folder_id is not None:
            await self._folder_ancestry(command.folder_id)
        entity_id = _generated_id("knowledge_bookmark", command.operation_id)
        timestamp = self._clock()
        bookmark = Bookmark(
            id=entity_id, target_kind=command.target.kind, target=command.target,
            display_label=command.display_label, authority_kind=command.authority_kind,
            space_id=command.space_id, folder_id=command.folder_id, tags=command.tags,
            position=command.position, revision=1, created_at=timestamp, updated_at=timestamp,
        )
        row, _, _ = await self._mutate(
            table="knowledge_bookmark", entity_kind="bookmark", entity_id=entity_id,
            command=command, operation_kind="create_bookmark", entity=bookmark,
            result_code="created",
        )
        return _model(Bookmark, row, code="knowledge_navigation_bookmark_invalid")

    async def update_bookmark(self, bookmark_id: str, command: UpdateBookmark) -> Bookmark:
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
            table="knowledge_bookmark", entity_kind="bookmark", entity_id=bookmark_id,
            command=command, operation_kind="update_bookmark", entity=bookmark,
            expected_revision=command.expected_revision, result_code="updated",
        )
        return _model(Bookmark, row, code="knowledge_navigation_bookmark_invalid")

    async def delete_bookmark(self, bookmark_id: str, command: DeleteBookmark) -> NavigationReceipt:
        _, receipt, _ = await self._mutate(
            table="knowledge_bookmark", entity_kind="bookmark", entity_id=bookmark_id,
            command=command, operation_kind="delete_bookmark", entity=None,
            expected_revision=command.expected_revision, mutation="delete", result_code="deleted",
        )
        return receipt

    async def list_bookmarks(self, filters: BookmarkFilters, cursor: str | None, limit: int) -> BookmarkPage:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("invalid_bookmark_limit")
        parsed_cursor = BookmarkCursor.decode(cursor) if cursor is not None else None
        variables = {
            "folder_id": filters.folder_id, "tags": filters.tags,
            "target_kinds": filters.target_kinds, "space_ids": filters.space_ids,
            "authority_kinds": filters.authority_kinds, "limit": limit + 1,
            "cursor_folder_id": parsed_cursor.folder_id if parsed_cursor else None,
            "cursor_position": parsed_cursor.position if parsed_cursor else None,
            "cursor_id": parsed_cursor.id if parsed_cursor else None,
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
        items = [_model(Bookmark, row, code="knowledge_navigation_bookmark_invalid") for row in rows[:limit]]
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = BookmarkCursor(folder_id=last.folder_id, position=last.position, id=last.id).encode()
        return BookmarkPage(items=items, next_cursor=next_cursor)

    async def create_workspace(self, command: CreateWorkspace) -> NamedKnowledgeWorkspace:
        entity_id = _generated_id("named_knowledge_workspace", command.operation_id)
        timestamp = self._clock()
        workspace = NamedKnowledgeWorkspace(id=entity_id, name=command.name, name_key=command.name_key, snapshot=command.snapshot, revision=1, created_at=timestamp, updated_at=timestamp)
        row, _, _ = await self._mutate(table="named_knowledge_workspace", entity_kind="workspace", entity_id=entity_id, command=command, operation_kind="create_workspace", entity=workspace, result_code="created")
        return _model(NamedKnowledgeWorkspace, row, code="knowledge_navigation_workspace_invalid")

    async def update_workspace(self, workspace_id: str, command: UpdateWorkspace) -> NamedKnowledgeWorkspace:
        existing = await self._existing("named_knowledge_workspace", workspace_id, NamedKnowledgeWorkspace)
        data = existing.model_dump(mode="python")
        for field in command.model_fields_set - {"operation_id", "expected_revision"}:
            data[field] = getattr(command, field)
        data.update(revision=existing.revision + 1, updated_at=self._clock())
        workspace = NamedKnowledgeWorkspace.model_validate(data)
        row, _, _ = await self._mutate(table="named_knowledge_workspace", entity_kind="workspace", entity_id=workspace_id, command=command, operation_kind="update_workspace", entity=workspace, expected_revision=command.expected_revision, result_code="updated")
        return _model(NamedKnowledgeWorkspace, row, code="knowledge_navigation_workspace_invalid")

    async def duplicate_workspace(self, workspace_id: str, command: DuplicateWorkspace) -> NamedKnowledgeWorkspace:
        source = await self.get_workspace(workspace_id)
        entity_id = _generated_id("named_knowledge_workspace", command.operation_id)
        timestamp = self._clock()
        workspace = NamedKnowledgeWorkspace(id=entity_id, name=command.name, name_key=command.name_key, snapshot=source.snapshot, revision=1, created_at=timestamp, updated_at=timestamp)
        row, _, _ = await self._mutate(table="named_knowledge_workspace", entity_kind="workspace", entity_id=entity_id, command=command, operation_kind="duplicate_workspace", entity=workspace, result_code="created")
        return _model(NamedKnowledgeWorkspace, row, code="knowledge_navigation_workspace_invalid")

    async def delete_workspace(self, workspace_id: str, command: DeleteWorkspace) -> NavigationReceipt:
        _, receipt, _ = await self._mutate(table="named_knowledge_workspace", entity_kind="workspace", entity_id=workspace_id, command=command, operation_kind="delete_workspace", entity=None, expected_revision=command.expected_revision, mutation="delete", result_code="deleted")
        return receipt

    async def get_workspace(self, workspace_id: str) -> NamedKnowledgeWorkspace:
        return await self._existing("named_knowledge_workspace", workspace_id, NamedKnowledgeWorkspace)

    async def list_workspaces(self) -> list[NamedKnowledgeWorkspaceSummary]:
        async with self._connection_factory() as connection:
            rows = await self._query(connection, "SELECT id, name, revision, updated_at FROM named_knowledge_workspace ORDER BY name_key, id;")
        return [_model(NamedKnowledgeWorkspaceSummary, row, code="knowledge_navigation_workspace_invalid") for row in rows]

    async def random_candidate_count(self, filters: RandomNoteFilters) -> int:
        variables = {"space_ids": filters.space_ids, "authority_kinds": filters.authority_kinds, "tags": filters.tags}
        async with self._connection_factory() as connection:
            rows = await self._query(connection, self._random_where("count() AS count"), variables)
        return int(rows[0].get("count", 0)) if rows and isinstance(rows[0], dict) else 0

    async def random_candidate_at(self, filters: RandomNoteFilters, offset: int) -> KnowledgeOpenDescriptor | None:
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("invalid_random_candidate_offset")
        variables = {"space_ids": filters.space_ids, "authority_kinds": filters.authority_kinds, "tags": filters.tags, "offset": offset}
        async with self._connection_factory() as connection:
            rows = await self._query(connection, self._random_where(_OPEN_DESCRIPTOR_FIELDS) + " LIMIT 1 START $offset;", variables)
        return _model(KnowledgeOpenDescriptor, rows[0], code="knowledge_navigation_descriptor_invalid") if rows else None

    @staticmethod
    def _random_where(fields: str) -> str:
        return f'''SELECT {fields} FROM knowledge_engine_document WHERE availability = "available" AND parse_state = "ready" AND document_kind IN ["note", "page", "journal"] AND "read" IN capabilities AND (array::len($space_ids) = 0 OR space_id IN $space_ids) AND (array::len($authority_kinds) = 0 OR authority_kind IN $authority_kinds) AND (array::len($tags) = 0 OR array::len(array::intersect(tags, $tags)) = array::len($tags))'''


__all__ = ["KnowledgeNavigationRepository", "KnowledgeNavigationRepositoryError"]
