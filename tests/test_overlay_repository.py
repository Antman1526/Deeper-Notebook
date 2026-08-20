from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import pytest

from deeper_notebook.overlay.repository import (
    OverlayConflictError,
    OverlayRepository,
    OverlayReservation,
)
from deeper_notebook.vault.contracts import (
    ParsedBlock,
    ParsedDocument,
    ParsedLink,
    ParsedTask,
)
from deeper_notebook.vault.repository import OwnedProjectionUnitOfWork, VaultRepository

NOW = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)


def _note_row(
    *,
    note_id: str = "overlay_note:one",
    projected_note_id: str = "note:one",
    kind: str = "daily",
    date_key: str | None = "2026-07-29",
    relative_path: str = "Daily/2026-07-29.md",
    title: str = "2026-07-29",
    revision: int = 1,
    content_hash: str = "0" * 64,
    projection_state: str = "pending",
) -> dict[str, Any]:
    return {
        "id": note_id,
        "space_id": "overlay_space:default",
        "projected_note_id": projected_note_id,
        "stable_id": "01JTESTOVERLAY000000000001",
        "kind": kind,
        "date_key": date_key,
        "relative_path": relative_path,
        "title": title,
        "content_hash": content_hash,
        "revision": revision,
        "projection_state": projection_state,
        "encoding": "utf-8",
        "newline": "lf",
        "created_at": NOW,
        "updated_at": NOW,
    }


def _receipt_row(
    *,
    operation: str = "create-daily",
    status: str = "started",
    overlay_note_id: str = "overlay_note:one",
    expected_revision: int | None = None,
    resulting_revision: int | None = None,
) -> dict[str, Any]:
    return {
        "id": "overlay_mutation_receipt:one",
        "operation_id": "op-one",
        "idempotency_key": "daily:2026-07-29",
        "overlay_note_id": overlay_note_id,
        "operation": operation,
        "expected_revision": expected_revision,
        "resulting_revision": resulting_revision,
        "before_hash": None,
        "after_hash": None,
        "status": status,
        "error_code": None,
        "started_at": NOW,
        "completed_at": None,
    }


def _link_row(
    *,
    link_id: str = "note_link:one",
    source_note_id: str = "note:one",
    source_overlay_note_id: str | None = "overlay_note:one",
    source_relative_path: str | None = "Daily/2026-07-29.md",
    source_title: str = "2026-07-29",
    target_note_id: str = "note:two",
    target_overlay_note_id: str | None = "overlay_note:two",
    target_title: str = "Target",
) -> dict[str, Any]:
    return {
        "id": link_id,
        "source_note_id": source_note_id,
        "source_note_title": source_title,
        "target_note_id": target_note_id,
        "target_note_title": target_title,
        "target_relative_path": "Notes/20260729-1542 Target.md",
        "target_text": target_title,
        "link_kind": "wikilink",
        "resolved": True,
        "source_start": 0,
        "source_end": 10,
        "source_overlay_note_id": source_overlay_note_id,
        "source_relative_path": source_relative_path,
        "target_overlay_note_id": target_overlay_note_id,
    }


def _parsed_document() -> ParsedDocument:
    markdown = "# 2026-07-29\n- [ ] Review [[Research]]"
    return ParsedDocument(
        relative_path="Daily/2026-07-29.md",
        source_format="markdown",
        title="2026-07-29",
        markdown=markdown,
        content_hash="a" * 64,
        newline="lf",
        blocks=[
            ParsedBlock(
                parser_id="heading",
                position=0,
                block_kind="heading",
                markdown="# 2026-07-29",
                plain_text="2026-07-29",
                source_start=0,
                source_end=12,
            ),
            ParsedBlock(
                parser_id="task",
                position=1,
                block_kind="task",
                markdown="- [ ] Review [[Research]]",
                plain_text="Review Research",
                task_state="todo",
                source_start=13,
                source_end=len(markdown.encode()),
            ),
        ],
        links=[
            ParsedLink(
                source_block_parser_id="task",
                target_text="Research",
                link_kind="wikilink",
                source_start=26,
                source_end=38,
            )
        ],
        tasks=[ParsedTask(block_parser_id="task", status="todo")],
    )


