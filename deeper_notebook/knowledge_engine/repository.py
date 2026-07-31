"""Transactional persistence for unified knowledge-engine snapshots."""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from deeper_notebook.database.repository import (
    db_connection,
    ensure_record_id,
    parse_record_ids,
)
from deeper_notebook.knowledge_engine.contracts import (
    BackfillCheckpoint,
    KnowledgeDocument,
    KnowledgeSnapshot,
    ProjectionDigest,
    ProjectionReceipt,
)
from deeper_notebook.knowledge_engine.identity import canonical_locator
from deeper_notebook.knowledge_engine.navigation_contracts import (
    KnowledgeBlockId,
    KnowledgeDocumentId,
    KnowledgeOpenDescriptor,
    KnowledgeRevisionId,
)

_ID_PATTERNS = {
    "space": re.compile(r"^knowledge_engine_space:[A-Za-z0-9_-]+$"),
    "document": re.compile(r"^knowledge_engine_document:[A-Za-z0-9_-]+$"),
    "block": re.compile(r"^knowledge_engine_block:[A-Za-z0-9_-]+$"),
    "relation": re.compile(r"^knowledge_engine_relation:[A-Za-z0-9_-]+$"),
    "task": re.compile(r"^knowledge_engine_task:[A-Za-z0-9_-]+$"),
    "asset": re.compile(r"^knowledge_engine_asset:[A-Za-z0-9_-]+$"),
    "revision": re.compile(r"^knowledge_engine_revision:[A-Za-z0-9_-]+$"),
    "receipt": re.compile(r"^knowledge_engine_projection_receipt:[A-Za-z0-9_-]+$"),
    "checkpoint": re.compile(r"^knowledge_engine_backfill_checkpoint:[A-Za-z0-9_-]+$"),
}
_OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_ERROR_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_DESCRIPTOR_LEGACY_IDS = {
    "overlay": (
        re.compile(r"^overlay_note:[A-Za-z0-9_-]+$"),
        re.compile(r"^overlay_space:[A-Za-z0-9_-]+$"),
        "overlay_note",
        "overlay_space",
    ),
    "external": (
        re.compile(r"^note:[A-Za-z0-9_-]+$"),
        re.compile(r"^vault_mount:[A-Za-z0-9_-]+$"),
        "note",
        "vault_mount",
    ),
}
_LEGACY_DIGEST_IDENTITY_KINDS = frozenset(
    {"note", "overlay_note", "overlay_space", "vault_file", "vault_mount"}
)
_DOCUMENT_FIELDS = (
    "id, space_id, source_native_id, authority_kind, relative_locator, "
    "document_kind, title, normalized_body, properties, tags, content_hash, "
    "source_revision_id, provenance, availability, parse_state, journal_date, "
    "capabilities, created_at, observed_at, updated_at"
)


class _Connection(Protocol):
    async def query(
        self, statement: str, variables: dict[str, Any] | None = None
    ) -> Any: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[_Connection]]