def test_overlay_package_exports_repository_and_service_boundaries():
    from deeper_notebook.overlay import (
        OverlayConflictError as PackageStorageConflictError,
    )
    from deeper_notebook.overlay import (
        OverlayRepository as PackageRepository,
    )
    from deeper_notebook.overlay import (
        OverlayRepositoryConflictError as PackageConflictError,
    )
    from deeper_notebook.overlay import OverlayService as PackageService
    from deeper_notebook.overlay import OverlayStorageError

    assert PackageConflictError is OverlayConflictError
    assert PackageRepository is OverlayRepository
    assert PackageService.__name__ == "OverlayService"
    assert issubclass(PackageStorageConflictError, OverlayStorageError)
    assert issubclass(OverlayStorageError, OSError)


class ScriptedConnection:
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def query(
        self,
        statement: str,
        variables: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append((" ".join(statement.split()), variables or {}))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class ReusableFactory:
    def __init__(self, connection: ScriptedConnection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def __call__(self):
        yield self.connection


@pytest.mark.asyncio
async def test_strict_overlay_hydration_queries_project_only_public_fields():
    space_row = {
        "id": "overlay_space:default",
        "slug": "default",
        "display_name": "Deeper Notebook Overlay",
        "root_version": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    connection = ScriptedConnection(
        [space_row],
        [_note_row()],
        [_note_row()],
        [_note_row()],
        [_receipt_row()],
    )
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )

    await repository.ensure_default_space()
    await repository.get_daily("2026-07-29")
    await repository.get_note("overlay_note:one")
    await repository.list_notes(10, 0)
    await repository.get_receipt(
        OverlayReservation(
            operation_id="op-one",
            idempotency_key="daily:2026-07-29",
            overlay_note_id="overlay_note:one",
            projected_note_id="note:one",
            relative_path="Daily/2026-07-29.md",
            title="2026-07-29",
            kind="daily",
            date_key="2026-07-29",
            expected_revision=None,
        )
    )

    statements = [statement for statement, _variables in connection.calls]
    assert "RETURN AFTER" not in statements[0]
    assert "SELECT id, slug, display_name, root_version" in statements[0]
    for statement in statements[1:4]:
        assert "SELECT *" not in statement
        assert "schema_version" not in statement
        assert "projected_note_id" in statement
    assert "SELECT *" not in statements[4]
    assert "schema_version" not in statements[4]
    assert "operation_id" in statements[4]


def test_reservation_outputs_exclude_internal_schema_fields():
    create_statement = " ".join(OverlayRepository._reserve_create_transaction().split())
    update_statement = " ".join(OverlayRepository._reserve_update_transaction().split())

    assert "SELECT * FROM overlay_note" not in create_statement
    assert "SELECT * FROM overlay_mutation_receipt" not in create_statement
    assert "schema_version" not in create_statement
    assert "projected_note_id" in create_statement
    assert "operation_id" in create_statement
    assert "SELECT * FROM $note_id" not in update_statement
    assert "SELECT * FROM overlay_mutation_receipt" not in update_statement
    assert "schema_version" not in update_statement
    assert "projected_note_id" in update_statement
    assert "operation_id" in update_statement
    assert "ELSE { IF" not in create_statement
    assert "ELSE { IF" not in update_statement
    assert (
        "LET $winner_receipt = IF $existing_receipt != NONE { "
        "$existing_receipt } ELSE { RETURN IF $winner != NONE" in create_statement
    )


def test_native_overlay_page_query_wraps_let_return_in_transaction():
    statement = " ".join(OverlayRepository._page_query().split())

    assert statement.startswith("BEGIN TRANSACTION; LET $overlay")
    assert statement.endswith("COMMIT TRANSACTION;")


@pytest.mark.asyncio
async def test_overlay_page_query_preserves_both_identity_domains():
    link = _link_row()
    backlink = _link_row(
        link_id="note_link:backlink",
        source_note_id="note:source",
        source_overlay_note_id="overlay_note:source",
        source_relative_path="Notes/20260729-1541 Source.md",
        source_title="Source",
        target_note_id="note:one",
        target_overlay_note_id="overlay_note:one",
        target_title="2026-07-29",
    )
    connection = ScriptedConnection(
        [
            {
                "page": {
                    "overlay": _note_row(projection_state="current"),
                    "note": {"id": "note:one", "title": "2026-07-29"},
                    "blocks": [],
                    "tasks": [],
                    "outgoing_links": [link],
                    "backlinks": [backlink],
                    "graph": None,
                }
            }
        ]
    )
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )

    page = await repository.get_page("overlay_note:one")

    assert page.outgoing_links[0].source_note_id == "note:one"
    assert page.outgoing_links[0].target_note_id == "note:two"
    assert page.outgoing_links[0].source_overlay_note_id == "overlay_note:one"
    assert page.outgoing_links[0].source_relative_path == "Daily/2026-07-29.md"
    assert page.outgoing_links[0].target_overlay_note_id == "overlay_note:two"
    assert page.graph is not None
    assert {node["id"] for node in page.graph.nodes} == {
        "note:one",
        "note:source",
        "note:two",
    }
    assert {(edge["source"], edge["target"]) for edge in page.graph.edges} == {
        ("note:one", "note:two"),
        ("note:source", "note:one"),
    }
    query = connection.calls[0][0]
    assert "SELECT * FROM $overlay_note_id" not in query
    assert (
        "SELECT id, space_id, projected_note_id, stable_id, kind, date_key,"
        " relative_path, title, content_hash, revision, projection_state,"
        " encoding, newline, created_at, updated_at FROM $overlay_note_id"
    ) in query
    assert query.count("source_note_id.overlay_note_id AS source_overlay_note_id") == 2
    assert (
        query.count(
            "source_note_id.overlay_note_id.relative_path AS source_relative_path"
        )
        == 2
    )
    assert query.count("target_note_id.overlay_note_id AS target_overlay_note_id") == 2


def test_owned_projection_page_query_preserves_both_identity_domains():
    query = " ".join(
        VaultRepository._owned_projection_transaction("RETURN true;").split()
    )

    assert "SELECT * FROM $overlay_note_id" not in query
    assert (
        "SELECT id, space_id, projected_note_id, stable_id, kind, date_key,"
        " relative_path, title, content_hash, revision, projection_state,"
        " encoding, newline, created_at, updated_at FROM $overlay_note_id"
    ) in query
    assert "overlay: $overlay" in query
    assert query.count("source_note_id.overlay_note_id AS source_overlay_note_id") == 2
    assert (
        query.count(
            "source_note_id.overlay_note_id.relative_path AS source_relative_path"
        )
        == 2
    )
    assert query.count("target_note_id.overlay_note_id AS target_overlay_note_id") == 2


@pytest.mark.asyncio
async def test_owned_projection_return_hydrates_the_same_overlay_local_graph():
    link = _link_row()
    backlink = _link_row(
        link_id="note_link:backlink",
        source_note_id="note:source",
        source_overlay_note_id="overlay_note:source",
        source_relative_path="Notes/20260729-1541 Source.md",
        source_title="Source",
        target_note_id="note:one",
        target_overlay_note_id="overlay_note:one",
        target_title="2026-07-29",
    )
    connection = ScriptedConnection(
        [
            {
                "outcome": "projected",
                "page": {
                    "overlay": _note_row(
                        content_hash="a" * 64,
                        projection_state="current",
                    ),
                    "note": {"id": "note:one", "title": "2026-07-29"},
                    "blocks": [],
                    "tasks": [],
                    "outgoing_links": [link],
                    "backlinks": [backlink],
                    "graph": None,
                },
            }
        ]
    )
    repository = VaultRepository(
        connection_factory=ReusableFactory(connection),
    )

    page = await repository.project_owned_document(
        source_authority="overlay",
        overlay_space_id="overlay_space:default",
        overlay_note_id="overlay_note:one",
        projected_note_id="note:one",
        parsed=_parsed_document(),
        revision=1,
    )

    assert page.graph is not None
    assert {node["id"] for node in page.graph.nodes} == {
        "note:one",
        "note:source",
        "note:two",
    }
    assert {(edge["source"], edge["target"]) for edge in page.graph.edges} == {
        ("note:one", "note:two"),
        ("note:source", "note:one"),
    }


@pytest.mark.asyncio
async def test_daily_reservation_has_one_transactional_winner():
    response = [
        {
            "outcome": "reserved",
            "note": _note_row(),
            "receipt": _receipt_row(),
        }
    ]
    connection = ScriptedConnection(response, response)
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )

    first = await repository.reserve_create(
        operation="create-daily",
        idempotency_key="daily:2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
    )
    second = await repository.reserve_create(
        operation="create-daily",
        idempotency_key="daily:2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
    )

    assert (
        first
        == second
        == OverlayReservation(
            operation_id="op-one",
            idempotency_key="daily:2026-07-29",
            overlay_note_id="overlay_note:one",
            projected_note_id="note:one",
            relative_path="Daily/2026-07-29.md",
            title="2026-07-29",
            kind="daily",
            date_key="2026-07-29",
            expected_revision=None,
        )
    )
    for statement, _variables in connection.calls:
        assert statement.startswith("BEGIN TRANSACTION;")
        assert "CREATE $note_id CONTENT $note" in statement
        assert "CREATE $receipt_id CONTENT $receipt" in statement
        assert statement.endswith("COMMIT TRANSACTION;")
        assert "vault_mount" not in statement
        assert "vault_file" not in statement
        assert "vault_sync_receipt" not in statement


@pytest.mark.asyncio
async def test_commit_writes_revision_projection_and_success_receipt_atomically():
    committed = _note_row(
        content_hash="a" * 64,
        projection_state="current",
    )
    connection = ScriptedConnection(
        [{"outcome": "committed", "note": committed}],
    )
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )
    reservation = OverlayReservation(
        operation_id="op-one",
        idempotency_key="daily:2026-07-29",
        overlay_note_id="overlay_note:one",
        projected_note_id="note:one",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        expected_revision=None,
    )

    result = await repository.commit_revision(
        reservation=reservation,
        content_hash="a" * 64,
        byte_size=42,
        relative_snapshot="revisions/one-r1-aaaa.md",
        parsed=_parsed_document(),
    )

    assert result.revision == 1
    statement, variables = connection.calls[0]
    assert statement.startswith("BEGIN TRANSACTION;")
    assert "UPSERT $overlay_note_id MERGE $overlay_note" in statement
    assert "UPSERT $projected_note_id MERGE $projected_note" in statement
    assert "CREATE $revision_id CONTENT $revision" in statement
    assert "UPDATE $receipt_id MERGE $success_receipt" in statement
    assert "FOR $block IN $blocks" in statement
    assert "FOR $link IN $links" in statement
    assert "FOR $task IN $tasks" in statement
    assert statement.endswith("COMMIT TRANSACTION;")
    assert variables["projected_note"]["source_authority"] == "overlay"
    assert variables["projected_note"]["canonical_external"] is False
    assert variables["revision"]["relative_snapshot"] == "revisions/one-r1-aaaa.md"
    assert variables["revision"]["content_hash"] == "a" * 64
    assert variables["revision"]["byte_size"] == 42
    assert "$receipt.after_hash = $content_hash" in statement
    assert all(block["data"]["vault_file_id"] is None for block in variables["blocks"])
    assert all(
        str(block["data"]["overlay_note_id"]) == "overlay_note:one"
        for block in variables["blocks"]
    )
    serialized = repr(variables)
    assert "/Users/" not in serialized
    assert "vault_mount" not in serialized
    assert "vault_sync_receipt" not in statement