class KnowledgeRepositoryError(RuntimeError):
    """A stable, scrubbed knowledge-engine persistence failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class KnowledgePageIdentity(BaseModel):
    """Current unified IDs that may safely enrich an existing legacy page."""

    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: KnowledgeDocumentId | None = None
    block_ids: dict[str, KnowledgeBlockId] = Field(default_factory=dict)


class KnowledgeBlockIdentity(BaseModel):
    """Bounded current block identity, deliberately excluding source content."""

    model_config = ConfigDict(extra="forbid", strict=True)

    block_id: KnowledgeBlockId
    document_id: KnowledgeDocumentId
    source_revision_id: KnowledgeRevisionId


@dataclass(frozen=True, slots=True)
class EngineProjectionStatus:
    projected: int
    unchanged: int
    failed: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_id(value: str, *, kind: str):
    pattern = _ID_PATTERNS.get(kind)
    if (
        pattern is None
        or not isinstance(value, str)
        or pattern.fullmatch(value) is None
    ):
        raise ValueError(f"invalid_knowledge_engine_{kind}_id")
    return ensure_record_id(value)


def _operation(value: str) -> str:
    if not isinstance(value, str) or _OPERATION_ID.fullmatch(value) is None:
        raise ValueError("invalid_knowledge_engine_operation_id")
    return value


def _source_ref(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or "/" in value
        or "\\" in value
        or value in {".", ".."}
        or value.startswith(".")
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise ValueError("invalid_knowledge_engine_source_ref")
    return value


def _receipt_id(operation_id: str) -> str:
    return (
        "knowledge_engine_projection_receipt:"
        f"{sha256(operation_id.encode()).hexdigest()}"
    )


def _source_revision_record_id(value: str):
    _record_id(value, kind="revision")
    return ensure_record_id(
        value.replace(
            "knowledge_engine_revision:", "knowledge_engine_source_revision:", 1
        )
    )


def _checkpoint_id(space_id: str) -> str:
    suffix = space_id.split(":", 1)[1]
    return f"knowledge_engine_backfill_checkpoint:{suffix}"


def _content(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        **{key: item for key, item in value.items() if key != "id"},
    }


def _receipt_from(value: Any) -> ProjectionReceipt:
    try:
        if isinstance(value, dict):
            value = {key: item for key, item in value.items() if key != "id"}
        return ProjectionReceipt.model_validate(value)
    except ValidationError:
        raise KnowledgeRepositoryError("knowledge_engine_receipt_invalid") from None


def _checkpoint_from(value: Any) -> BackfillCheckpoint:
    try:
        if isinstance(value, dict):
            value = {
                key: item
                for key, item in value.items()
                if key not in {"id", "schema_version"}
            }
        return BackfillCheckpoint.model_validate(value)
    except ValidationError:
        raise KnowledgeRepositoryError("knowledge_engine_checkpoint_invalid") from None


class KnowledgeRepository:
    """Commit complete engine projections in one SurrealQL transaction."""

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
    ) -> list[dict[str, Any]]:
        try:
            result = await connection.query(statement, variables)
        except KnowledgeRepositoryError:
            raise
        except Exception:
            raise KnowledgeRepositoryError(
                "knowledge_engine_repository_unavailable"
            ) from None
        if isinstance(result, str):
            raise KnowledgeRepositoryError("knowledge_engine_repository_unavailable")
        parsed = parse_record_ids(result)
        return parsed if isinstance(parsed, list) else [parsed]

    async def commit_snapshot(
        self, snapshot: KnowledgeSnapshot, *, operation_id: str
    ) -> ProjectionReceipt:
        operation_id = _operation(operation_id)
        variables = self._snapshot_variables(snapshot, operation_id)
        try:
            async with self._connection_factory() as connection:
                rows = await self._query(
                    connection, self._snapshot_transaction(), variables
                )
        except KnowledgeRepositoryError as error:
            if error.code != "knowledge_engine_repository_unavailable":
                raise
            return await self._reconcile_transaction_conflict(
                operation_id=operation_id,
                input_hash=variables["input_hash"],
            )
        result = next(
            (
                row
                for row in reversed(rows)
                if isinstance(row, dict) and "receipt" in row
            ),
            None,
        )
        if result is None:
            raise KnowledgeRepositoryError("knowledge_engine_commit_outcome_missing")
        receipt = _receipt_from(result.get("receipt"))
        prior_input_hash = result.get("prior_input_hash")
        if prior_input_hash is not None and prior_input_hash != variables["input_hash"]:
            raise KnowledgeRepositoryError("operation_conflict")
        existing_status = result.get("existing_status")
        if existing_status == "failed":
            return receipt
        if prior_input_hash == variables["input_hash"]:
            return receipt.model_copy(update={"status": "unchanged"})
        return receipt

    async def _reconcile_transaction_conflict(
        self, *, operation_id: str, input_hash: str
    ) -> ProjectionReceipt:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT * FROM knowledge_engine_projection_receipt
                WHERE operation_id = $operation_id LIMIT 1;
                """,
                {"operation_id": operation_id},
            )
        if not rows:
            raise KnowledgeRepositoryError("knowledge_engine_repository_unavailable")
        receipt = _receipt_from(rows[0])
        if receipt.input_hash != input_hash:
            raise KnowledgeRepositoryError("operation_conflict")
        if receipt.status != "projected":
            raise KnowledgeRepositoryError("knowledge_engine_repository_unavailable")
        return receipt.model_copy(update={"status": "unchanged"})

    async def get_document(self, document_id: str) -> KnowledgeDocument:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                f"SELECT {_DOCUMENT_FIELDS} FROM $document_id LIMIT 1;",
                {"document_id": _record_id(document_id, kind="document")},
            )
        if not rows:
            raise LookupError("knowledge_engine_document_not_found")
        try:
            return KnowledgeDocument.model_validate(rows[0])
        except ValidationError:
            raise KnowledgeRepositoryError(
                "knowledge_engine_document_invalid"
            ) from None

    async def get_current_block(
        self,
        *,
        document_id: str,
        block_id: str,
        source_revision_id: str,
    ) -> KnowledgeBlockIdentity | None:
        """Return a block only when it belongs to the current document revision."""
        _record_id(document_id, kind="document")
        _record_id(block_id, kind="block")
        _record_id(source_revision_id, kind="revision")
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT id AS block_id, document_id, source_revision_id FROM $block_id
                WHERE document_id = $document_id
                    AND source_revision_id = $source_revision_id
                LIMIT 1;
                """,
                {
                    "block_id": _record_id(block_id, kind="block"),
                    "document_id": document_id,
                    "source_revision_id": source_revision_id,
                },
            )
        if not rows:
            return None
        try:
            return KnowledgeBlockIdentity.model_validate(rows[0])
        except ValidationError:
            raise KnowledgeRepositoryError(
                "knowledge_engine_block_invalid"
            ) from None

    async def resolve_legacy_page(
        self, *, legacy_note_id: str, block_keys: tuple[str, ...]
    ) -> KnowledgePageIdentity:
        """Resolve one legacy page against only its document's current revision."""
        if (
            not isinstance(legacy_note_id, str)
            or not 1 <= len(legacy_note_id) <= 128
            or not isinstance(block_keys, tuple)
            or len(block_keys) > 10_000
            or len(set(block_keys)) != len(block_keys)
            or any(
                not isinstance(key, str) or not 1 <= len(key) <= 256
                for key in block_keys
            )
        ):
            raise ValueError("invalid_knowledge_engine_legacy_page_identity")
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                RETURN {
                    document_claims: (
                        SELECT engine_id, source_revision_id, created_at
                        FROM knowledge_engine_identity_map
                        WHERE (legacy_kind = 'note' OR legacy_kind = 'overlay_note')
                        AND legacy_id = $legacy_note_id
                        AND engine_kind = 'document'
                        ORDER BY created_at DESC, engine_id
                    ),
                    documents: (
                        SELECT id, source_revision_id, updated_at
                        FROM knowledge_engine_document
                        WHERE source_revision_id IN (
                            SELECT VALUE source_revision_id
                            FROM knowledge_engine_identity_map
                            WHERE (legacy_kind = 'note' OR legacy_kind = 'overlay_note')
                            AND legacy_id = $legacy_note_id
                            AND engine_kind = 'document'
                        )
                        ORDER BY updated_at DESC, id
                    ),
                    block_claims: (
                        SELECT legacy_id, engine_id, source_revision_id, created_at
                        FROM knowledge_engine_identity_map
                        WHERE legacy_kind = 'source_native_block'
                        AND legacy_id IN $block_keys
                        AND engine_kind = 'block'
                        ORDER BY legacy_id, created_at DESC, engine_id
                    ),
                    blocks: (
                        SELECT id, document_id, source_revision_id
                        FROM knowledge_engine_block
                        WHERE source_revision_id IN (
                            SELECT VALUE source_revision_id
                            FROM knowledge_engine_identity_map
                            WHERE legacy_kind = 'source_native_block'
                            AND legacy_id IN $block_keys
                            AND engine_kind = 'block'
                        )
                    )
                };
                """,
                {
                    "legacy_note_id": legacy_note_id,
                    "block_keys": list(block_keys),
                },
            )
        row = rows[0] if rows and isinstance(rows[0], dict) else {}
        document_claims = {
            (str(item["engine_id"]), str(item["source_revision_id"]))
            for item in row.get("document_claims", [])
            if isinstance(item, dict)
            and isinstance(item.get("engine_id"), str)
            and isinstance(item.get("source_revision_id"), str)
        }
        current_document = next(
            (
                item
                for item in row.get("documents", [])
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and isinstance(item.get("source_revision_id"), str)
                and (str(item["id"]), str(item["source_revision_id"]))
                in document_claims
            ),
            None,
        )
        if current_document is None:
            return KnowledgePageIdentity()
        current_document_id = str(current_document["id"])
        current_revision_id = str(current_document["source_revision_id"])
        current_block_ids = {
            str(item["id"])
            for item in row.get("blocks", [])
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("document_id") == current_document_id
            and item.get("source_revision_id") == current_revision_id
        }
        block_ids = {
            str(item["legacy_id"]): str(item["engine_id"])
            for item in row.get("block_claims", [])
            if isinstance(item, dict)
            and isinstance(item.get("legacy_id"), str)
            and isinstance(item.get("engine_id"), str)
            and item.get("source_revision_id") == current_revision_id
            and str(item["engine_id"]) in current_block_ids
        }
        try:
            return KnowledgePageIdentity(
                document_id=current_document_id, block_ids=block_ids
            )
        except ValidationError:
            raise KnowledgeRepositoryError(
                "knowledge_engine_identity_invalid"
            ) from None

    async def open_descriptor(self, document_id: str) -> KnowledgeOpenDescriptor | None:
        """Read safe logical open metadata without exposing source content or roots."""
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT
                    id AS document_id,
                    space_id,
                    authority_kind,
                    (SELECT VALUE source_kind FROM knowledge_engine_space
                        WHERE type::string(id) = $parent.space_id LIMIT 1)[0]
                        AS source_kind,
                    title,
                    relative_locator,
                    (SELECT legacy_kind, legacy_id
                        FROM knowledge_engine_identity_map
                        WHERE (legacy_kind = 'note' OR legacy_kind = 'overlay_note')
                        AND engine_kind = 'document'
                        AND engine_id = type::string($parent.id)
                        AND source_revision_id = $parent.source_revision_id
                        ORDER BY legacy_kind, legacy_id) AS document_claims,
                    (SELECT legacy_kind, legacy_id
                        FROM knowledge_engine_identity_map
                        WHERE (legacy_kind = 'vault_mount' OR legacy_kind = 'overlay_space')
                        AND engine_kind = 'space'
                        AND engine_id = $parent.space_id
                        AND source_revision_id = $parent.source_revision_id
                        ORDER BY legacy_kind, legacy_id) AS container_claims
                FROM $document_id LIMIT 1;
                """,
                {"document_id": _record_id(document_id, kind="document")},
            )
        if not rows or rows[0] is None:
            return None
        row = rows[0]
        if not isinstance(row, dict):
            raise KnowledgeRepositoryError("knowledge_engine_descriptor_invalid")
        source_kind = row.get("source_kind")
        identity_rules = _DESCRIPTOR_LEGACY_IDS[
            "overlay" if source_kind == "overlay" else "external"
        ]
        note_pattern, container_pattern, note_kind, container_kind = identity_rules
        document_claim = next(
            (
                claim
                for claim in row.get("document_claims", [])
                if isinstance(claim, dict)
                and claim.get("legacy_kind") == note_kind
                and isinstance(claim.get("legacy_id"), str)
            ),
            None,
        )
        container_claim = next(
            (
                claim
                for claim in row.get("container_claims", [])
                if isinstance(claim, dict)
                and claim.get("legacy_kind") == container_kind
                and isinstance(claim.get("legacy_id"), str)
            ),
            None,
        )
        if document_claim is None or container_claim is None:
            return None
        row = {
            key: value
            for key, value in row.items()
            if key not in {"document_claims", "container_claims"}
        }
        row["legacy_note_id"] = document_claim["legacy_id"]
        row["legacy_container_id"] = container_claim["legacy_id"]
        try:
            descriptor = KnowledgeOpenDescriptor.model_validate(row)
        except ValidationError:
            raise KnowledgeRepositoryError(
                "knowledge_engine_descriptor_invalid"
            ) from None
        if (
            note_pattern.fullmatch(descriptor.legacy_note_id) is None
            or container_pattern.fullmatch(descriptor.legacy_container_id) is None
        ):
            return None
        return descriptor

    async def list_documents(
        self, *, space_id: str | None, limit: int, offset: int
    ) -> list[KnowledgeDocument]:
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or not 0 <= offset <= 1_000_000
        ):
            raise ValueError("invalid_pagination")
        variables: dict[str, Any] = {"limit": limit, "offset": offset}
        where = ""
        if space_id is not None:
            _record_id(space_id, kind="space")
            variables["space_id"] = space_id
            where = "WHERE space_id = $space_id"
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                f"""
                SELECT {_DOCUMENT_FIELDS} FROM knowledge_engine_document
                {where}
                ORDER BY updated_at DESC, id
                LIMIT $limit START $offset;
                """,
                variables,
            )
        try:
            return [KnowledgeDocument.model_validate(row) for row in rows]
        except ValidationError:
            raise KnowledgeRepositoryError(
                "knowledge_engine_document_invalid"
            ) from None

    async def projection_status(self) -> EngineProjectionStatus:
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                SELECT
                    count() AS projected
                FROM knowledge_engine_projection_receipt
                WHERE status = 'projected'
                GROUP ALL;
                """,
            )
            failed_rows = await self._query(
                connection,
                """
                SELECT count() AS failed FROM knowledge_engine_projection_receipt
                WHERE status = 'failed' GROUP ALL;
                """,
            )
        return EngineProjectionStatus(
            projected=int(rows[0]["projected"]) if rows else 0,
            unchanged=0,
            failed=int(failed_rows[0]["failed"]) if failed_rows else 0,
        )

    async def projection_digest(
        self, space_id: str, exact_queries: tuple[str, ...]
    ) -> ProjectionDigest:
        """Read one bounded, redacted digest without returning canonical bodies."""
        _record_id(space_id, kind="space")
        if (
            not isinstance(exact_queries, tuple)
            or not 1 <= len(exact_queries) <= 32
            or any(
                not isinstance(query, str) or not query.strip() or len(query) > 256
                for query in exact_queries
            )
        ):
            raise ValueError("invalid_equivalence_queries")
        async with self._connection_factory() as connection:
            spaces = await self._query(
                connection,
                "SELECT authority_kind, source_kind, format_mode, capabilities "
                "FROM $space_id LIMIT 1;",
                {"space_id": _record_id(space_id, kind="space")},
            )
            documents = await self._query(
                connection,
                "SELECT id, relative_locator, content_hash, source_revision_id, properties, tags, provenance "
                "FROM knowledge_engine_document WHERE space_id = $space_id "
                "ORDER BY relative_locator;",
                {"space_id": space_id},
            )
            blocks = await self._query(
                connection,
                "SELECT properties FROM knowledge_engine_block WHERE space_id = $space_id;",
                {"space_id": space_id},
            )
            relations = await self._query(
                connection,
                "SELECT source_document_id, target_document_id, relation_kind "
                "FROM knowledge_engine_relation WHERE space_id = $space_id;",
                {"space_id": space_id},
            )
            tasks = await self._query(
                connection,
                "SELECT properties, tags FROM knowledge_engine_task WHERE space_id = $space_id;",
                {"space_id": space_id},
            )
            assets = await self._query(
                connection,
                "SELECT id FROM knowledge_engine_asset WHERE space_id = $space_id;",
                {"space_id": space_id},
            )
            identities = await self._query(
                connection,
                "SELECT legacy_kind, legacy_id, engine_id, source_revision_id "
                "FROM knowledge_engine_identity_map WHERE source_revision_id IN "
                "(SELECT VALUE source_revision_id FROM knowledge_engine_document "
                "WHERE space_id = $space_id) "
                "ORDER BY legacy_kind, legacy_id, source_revision_id, engine_id;",
                {"space_id": space_id},
            )
            searches = {
                query: await self._query(
                    connection,
                    "SELECT relative_locator FROM knowledge_engine_document "
                    "WHERE space_id = $space_id "
                    "AND string::contains(normalized_body, $query) "
                    "ORDER BY relative_locator;",
                    {"space_id": space_id, "query": query},
                )
                for query in exact_queries
            }
        locator_by_id = {
            str(row.get("id")): str(row["relative_locator"])
            for row in documents
            if isinstance(row.get("relative_locator"), str)
            and isinstance(row.get("content_hash"), str)
        }
        current_revisions = {
            str(row["id"]): str(row["source_revision_id"])
            for row in documents
            if isinstance(row.get("id"), str)
            and isinstance(row.get("source_revision_id"), str)
        }
        active_revisions = set(current_revisions.values())
        current_identities = [
            row
            for row in identities
            if row.get("legacy_kind") in _LEGACY_DIGEST_IDENTITY_KINDS
            and isinstance(row.get("engine_id"), str)
            and isinstance(row.get("source_revision_id"), str)
            and (
                current_revisions.get(str(row["engine_id"]))
                == row["source_revision_id"]
                or (
                    row["engine_id"] == space_id
                    and row["source_revision_id"] in active_revisions
                )
            )
        ]
        outgoing: dict[str, list[str]] = {}
        backlinks: dict[str, list[str]] = {}
        graph_edges: list[str] = []
        for relation in relations:
            source_id = str(relation.get("source_document_id") or "")
            target_id = str(relation.get("target_document_id") or "")
            source = locator_by_id.get(source_id)
            target = locator_by_id.get(target_id)
            if source is None or target is None:
                continue
            outgoing.setdefault(source, []).append(target)
            backlinks.setdefault(target, []).append(source)
            graph_edges.append(
                f"{source_id}->{target_id}:{str(relation.get('relation_kind') or '')}"
            )
        space = spaces[0] if spaces else {}
        return ProjectionDigest(
            space_id=space_id,
            document_count=len(documents),
            block_count=len(blocks),
            relation_count=len(relations),
            task_count=len(tasks),
            property_count=sum(
                len(row.get("properties") or {})
                for row in [*documents, *blocks, *tasks]
                if isinstance(row.get("properties") or {}, dict)
            ),
            tag_count=sum(
                len(row.get("tags") or [])
                for row in [*documents, *tasks]
                if isinstance(row.get("tags") or [], list)
            ),
            asset_count=len(assets),
            document_hashes={
                locator: str(row["content_hash"])
                for row in documents
                if (locator := locator_by_id.get(str(row.get("id")))) is not None
            },
            identity_pairs={
                f"{row['legacy_kind']}:{row['legacy_id']}": str(row["engine_id"])
                for row in current_identities
                if all(
                    isinstance(row.get(key), str)
                    for key in ("legacy_kind", "legacy_id", "engine_id")
                )
            },
            outgoing_membership=outgoing,
            backlink_membership=backlinks,
            graph_edges=graph_edges,
            exact_search_membership={
                sha256(query.encode("utf-8")).hexdigest(): [
                    str(row["relative_locator"])
                    for row in rows
                    if isinstance(row.get("relative_locator"), str)
                ]
                for query, rows in searches.items()
            },
            authority_kind=space.get("authority_kind"),
            source_kind=space.get("source_kind"),
            format_mode=space.get("format_mode"),
            provenance=(
                str(documents[0]["provenance"])
                if documents and isinstance(documents[0].get("provenance"), str)
                else None
            ),
            capabilities=space.get("capabilities") or [],
            overlay_revision_mappings={
                str(row["legacy_id"]): str(row["source_revision_id"])
                for row in current_identities
                if row.get("legacy_kind") == "overlay_note"
                and isinstance(row.get("legacy_id"), str)
                and isinstance(row.get("source_revision_id"), str)
            },
        )

    async def record_projection_failure(
        self,
        *,
        operation_id: str,
        space_id: str,
        relative_locator: str,
        input_hash: str,
        error_code: str,
    ) -> ProjectionReceipt:
        operation_id = _operation(operation_id)
        _record_id(space_id, kind="space")
        if not _ERROR_CODE.fullmatch(error_code):
            raise ValueError("invalid_knowledge_engine_error_code")
        try:
            relative_locator = canonical_locator(relative_locator)
        except ValueError:
            raise ValueError("invalid_knowledge_engine_relative_locator") from None
        if not re.fullmatch(r"[0-9a-f]{64}", input_hash):
            raise ValueError("invalid_knowledge_engine_input_hash")
        now = self._clock()
        receipt = {
            "schema_version": 1,
            "operation_id": operation_id,
            "space_id": space_id,
            "document_id": "knowledge_engine_document:unknown",
            "source_revision_id": "knowledge_engine_revision:unknown",
            "relative_locator": relative_locator,
            "input_hash": input_hash,
            "output_hash": None,
            "adapter_version": "knowledge-repository-v1",
            "status": "failed",
            "error_code": error_code,
            "started_at": now,
            "completed_at": now,
        }
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                """
                BEGIN TRANSACTION;
                LET $existing = (
                    SELECT * FROM knowledge_engine_projection_receipt
                    WHERE operation_id = $operation_id LIMIT 1
                )[0];
                IF $existing = NONE {
                    CREATE $receipt_id CONTENT $receipt;
                };
                RETURN { receipt: IF $existing = NONE { $receipt } ELSE { $existing } };
                COMMIT TRANSACTION;
                """,
                {
                    "receipt_id": _record_id(_receipt_id(operation_id), kind="receipt"),
                    "operation_id": operation_id,
                    "receipt": receipt,
                },
            )
        row = next((item for item in reversed(rows) if "receipt" in item), None)
        if row is None:
            raise KnowledgeRepositoryError("knowledge_engine_commit_outcome_missing")
        receipt = _receipt_from(row["receipt"])
        if receipt.input_hash != input_hash:
            raise KnowledgeRepositoryError("operation_conflict")
        return receipt

    async def get_checkpoint(self, space_id: str) -> BackfillCheckpoint | None:
        _record_id(space_id, kind="space")
        checkpoint_id = _checkpoint_id(space_id)
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "SELECT * FROM $checkpoint_id LIMIT 1;",
                {"checkpoint_id": _record_id(checkpoint_id, kind="checkpoint")},
            )
        if not rows:
            return None
        return _checkpoint_from(rows[0])

    async def save_checkpoint(
        self, checkpoint: BackfillCheckpoint
    ) -> BackfillCheckpoint:
        _record_id(checkpoint.space_id, kind="space")
        checkpoint_id = _checkpoint_id(checkpoint.space_id)
        data = checkpoint.model_dump(mode="python")
        data["schema_version"] = 1
        async with self._connection_factory() as connection:
            rows = await self._query(
                connection,
                "UPSERT $checkpoint_id CONTENT $checkpoint RETURN AFTER;",
                {
                    "checkpoint_id": _record_id(checkpoint_id, kind="checkpoint"),
                    "checkpoint": data,
                },
            )
        if not rows:
            raise KnowledgeRepositoryError("knowledge_engine_checkpoint_missing")
        return _checkpoint_from(rows[0])

    def _snapshot_variables(
        self, snapshot: KnowledgeSnapshot, operation_id: str
    ) -> dict[str, Any]:
        data = snapshot.model_dump(mode="python")
        _source_ref(snapshot.space.source_ref)
        space = _content(data["space"])
        document = _content(data["document"])
        revision = _content(data["revision"])
        for value, kind in (
            (snapshot.space.id, "space"),
            (snapshot.document.id, "document"),
            (snapshot.revision.id, "revision"),
        ):
            _record_id(value, kind=kind)
        children: dict[str, list[dict[str, Any]]] = {}
        for name, kind in (
            ("blocks", "block"),
            ("relations", "relation"),
            ("tasks", "task"),
            ("assets", "asset"),
        ):
            children[name] = [
                {"record_id": _record_id(item["id"], kind=kind), "data": _content(item)}
                for item in data[name]
            ]
        for block in data["blocks"]:
            if block["parent_block_id"] is not None:
                _record_id(block["parent_block_id"], kind="block")
        for relation in data["relations"]:
            _record_id(relation["source_document_id"], kind="document")
            if relation["source_block_id"] is not None:
                _record_id(relation["source_block_id"], kind="block")
            if relation["target_document_id"] is not None:
                _record_id(relation["target_document_id"], kind="document")
            if relation["target_block_id"] is not None:
                _record_id(relation["target_block_id"], kind="block")
        for task in data["tasks"]:
            _record_id(task["document_id"], kind="document")
            if task["block_id"] is not None:
                _record_id(task["block_id"], kind="block")
        for asset in data["assets"]:
            _record_id(asset["source_document_id"], kind="document")
        for claim in data["identity_claims"]:
            if claim["engine_kind"] not in _ID_PATTERNS:
                raise ValueError("invalid_knowledge_engine_engine_id")
            _record_id(claim["engine_id"], kind=claim["engine_kind"])
            _record_id(claim["source_revision_id"], kind="revision")
        receipt_id = _receipt_id(operation_id)
        _record_id(receipt_id, kind="receipt")
        now = self._clock()
        success_receipt = {
            "schema_version": 1,
            "operation_id": operation_id,
            "space_id": snapshot.space.id,
            "document_id": snapshot.document.id,
            "source_revision_id": snapshot.revision.id,
            "relative_locator": snapshot.document.relative_locator,
            "input_hash": snapshot.revision.content_hash,
            "output_hash": snapshot.document.content_hash,
            "adapter_version": snapshot.revision.adapter_version,
            "status": "projected",
            "error_code": None,
            "started_at": now,
            "completed_at": now,
        }
        return {
            "operation_id": operation_id,
            "input_hash": snapshot.revision.content_hash,
            "space_id": snapshot.space.id,
            "document_id": snapshot.document.id,
            "revision_id": snapshot.revision.id,
            "space_record_id": _record_id(snapshot.space.id, kind="space"),
            "document_record_id": _record_id(snapshot.document.id, kind="document"),
            "revision_record_id": _source_revision_record_id(snapshot.revision.id),
            "receipt_id": _record_id(receipt_id, kind="receipt"),
            "space": space,
            "document": document,
            "revision": revision,
            **children,
            "identity_claims": data["identity_claims"],
            "success_receipt": success_receipt,
        }

    @staticmethod
    def _snapshot_transaction() -> str:
        return """
        BEGIN TRANSACTION;
        LET $existing_receipt = (
            SELECT * FROM knowledge_engine_projection_receipt
            WHERE operation_id = $operation_id LIMIT 1
        )[0];
        LET $existing_document = (
            SELECT * FROM knowledge_engine_document
            WHERE id = $document_record_id LIMIT 1
        )[0];
        LET $existing_status = IF $existing_receipt = NONE {
            'missing'
        } ELSE {
            $existing_receipt.status
        };
        LET $retry_failed = IF $existing_receipt = NONE {
            false
        } ELSE {
            $existing_receipt.status = 'failed'
            AND $existing_receipt.input_hash = $input_hash
        };
        LET $write_snapshot = IF $existing_receipt = NONE {
            true
        } ELSE {
            $retry_failed
        };
        IF $write_snapshot {
            UPSERT $space_record_id CONTENT $space;
            UPSERT $revision_record_id CONTENT $revision;
            UPSERT $document_record_id CONTENT $document;
            DELETE knowledge_engine_block WHERE document_id = $document_id;
            DELETE knowledge_engine_relation WHERE source_document_id = $document_id;
            DELETE knowledge_engine_task WHERE document_id = $document_id;
            DELETE knowledge_engine_asset WHERE source_document_id = $document_id;
            FOR $block IN $blocks { UPSERT $block.record_id CONTENT $block.data; };
            FOR $relation IN $relations { UPSERT $relation.record_id CONTENT $relation.data; };
            FOR $task IN $tasks { UPSERT $task.record_id CONTENT $task.data; };
            FOR $asset IN $assets { UPSERT $asset.record_id CONTENT $asset.data; };
            FOR $claim IN $identity_claims {
                LET $mapped = (
                    SELECT * FROM knowledge_engine_identity_map
                    WHERE legacy_kind = $claim.legacy_kind
                    AND legacy_id = $claim.legacy_id
                    AND source_revision_id = $claim.source_revision_id
                    LIMIT 1
                )[0];
                IF $mapped = NONE {
                    CREATE knowledge_engine_identity_map CONTENT $claim;
                } ELSE {
                    IF $mapped.claim_hash != $claim.claim_hash
                    OR $mapped.engine_kind != $claim.engine_kind
                    OR $mapped.engine_id != $claim.engine_id {
                        THROW 'identity_mapping_conflict';
                    };
                };
            };
            IF $existing_receipt = NONE {
                CREATE $receipt_id CONTENT $success_receipt;
            } ELSE {
                UPDATE $receipt_id CONTENT $success_receipt;
            };
        };
        RETURN {
            existing_status: $existing_status,
            prior_input_hash: $existing_receipt.input_hash,
            receipt: IF $write_snapshot { $success_receipt } ELSE { $existing_receipt }
        };
        COMMIT TRANSACTION;
        """


__all__ = [
    "EngineProjectionStatus",
    "KnowledgePageIdentity",
    "KnowledgeRepository",
    "KnowledgeRepositoryError",
]