@pytest.mark.asyncio
async def test_prepare_revision_durably_binds_receipt_to_intended_hash():
    connection = ScriptedConnection([{"outcome": "prepared"}])
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )
    reservation = OverlayReservation(
        operation_id="op-one",
        idempotency_key="daily:2026-07-29",
        overlay_note_id="overlay_note:one",
        projected_note_id="note:one",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        expected_revision=None,
    )

    await repository.prepare_revision(
        reservation=reservation,
        content_hash="a" * 64,
    )

    statement, variables = connection.calls[0]
    assert statement.startswith("BEGIN TRANSACTION;")
    assert "after_hash = $content_hash" in statement
    assert "$receipt.after_hash = NONE" in statement
    assert statement.endswith("COMMIT TRANSACTION;")
    assert variables["content_hash"] == "a" * 64


@pytest.mark.asyncio
async def test_commit_rejects_projected_title_that_differs_from_canonical_metadata():
    connection = ScriptedConnection(
        [
            {
                "outcome": "committed",
                "note": _note_row(
                    content_hash="a" * 64,
                    projection_state="current",
                ),
            }
        ]
    )
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )
    reservation = OverlayReservation(
        operation_id="op-one",
        idempotency_key="daily:2026-07-29",
        overlay_note_id="overlay_note:one",
        projected_note_id="note:one",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        expected_revision=None,
    )

    with pytest.raises(ValueError, match="overlay_projection_title_mismatch"):
        await repository.commit_revision(
            reservation=reservation,
            content_hash="a" * 64,
            byte_size=42,
            relative_snapshot="revisions/one-r1-aaaa.md",
            parsed=_parsed_document().model_copy(update={"title": "Different"}),
        )

    assert connection.calls == []


@pytest.mark.asyncio
async def test_commit_uses_public_owned_projection_unit_of_work():
    committed = _note_row(
        content_hash="a" * 64,
        projection_state="current",
    )
    connection = ScriptedConnection(
        [{"outcome": "committed", "note": committed}],
    )

    class ProjectionSeam:
        def __init__(self) -> None:
            self.calls = []

        def owned_projection_unit_of_work(self, **kwargs):
            self.calls.append(kwargs)
            return OwnedProjectionUnitOfWork(
                variables={
                    "overlay_space_id": "overlay_space:default",
                    "overlay_note_id": "overlay_note:one",
                    "projected_note_id": "note:one",
                    "revision": 1,
                    "projected_note": {},
                    "blocks": [],
                    "links": [],
                    "tasks": [],
                },
                mutation_statement="RETURN true;",
            )

    projection = ProjectionSeam()
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
        projection_repository=projection,  # type: ignore[arg-type]
    )
    reservation = OverlayReservation(
        operation_id="op-one",
        idempotency_key="daily:2026-07-29",
        overlay_note_id="overlay_note:one",
        projected_note_id="note:one",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        expected_revision=None,
    )

    await repository.commit_revision(
        reservation=reservation,
        content_hash="a" * 64,
        byte_size=42,
        relative_snapshot="revisions/one-r1-aaaa.md",
        parsed=_parsed_document(),
    )

    assert len(projection.calls) == 1
    assert projection.calls[0]["source_authority"] == "overlay"
    assert "RETURN true;" in connection.calls[0][0]


@pytest.mark.asyncio
async def test_reserve_update_compares_revision_and_current_projection_hash():
    connection = ScriptedConnection([{"outcome": "revision-conflict"}])
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )

    with pytest.raises(OverlayConflictError, match="overlay_revision_conflict"):
        await repository.reserve_update(
            note_id="overlay_note:one",
            expected_revision=99,
            idempotency_key="save-1",
        )

    statement, variables = connection.calls[0]
    assert statement.startswith("BEGIN TRANSACTION;")
    assert "$note.revision = $expected_revision" in statement
    assert "$latest_revision.content_hash = $note.content_hash" in statement
    assert "CREATE $receipt_id CONTENT $receipt" in statement
    assert statement.endswith("COMMIT TRANSACTION;")
    assert variables["expected_revision"] == 99


@pytest.mark.asyncio
async def test_unique_path_conflict_is_typed_and_creates_no_started_receipt():
    connection = ScriptedConnection([{"outcome": "path-conflict"}])
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )

    with pytest.raises(OverlayConflictError, match="overlay_path_conflict"):
        await repository.reserve_create(
            operation="create-unique",
            idempotency_key="unique-two",
            kind="unique",
            date_key=None,
            relative_path="Notes/20260729-1542 Research.md",
            title="Research",
        )

    statement, _variables = connection.calls[0]
    assert "$path_conflict" in statement
    assert "IF $can_reserve" in statement


@pytest.mark.asyncio
async def test_unpublished_unique_reservation_reassigns_path_transactionally():
    note = _note_row(
        kind="unique",
        date_key=None,
        relative_path="Notes/20260729-1542 Research-2.md",
        title="Research",
    )
    receipt = _receipt_row(
        operation="create-unique",
    )
    receipt["idempotency_key"] = "unique-two"
    connection = ScriptedConnection(
        [{"outcome": "reassigned", "note": note, "receipt": receipt}]
    )
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )
    reservation = OverlayReservation(
        operation_id="op-one",
        idempotency_key="unique-two",
        overlay_note_id="overlay_note:one",
        projected_note_id="note:one",
        relative_path="Notes/20260729-1542 Research.md",
        title="Research",
        kind="unique",
        date_key=None,
        expected_revision=None,
    )

    reassigned = await repository.reassign_unique_path(
        reservation=reservation,
        relative_path="Notes/20260729-1542 Research-2.md",
    )

    assert reassigned.relative_path.endswith("Research-2.md")
    statement, variables = connection.calls[0]
    assert statement.startswith("BEGIN TRANSACTION;")
    assert "$note.content_hash = $zero_hash" in statement
    assert "$revision = NONE" in statement
    assert "projection_state = 'pending'" in statement
    assert "after_hash = NONE" in statement
    assert statement.endswith("COMMIT TRANSACTION;")
    assert variables["relative_path"] == "Notes/20260729-1542 Research-2.md"


@pytest.mark.asyncio
async def test_failure_receipt_is_typed_and_never_contains_source_content_or_root():
    connection = ScriptedConnection([[]])
    repository = OverlayRepository(
        connection_factory=ReusableFactory(connection),
        clock=lambda: NOW,
    )
    reservation = OverlayReservation(
        operation_id="op-one",
        idempotency_key="daily:2026-07-29",
        overlay_note_id="overlay_note:one",
        projected_note_id="note:one",
        relative_path="Daily/2026-07-29.md",
        title="2026-07-29",
        kind="daily",
        date_key="2026-07-29",
        expected_revision=None,
    )

    await repository.record_failure(
        reservation=reservation,
        error_code="overlay_storage_unavailable",
    )

    statement, variables = connection.calls[0]
    assert statement.startswith("BEGIN TRANSACTION;")
    assert set(variables).isdisjoint({"markdown", "absolute_path", "root_path"})
    assert variables["error_code"] == "overlay_storage_unavailable"
    assert "after_hash =" not in statement
    assert "/Users/" not in repr(variables)
    assert statement.endswith("COMMIT TRANSACTION;")
