from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, nullcontext
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from deeper_notebook.database import async_migrate
from deeper_notebook.database.async_migrate import (
    AsyncMigrationManager,
    get_latest_version,
)
from deeper_notebook.database.repository import (
    db_connection,
    ensure_record_id,
    repo_query,
)
from deeper_notebook.vault.contracts import (
    ParsedBlock,
    ParsedDocument,
    ParsedLink,
    ParsedTask,
)
from deeper_notebook.vault.parsers import parse_document
from deeper_notebook.vault.repository import (
    VaultMount,
    VaultMountCreate,
    VaultProjectionError,
    VaultRepository,
)
from deeper_notebook.vault.security import approve_vault_root
from deeper_notebook.vault.service import VaultService
from deeper_notebook.vault.watcher import VaultWorkItem

pytestmark = pytest.mark.integration_surreal

ROOT = Path(__file__).resolve().parents[2]
UP = ROOT / "deeper_notebook/database/migrations/32.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/32_down.surrealql"
UPGRADE = ROOT / "deeper_notebook/database/migrations/33.surrealql"
MIGRATION_34_DOWN = ROOT / "deeper_notebook/database/migrations/34_down.surrealql"
MIGRATION_35 = ROOT / "deeper_notebook/database/migrations/35.surrealql"
MIGRATION_35_DOWN = ROOT / "deeper_notebook/database/migrations/35_down.surrealql"
MIGRATION_36_DOWN = ROOT / "deeper_notebook/database/migrations/36_down.surrealql"
MIGRATION_37_DOWN = ROOT / "deeper_notebook/database/migrations/37_down.surrealql"
MIGRATION_38_DOWN = ROOT / "deeper_notebook/database/migrations/38_down.surrealql"


async def _restore_recorded_v35_state() -> None:
    """Undo overlay migration 36 so migration-35 behavior can be isolated."""
    await repo_query(MIGRATION_38_DOWN.read_text(encoding="utf-8"))
    await repo_query("DELETE type::thing('_sbl_migrations', 38);")
    await repo_query(MIGRATION_37_DOWN.read_text(encoding="utf-8"))
    await repo_query("DELETE type::thing('_sbl_migrations', 37);")
    await repo_query(MIGRATION_36_DOWN.read_text(encoding="utf-8"))
    await repo_query("DELETE type::thing('_sbl_migrations', 36);")


async def _restore_recorded_v32_state() -> None:
    """Undo the current-head migrations so the test starts at recorded v32."""
    await _restore_recorded_v35_state()
    await repo_query(MIGRATION_35_DOWN.read_text(encoding="utf-8"))
    await repo_query(MIGRATION_34_DOWN.read_text(encoding="utf-8"))
    await repo_query(
        """
        DELETE type::thing('_sbl_migrations', 35);
        DELETE type::thing('_sbl_migrations', 34);
        DELETE type::thing('_sbl_migrations', 33);
        """
    )


async def test_migration_creates_vault_projection_tables(clean_namespace):
    rows = await repo_query("INFO FOR DB;")
    head = rows[0] if isinstance(rows, list) else rows
    tables = head.get("tables") or head.get("tb") or {}

    assert {
        "vault_mount",
        "vault_file",
        "note_block",
        "note_link",
        "knowledge_task",
        "vault_revision",
        "vault_sync_receipt",
        "vault_trust_record",
    }.issubset(tables)
    assert {
        "knowledge_engine_space",
        "knowledge_engine_document",
        "knowledge_engine_block",
        "knowledge_engine_relation",
        "knowledge_engine_task",
        "knowledge_engine_asset",
        "knowledge_engine_view",
        "knowledge_engine_source_revision",
        "knowledge_engine_identity_map",
        "knowledge_engine_projection_receipt",
        "knowledge_engine_backfill_checkpoint",
    }.issubset(tables)
    assert await get_latest_version() == 38


async def test_migration_38_down_up_preserves_shadow_records(clean_namespace):
    await repo_query(
        "CREATE knowledge_engine_backfill_checkpoint:round_trip CONTENT $checkpoint;",
        {
            "checkpoint": {
                "schema_version": 1,
                "space_id": "space:round_trip",
                "last_relative_locator": "Pages/Round Trip.md",
                "last_source_hash": "a" * 64,
                "status": "completed",
                "projected": 1,
                "unchanged": 0,
                "failed": 0,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    await repo_query(MIGRATION_38_DOWN.read_text(encoding="utf-8"))
    await repo_query("DELETE type::thing('_sbl_migrations', 38);")
    assert await get_latest_version() == 37

    row_after_down = (
        await repo_query(
            "SELECT * FROM knowledge_engine_backfill_checkpoint:round_trip;"
        )
    )[0]
    assert str(row_after_down["id"]) == "knowledge_engine_backfill_checkpoint:round_trip"

    manager = AsyncMigrationManager()
    await manager.run_migration_up()
    assert await get_latest_version() == 38
    row_after_up = (
        await repo_query(
            "SELECT * FROM knowledge_engine_backfill_checkpoint:round_trip;"
        )
    )[0]
    assert str(row_after_up["id"]) == "knowledge_engine_backfill_checkpoint:round_trip"


async def _vault_file_fields() -> dict:
    rows = await repo_query("INFO FOR TABLE vault_file;")
    head = rows[0] if isinstance(rows, list) else rows
    return head.get("fields") or head.get("fd") or {}


async def _create_v34_vault_file(record_id: str, *, newline=None) -> None:
    data = {
        "schema_version": 1,
        "vault_id": ensure_record_id("vault_mount:integration"),
        "relative_path": f"Pages/{record_id.rsplit(':', 1)[-1]}.md",
        "file_kind": "markdown",
        "format": "obsidian",
        "content_hash": "a" * 64,
        "size_bytes": 7,
        "modified_ns": 1,
        "encoding": "utf-8",
        "parse_status": "parsed",
        "parse_error_code": None,
        "embedding_state": "pending",
        "deleted_state": "present",
    }
    if newline is not None:
        data["newline"] = newline
    await repo_query(
        "CREATE $id CONTENT $data;",
        {"id": ensure_record_id(record_id), "data": data},
    )


async def test_migration_35_exposes_optional_vault_file_newline_field(
    clean_namespace,
):
    assert "newline" in await _vault_file_fields()
    assert await get_latest_version() == 38


async def test_migration_35_upgrades_v34_row_without_newline(clean_namespace):
    await _restore_recorded_v35_state()
    await repo_query(MIGRATION_35_DOWN.read_text(encoding="utf-8"))
    await repo_query("DELETE type::thing('_sbl_migrations', 35);")
    assert await get_latest_version() == 34
    await _create_mount()
    await _create_v34_vault_file("vault_file:migration_without_newline")
    before = (
        await repo_query(
            "SELECT * FROM $id;",
            {"id": ensure_record_id("vault_file:migration_without_newline")},
        )
    )[0]
    assert "newline" not in before

    manager = AsyncMigrationManager()
    await manager.run_migration_up()

    assert await get_latest_version() == 38
    row = (
        await repo_query(
            "SELECT * FROM $id;",
            {"id": ensure_record_id("vault_file:migration_without_newline")},
        )
    )[0]
    assert row.get("newline") is None


async def test_migration_35_validates_newline_values_natively(clean_namespace):
    await _create_mount()
    await _create_v34_vault_file("vault_file:newline_crlf", newline="crlf")
    row = (
        await repo_query(
            "SELECT * FROM $id;",
            {"id": ensure_record_id("vault_file:newline_crlf")},
        )
    )[0]
    assert row["newline"] == "crlf"

    with pytest.raises(Exception):
        await _create_v34_vault_file(
            "vault_file:newline_invalid",
            newline="invalid-newline",
        )


async def test_migration_35_down_preserves_row_and_up_is_idempotent(
    clean_namespace,
):
    await _create_mount()
    await _create_v34_vault_file("vault_file:newline_round_trip", newline="crlf")

    await _restore_recorded_v35_state()
    await repo_query(MIGRATION_35_DOWN.read_text(encoding="utf-8"))

    assert "newline" not in await _vault_file_fields()
    rows = await repo_query(
        "SELECT * FROM $id;",
        {"id": ensure_record_id("vault_file:newline_round_trip")},
    )
    assert len(rows) == 1
    assert str(rows[0]["id"]) == "vault_file:newline_round_trip"

    await repo_query("DELETE type::thing('_sbl_migrations', 35);")
    assert await get_latest_version() == 34
    manager = AsyncMigrationManager()
    await manager.run_migration_up()
    await manager.run_migration_up()
    assert await get_latest_version() == 38
    assert "newline" in await _vault_file_fields()


async def test_migration_rejects_watching_on_mixed_parent(clean_namespace):
    with pytest.raises(Exception, match=r"(?i)(assert|watch|mixed)"):
        await repo_query(
            "CREATE vault_mount CONTENT $mount;",
            {
                "mount": {
                    "name": "2nd Brains",
                    "root_path": "/approved/2nd Brains",
                    "format_mode": "mixed",
                    "status": "ready-read-only",
                    "watch_enabled": True,
                    "write_policy": "read-only",
                    "protected_globs": [],
                    "parser_version": "test",
                }
            },
        )


async def test_mount_child_round_trips_native_record_typed_parent_id(
    clean_namespace, tmp_path
):
    """A child mount must persist and serialize its parent ID on native SurrealDB."""
    parent_root = tmp_path / "fixture-parent"
    child_root = parent_root / "fixture-child"
    child_root.mkdir(parents=True)

    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    parent = await repository.create_mount(
        VaultMountCreate(
            name="Fixture Parent",
            root_path=str(parent_root),
            format_mode="mixed",
            parser_version="integration",
        )
    )
    child = await repository.create_mount(
        VaultMountCreate(
            name="Fixture Child",
            root_path=str(child_root),
            format_mode="obsidian",
            parent_vault_id=parent.id,
            parser_version="integration",
        )
    )

    assert child.parent_vault_id == parent.id
    assert (await repository.get_mount(child.id)).parent_vault_id == parent.id
    listed = {mount.id: mount for mount in await repository.list_mounts()}
    assert listed[child.id].parent_vault_id == parent.id


async def test_vault_api_creates_child_mount_against_native_surrealdb(
    clean_namespace, monkeypatch, tmp_path
):
    """The branch API must not sanitize a valid native child mount as unavailable."""
    from api.main import app

    parent_root = tmp_path / "api-parent"
    child_root = parent_root / "api-child"
    child_root.mkdir(parents=True)
    # This test isolates native persistence and router serialization; root
    # approval has dedicated security coverage.
    monkeypatch.setattr(
        "api.routers.vault.approve_vault_root", lambda _path: nullcontext()
    )
    app.state.vault_service = VaultService(
        VaultRepository(embedding_submitter=lambda *_args: None)
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            parent_response = await client.post(
                "/api/deeper-notebook/vaults",
                json={
                    "name": "API Parent",
                    "path": str(parent_root),
                    "format_mode": "mixed",
                    "watch_enabled": False,
                },
            )
            assert parent_response.status_code == 201
            parent_id = parent_response.json()["id"]

            child_response = await client.post(
                "/api/deeper-notebook/vaults",
                json={
                    "name": "API Child",
                    "path": str(child_root),
                    "format_mode": "obsidian",
                    "parent_vault_id": parent_id,
                },
            )
            assert child_response.status_code == 201
            assert child_response.json()["parent_vault_id"] == parent_id

            listed = await client.get("/api/deeper-notebook/vaults")
            assert listed.status_code == 200
            child = next(
                item
                for item in listed.json()
                if item["id"] == child_response.json()["id"]
            )
            assert child["parent_vault_id"] == parent_id
    finally:
        app.state.vault_service = None


async def test_migration_32_up_down_up_and_reapply_are_safe(clean_namespace):
    await repo_query(DOWN.read_text(encoding="utf-8"))
    info_after_down = await repo_query("INFO FOR DB;")
    down_head = (
        info_after_down[0] if isinstance(info_after_down, list) else info_after_down
    )
    tables_after_down = down_head.get("tables") or {}
    assert "vault_mount" not in tables_after_down
    assert "note" in tables_after_down

    up = UP.read_text(encoding="utf-8")
    await repo_query(up)
    await repo_query(up)
    info_after_up = await repo_query("INFO FOR DB;")
    up_head = info_after_up[0] if isinstance(info_after_up, list) else info_after_up
    tables_after_up = up_head.get("tables") or {}
    assert "vault_mount" in tables_after_up
    assert "note" in tables_after_up


async def test_recorded_v32_schema_upgrades_through_idempotent_migration_33(
    clean_namespace,
):
    await _restore_recorded_v32_state()
    # Exact schema delta from 25bfea73 migration 32
    # (SHA-256 f38236a6c41eec6e3695881d677ac42ced24ec57c0b899d068339d18f9251dae):
    # title_key, target_title_key, the title-key index, and the composite trust
    # index did not exist. Reconstruct that state without approximating any
    # other part of the already-applied v32 schema.
    await repo_query(
        """
        REMOVE INDEX IF EXISTS idx_note_vault_title_key ON TABLE note;
        REMOVE FIELD IF EXISTS title_key ON TABLE note;
        REMOVE FIELD IF EXISTS target_title_key ON TABLE note_link;
        REMOVE INDEX IF EXISTS idx_vault_trust_manifest ON TABLE vault_trust_record;
        DEFINE INDEX IF NOT EXISTS idx_vault_trust_manifest
            ON TABLE vault_trust_record COLUMNS manifest_id UNIQUE;
        """
    )
    assert await get_latest_version() == 32

    mount_a = ensure_record_id("vault_mount:migration_a")
    mount_b = ensure_record_id("vault_mount:migration_b")
    await repo_query(
        "CREATE $id CONTENT $data;",
        {
            "id": mount_a,
            "data": {
                "schema_version": 1,
                "name": "Migration A",
                "root_path": "/synthetic/migration-a",
                "format_mode": "obsidian",
                "status": "ready-read-only",
                "watch_enabled": False,
                "write_policy": "read-only",
                "protected_globs": [],
                "parser_version": "integration",
            },
        },
    )
    await repo_query(
        "CREATE $id CONTENT $data;",
        {
            "id": mount_b,
            "data": {
                "schema_version": 1,
                "name": "Migration B",
                "root_path": "/synthetic/migration-b",
                "format_mode": "obsidian",
                "status": "ready-read-only",
                "watch_enabled": False,
                "write_policy": "read-only",
                "protected_globs": [],
                "parser_version": "integration",
            },
        },
    )

    note_ids = {
        name: ensure_record_id(f"note:migration_{name}")
        for name in (
            "a_source",
            "a_beta",
            "a_cafe_1",
            "a_cafe_2",
            "a_empty",
            "b_source",
            "b_beta",
            "b_only",
        )
    }
    notes = (
        ("a_source", mount_a, "Source A"),
        ("a_cafe_1", mount_a, " Café "),
        ("a_cafe_2", mount_a, "Ｃａｆｅ\u0301"),
        ("a_empty", mount_a, ""),
        ("b_source", mount_b, "Source B"),
        ("b_beta", mount_b, "Beta SPACE"),
        ("b_only", mount_b, "Only B"),
    )
    for name, vault_id, title in notes:
        await repo_query(
            "CREATE $id CONTENT $data;",
            {
                "id": note_ids[name],
                "data": {
                    "title": title,
                    "content": f"content-{name}",
                    "vault_id": vault_id,
                    "source_format": "obsidian",
                    "canonical_external": True,
                    "source_hash": name.ljust(64, "0"),
                    "external_state": "current",
                },
            },
        )

    link_ids = {
        name: ensure_record_id(f"note_link:migration_{name}")
        for name in ("a_unique", "a_duplicate", "a_cross", "a_empty", "b_unique")
    }
    seeded_links = (
        (
            "a_unique",
            note_ids["a_source"],
            "  beta \n  SPACE ",
            note_ids["b_beta"],
        ),
        (
            "a_duplicate",
            note_ids["a_source"],
            "  Ｃａｆｅ\u0301 ",
            note_ids["a_cafe_1"],
        ),
        (
            "a_cross",
            note_ids["a_source"],
            "Only\t B",
            note_ids["b_only"],
        ),
        (
            "a_empty",
            note_ids["a_source"],
            "",
            note_ids["b_only"],
        ),
        (
            "b_unique",
            note_ids["b_source"],
            "Ｂｅｔａ  SPACE",
            note_ids["a_beta"],
        ),
    )
    for position, (name, source_note_id, target_text, wrong_target_id) in enumerate(
        seeded_links
    ):
        await repo_query(
            "CREATE $id CONTENT $data;",
            {
                "id": link_ids[name],
                "data": {
                    "schema_version": 1,
                    "source_note_id": source_note_id,
                    "target_note_id": wrong_target_id,
                    "target_text": target_text,
                    "link_kind": "wikilink",
                    "resolved": True,
                    "source_start": position * 10,
                    "source_end": position * 10 + 5,
                },
            },
        )

    # The unique same-vault target appears after its link. Repair must use the
    # authoritative database state and must not require an unchanged scan.
    await repo_query(
        "CREATE $id CONTENT $data;",
        {
            "id": note_ids["a_beta"],
            "data": {
                "title": "  Ｂｅｔａ\t  SPACE ",
                "content": "content-a_beta",
                "vault_id": mount_a,
                "source_format": "obsidian",
                "canonical_external": True,
                "source_hash": "a_beta".ljust(64, "0"),
                "external_state": "current",
            },
        },
    )
    before_notes = {
        str(row["id"]): row
        for row in await repo_query("SELECT * FROM note ORDER BY id;")
    }
    before_links = {
        str(row["id"]): row
        for row in await repo_query("SELECT * FROM note_link ORDER BY id;")
    }

    manager = AsyncMigrationManager()
    await manager.run_migration_up()
    assert await get_latest_version() == 38

    note_info = await repo_query("INFO FOR TABLE note;")
    link_info = await repo_query("INFO FOR TABLE note_link;")
    trust_info = await repo_query("INFO FOR TABLE vault_trust_record;")
    note_info = note_info[0] if isinstance(note_info, list) else note_info
    link_info = link_info[0] if isinstance(link_info, list) else link_info
    trust_info = trust_info[0] if isinstance(trust_info, list) else trust_info
    assert "title_key" in (note_info.get("fields") or {})
    assert "idx_note_vault_title_key" in (note_info.get("indexes") or {})
    assert "target_title_key" in (link_info.get("fields") or {})
    trust_index = str((trust_info.get("indexes") or {})["idx_vault_trust_manifest"])
    assert "vault_id" in trust_index
    assert "manifest_relative_path" in trust_index
    assert "manifest_id" in trust_index

    notes_after = {
        str(row["id"]): row
        for row in await repo_query("SELECT * FROM note ORDER BY id;")
    }
    links_after = {
        str(row["id"]): row
        for row in await repo_query("SELECT * FROM note_link ORDER BY id;")
    }
    assert notes_after[str(note_ids["a_beta"])]["title_key"] == "beta space"
    assert notes_after[str(note_ids["a_cafe_1"])]["title_key"] == "café"
    assert notes_after[str(note_ids["a_cafe_2"])]["title_key"] == "café"
    assert notes_after[str(note_ids["a_empty"])]["title_key"] == ""
    assert links_after[str(link_ids["a_unique"])]["target_title_key"] == "beta space"
    assert links_after[str(link_ids["a_unique"])]["target_note_id"] == str(
        note_ids["a_beta"]
    )
    assert links_after[str(link_ids["a_unique"])]["resolved"] is True
    assert links_after[str(link_ids["a_duplicate"])]["target_title_key"] == "café"
    assert links_after[str(link_ids["a_duplicate"])].get("target_note_id") is None
    assert links_after[str(link_ids["a_duplicate"])]["resolved"] is False
    assert links_after[str(link_ids["a_cross"])]["target_title_key"] == "only b"
    assert links_after[str(link_ids["a_cross"])].get("target_note_id") is None
    assert links_after[str(link_ids["a_cross"])]["resolved"] is False
    assert links_after[str(link_ids["a_empty"])]["target_title_key"] == ""
    assert links_after[str(link_ids["a_empty"])]["target_note_id"] == str(
        note_ids["a_empty"]
    )
    assert links_after[str(link_ids["a_empty"])]["resolved"] is True
    assert links_after[str(link_ids["b_unique"])]["target_note_id"] == str(
        note_ids["b_beta"]
    )
    assert links_after[str(link_ids["b_unique"])]["resolved"] is True

    for note_id, before in before_notes.items():
        after = notes_after[note_id]
        assert after["title"] == before["title"]
        assert after["content"] == before["content"]
        assert after["created"] == before["created"]
        assert after["updated"] == before["updated"], note_id
        assert after["source_hash"] == before["source_hash"]
    for link_id, before in before_links.items():
        after = links_after[link_id]
        assert after["target_text"] == before["target_text"]
        assert after["source_note_id"] == before["source_note_id"]
        assert after["created"] == before["created"]
        assert after["updated"] == before["updated"], link_id
        assert after["source_start"] == before["source_start"]
        assert after["source_end"] == before["source_end"]

    await manager.runner.run_one_down()
    assert await get_latest_version() == 37
    await manager.runner.run_one_down()
    assert await get_latest_version() == 36
    await manager.runner.run_one_down()
    assert await get_latest_version() == 35
    await manager.runner.run_one_down()
    assert await get_latest_version() == 34
    await manager.runner.run_one_down()
    assert await get_latest_version() == 33
    await manager.runner.run_one_down()
    assert await get_latest_version() == 32
    await manager.run_migration_up()
    assert await get_latest_version() == 38
    assert await repo_query("SELECT * FROM note ORDER BY id;") == list(
        notes_after.values()
    )
    assert await repo_query("SELECT * FROM note_link ORDER BY id;") == list(
        links_after.values()
    )


class _MigrationBatchFailureConnection:
    def __init__(self, connection, *, mutation_marker: str) -> None:
        self._connection = connection
        self._mutation_marker = mutation_marker

    async def query(self, statement, variables=None):
        if self._mutation_marker in statement:
            proof = (
                "RETURN { canonical_updated_fields_restored: true };"
                if "canonical_updated_fields_restored" in statement
                else "RETURN { updated_preserved: true };"
            )
            statement = statement.replace(
                proof,
                f"THROW 'migration-33-injected-failure'; {proof}",
                1,
            )
        return await self._connection.query(statement, variables)


async def _updated_field_definition(table: str) -> str:
    info = await repo_query(f"INFO FOR TABLE {table};")
    info = info[0] if isinstance(info, list) else info
    return str((info.get("fields") or {})["updated"])


async def test_migration_33_note_batch_failure_rolls_back_row_and_field_definition(
    clean_namespace,
    monkeypatch,
):
    await _restore_recorded_v32_state()
    assert await get_latest_version() == 32
    mount_id = ensure_record_id("vault_mount:migration_rollback_note")
    note_id = ensure_record_id("note:migration_rollback_note")
    await repo_query(
        "CREATE $id CONTENT $data;",
        {
            "id": mount_id,
            "data": {
                "name": "Migration rollback note",
                "root_path": "/synthetic/migration-rollback-note",
                "format_mode": "obsidian",
                "status": "ready-read-only",
                "watch_enabled": False,
                "write_policy": "read-only",
                "protected_globs": [],
                "parser_version": "integration",
            },
        },
    )
    await repo_query(
        "CREATE $id CONTENT $data;",
        {
            "id": note_id,
            "data": {
                "title": "Rollback Note",
                "content": "before",
                "vault_id": mount_id,
                "source_format": "obsidian",
                "canonical_external": True,
                "source_hash": "rollback-note".ljust(64, "0"),
                "external_state": "current",
            },
        },
    )
    before = (await repo_query("SELECT * FROM $id;", {"id": note_id}))[0]
    schema_before = await _updated_field_definition("note")
    original_connection_factory = async_migrate.db_connection

    @asynccontextmanager
    async def failing_connection_factory():
        async with original_connection_factory() as connection:
            yield _MigrationBatchFailureConnection(
                connection,
                mutation_marker="SET title_key = $item.title_key",
            )

    manager = AsyncMigrationManager()
    with monkeypatch.context() as patch:
        patch.setattr(async_migrate, "db_connection", failing_connection_factory)
        with pytest.raises(Exception, match=r"(?i)(migration[_-]33|query[ _]failed)"):
            await manager.run_migration_up()

    assert await get_latest_version() == 32
    assert (await repo_query("SELECT * FROM $id;", {"id": note_id}))[0] == before
    failed_schema = await _updated_field_definition("note")
    assert "DEFAULT time::now()" in failed_schema
    assert "VALUE" not in failed_schema

    await manager.run_migration_up()
    assert await get_latest_version() == 38
    migrated = (await repo_query("SELECT * FROM $id;", {"id": note_id}))[0]
    assert migrated["title_key"] == "rollback note"
    assert migrated["updated"] == before["updated"]
    assert await _updated_field_definition("note") == schema_before

    await asyncio.sleep(0.01)
    await repo_query("UPDATE $id SET content = 'after';", {"id": note_id})
    later = (await repo_query("SELECT * FROM $id;", {"id": note_id}))[0]
    assert later["updated"] > before["updated"]


async def test_migration_33_link_batch_failure_rolls_back_row_and_field_definition(
    clean_namespace,
    monkeypatch,
):
    await _restore_recorded_v32_state()
    assert await get_latest_version() == 32
    mount_id = ensure_record_id("vault_mount:migration_rollback_link")
    source_id = ensure_record_id("note:migration_rollback_link_source")
    target_id = ensure_record_id("note:migration_rollback_link_target")
    link_id = ensure_record_id("note_link:migration_rollback_link")
    await repo_query(
        "CREATE $id CONTENT $data;",
        {
            "id": mount_id,
            "data": {
                "name": "Migration rollback link",
                "root_path": "/synthetic/migration-rollback-link",
                "format_mode": "obsidian",
                "status": "ready-read-only",
                "watch_enabled": False,
                "write_policy": "read-only",
                "protected_globs": [],
                "parser_version": "integration",
            },
        },
    )
    for note_id, title in ((source_id, "Source"), (target_id, "Target")):
        await repo_query(
            "CREATE $id CONTENT $data;",
            {
                "id": note_id,
                "data": {
                    "title": title,
                    "title_key": title.casefold(),
                    "content": title,
                    "vault_id": mount_id,
                    "source_format": "obsidian",
                    "canonical_external": True,
                    "source_hash": str(note_id).ljust(64, "0")[:64],
                    "external_state": "current",
                },
            },
        )
    await repo_query("REMOVE FIELD target_title_key ON TABLE note_link;")
    await repo_query(
        "CREATE $id CONTENT $data;",
        {
            "id": link_id,
            "data": {
                "source_note_id": source_id,
                "target_text": "Target",
                "link_kind": "wikilink",
                "resolved": False,
                "source_start": 0,
                "source_end": 6,
            },
        },
    )
    before = (await repo_query("SELECT * FROM $id;", {"id": link_id}))[0]
    schema_before = await _updated_field_definition("note_link")
    original_connection_factory = async_migrate.db_connection

    @asynccontextmanager
    async def failing_connection_factory():
        async with original_connection_factory() as connection:
            yield _MigrationBatchFailureConnection(
                connection,
                mutation_marker="SET target_title_key = $item.target_title_key",
            )

    manager = AsyncMigrationManager()
    with monkeypatch.context() as patch:
        patch.setattr(async_migrate, "db_connection", failing_connection_factory)
        with pytest.raises(Exception, match=r"(?i)(migration[_-]33|query[ _]failed)"):
            await manager.run_migration_up()

    assert await get_latest_version() == 32
    assert (await repo_query("SELECT * FROM $id;", {"id": link_id}))[0] == before
    failed_schema = await _updated_field_definition("note_link")
    assert "DEFAULT time::now()" in failed_schema
    assert "VALUE" not in failed_schema

    await manager.run_migration_up()
    assert await get_latest_version() == 38
    migrated = (await repo_query("SELECT * FROM $id;", {"id": link_id}))[0]
    assert migrated["target_title_key"] == "target"
    assert migrated["target_note_id"] == str(target_id)
    assert migrated["resolved"] is True
    assert migrated["updated"] == before["updated"]
    assert await _updated_field_definition("note_link") == schema_before

    await asyncio.sleep(0.01)
    await repo_query("UPDATE $id SET alias = 'later';", {"id": link_id})
    later = (await repo_query("SELECT * FROM $id;", {"id": link_id}))[0]
    assert later["updated"] > before["updated"]


async def test_migration_33_final_restore_failure_rolls_back_both_field_definitions(
    clean_namespace,
    monkeypatch,
):
    await _restore_recorded_v32_state()
    assert await get_latest_version() == 32
    note_schema_before = await _updated_field_definition("note")
    link_schema_before = await _updated_field_definition("note_link")
    original_connection_factory = async_migrate.db_connection

    @asynccontextmanager
    async def failing_connection_factory():
        async with original_connection_factory() as connection:
            yield _MigrationBatchFailureConnection(
                connection,
                mutation_marker="canonical_updated_fields_restored",
            )

    manager = AsyncMigrationManager()
    with monkeypatch.context() as patch:
        patch.setattr(async_migrate, "db_connection", failing_connection_factory)
        with pytest.raises(Exception, match=r"(?i)(migration[_-]33|query[ _]failed)"):
            await manager.run_migration_up()

    assert await get_latest_version() == 32
    failed_note_schema = await _updated_field_definition("note")
    failed_link_schema = await _updated_field_definition("note_link")
    assert "DEFAULT time::now()" in failed_note_schema
    assert "VALUE" not in failed_note_schema
    assert "DEFAULT time::now()" in failed_link_schema
    assert "VALUE" not in failed_link_schema

    await manager.run_migration_up()
    assert await get_latest_version() == 38
    assert await _updated_field_definition("note") == note_schema_before
    assert await _updated_field_definition("note_link") == link_schema_before


def _mount() -> VaultMount:
    return VaultMount(
        id="vault_mount:integration",
        name="Synthetic integration vault",
        root_path="/synthetic/integration-vault",
        format_mode="obsidian",
        status="ready-read-only",
        watch_enabled=True,
        write_policy="read-only",
        protected_globs=[],
        parser_version="integration",
    )


def _work(
    content_hash: str = "a" * 64,
    *,
    modified_ns: int = 123,
) -> VaultWorkItem:
    return VaultWorkItem(
        vault_id="vault_mount:integration",
        relative_path="Pages/Alpha.md",
        file_kind="markdown",
        protected=False,
        content=b"# Alpha\n- [ ] Task [[Beta]]",
        content_hash=content_hash,
        byte_size=28,
        modified_ns=modified_ns,
    )


def _document(content_hash: str = "a" * 64) -> ParsedDocument:
    markdown = "# Alpha\n- [ ] Task [[Beta]]"
    return ParsedDocument(
        relative_path="Pages/Alpha.md",
        source_format="obsidian",
        title="Alpha",
        markdown=markdown,
        content_hash=content_hash,
        newline="lf",
        blocks=[
            ParsedBlock(
                parser_id="heading",
                position=0,
                block_kind="heading",
                markdown="# Alpha",
                plain_text="Alpha",
                source_start=0,
                source_end=7,
            ),
            ParsedBlock(
                parser_id="task",
                position=1,
                block_kind="task",
                markdown="- [ ] Task [[Beta]]",
                plain_text="Task Beta",
                task_state="todo",
                source_start=8,
                source_end=len(markdown.encode()),
            ),
        ],
        links=[
            ParsedLink(
                source_block_parser_id="task",
                target_text="Beta",
                link_kind="wikilink",
                source_start=19,
                source_end=27,
            )
        ],
        tasks=[ParsedTask(block_parser_id="task", status="todo")],
    )


async def _create_mount() -> None:
    await repo_query(
        "CREATE vault_mount:integration CONTENT $mount;",
        {
            "mount": {
                "schema_version": 1,
                "name": "Synthetic integration vault",
                "root_path": "/synthetic/integration-vault",
                "format_mode": "obsidian",
                "status": "ready-read-only",
                "watch_enabled": True,
                "write_policy": "read-only",
                "protected_globs": [],
                "parser_version": "integration",
            }
        },
    )


async def test_complete_projection_is_atomic_and_record_typed(clean_namespace):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    result = await repository.project_document(
        _mount(), _work(), _document(), "integration-project"
    )

    assert result.status == "projected"
    file_rows = await repo_query("SELECT * FROM vault_file;")
    assert len(file_rows) == 1
    assert file_rows[0]["newline"] == "lf"
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM note_block;")) == 2
    assert len(await repo_query("SELECT * FROM note_link;")) == 1
    assert len(await repo_query("SELECT * FROM knowledge_task;")) == 1
    receipts = await repo_query("SELECT * FROM vault_sync_receipt;")
    assert len(receipts) == 1
    assert receipts[0]["status"] == "success"
    assert receipts[0].get("before_hash") is None
    assert receipts[0]["after_hash"] == "a" * 64


async def test_owned_projection_is_overlay_scoped_and_keeps_vault_tables_immutable(
    clean_namespace,
):
    overlay_space_id = ensure_record_id("overlay_space:default")
    overlay_note_id = ensure_record_id("overlay_note:integration_owned")
    projected_note_id = ensure_record_id("note:integration_owned")
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    await repo_query(
        """
        CREATE $space_id CONTENT $space;
        CREATE $overlay_note_id CONTENT $overlay_note;
        """,
        {
            "space_id": overlay_space_id,
            "space": {
                "schema_version": 1,
                "slug": "default",
                "display_name": "Deeper Notebook Overlay",
                "root_version": 1,
                "created_at": now,
                "updated_at": now,
            },
            "overlay_note_id": overlay_note_id,
            "overlay_note": {
                "schema_version": 1,
                "space_id": overlay_space_id,
                "projected_note_id": projected_note_id,
                "stable_id": "01JTESTOVERLAY000000000001",
                "kind": "unique",
                "date_key": None,
                "relative_path": "Notes/20260729-1542 Alpha.md",
                "title": "Alpha",
                "content_hash": "a" * 64,
                "revision": 1,
                "projection_state": "current",
                "encoding": "utf-8",
                "newline": "lf",
                "created_at": now,
                "updated_at": now,
            },
        },
    )
    repository = VaultRepository(embedding_submitter=lambda *_args: None)

    page = await repository.project_owned_document(
        source_authority="overlay",
        overlay_space_id="overlay_space:default",
        overlay_note_id="overlay_note:integration_owned",
        projected_note_id="note:integration_owned",
        parsed=_document(),
        revision=1,
    )

    assert page.overlay.id == "overlay_note:integration_owned"
    assert page.note["source_authority"] == "overlay"
    assert page.note["canonical_external"] is False
    blocks = await repo_query("SELECT * FROM note_block;")
    assert len(blocks) == 2
    assert all(block.get("vault_file_id") is None for block in blocks)
    assert all(
        str(block["overlay_note_id"]) == "overlay_note:integration_owned"
        for block in blocks
    )
    assert await repo_query("SELECT * FROM vault_mount;") == []
    assert await repo_query("SELECT * FROM vault_file;") == []
    assert await repo_query("SELECT * FROM vault_sync_receipt;") == []


async def test_obsidian_fixture_embeds_project_once_per_source_span(clean_namespace):
    await _create_mount()
    raw = (ROOT / "tests/fixtures/vault/obsidian/complete.md").read_bytes()
    parsed = parse_document("complete.md", raw, format_mode="obsidian")
    work = VaultWorkItem(
        vault_id="vault_mount:integration",
        relative_path="complete.md",
        file_kind="markdown",
        protected=False,
        content=raw,
        content_hash=parsed.content_hash,
        byte_size=len(raw),
        modified_ns=456,
    )
    repository = VaultRepository(embedding_submitter=lambda *_args: None)

    first = await repository.project_document(
        _mount(), work, parsed, "integration-obsidian-embeds"
    )
    second = await repository.project_document(
        _mount(), work, parsed, "integration-obsidian-embeds-repeat"
    )

    assert first.status == "projected"
    assert second.status == "unchanged"
    links = await repo_query("SELECT * FROM note_link;")
    assert len(links) == len(
        {(link.source_start, link.source_end) for link in parsed.links}
    )
    assert sum(link["link_kind"] == "embed" for link in links) == 2


class _InjectFailureConnection:
    def __init__(self, connection) -> None:
        self._connection = connection

    async def query(self, statement, variables=None):
        if "FOR $link IN $links" in statement:
            statement = statement.replace(
                "FOR $link IN $links {",
                "THROW 'integration-injected-failure'; FOR $link IN $links {",
                1,
            )
        return await self._connection.query(statement, variables)


@asynccontextmanager
async def _failure_connection():
    async with db_connection() as connection:
        yield _InjectFailureConnection(connection)


async def test_injected_mid_projection_failure_rolls_back_rows(clean_namespace):
    await _create_mount()
    repository = VaultRepository(
        connection_factory=_failure_connection,
        embedding_submitter=lambda *_args: None,
    )
    with pytest.raises(Exception, match="database query failed"):
        await repository.project_document(
            _mount(), _work(), _document(), "integration-failed"
        )

    assert await repo_query("SELECT * FROM note;") == []
    assert await repo_query("SELECT * FROM note_block;") == []
    assert await repo_query("SELECT * FROM note_link;") == []
    assert await repo_query("SELECT * FROM knowledge_task;") == []
    files = await repo_query("SELECT * FROM vault_file;")
    assert len(files) == 1
    assert files[0]["parse_status"] == "invalid"
    assert files[0]["content_hash"] == "a" * 64
    receipts = await repo_query("SELECT * FROM vault_sync_receipt;")
    assert len(receipts) == 1
    assert receipts[0]["status"] == "stale-invalid"


async def test_same_hash_is_idempotent_and_missing_preserves_projection(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    first = await repository.project_document(
        _mount(), _work(), _document(), "integration-first"
    )
    second = await repository.project_document(
        _mount(), _work(), _document(), "integration-unchanged"
    )
    assert first.status == "projected"
    assert second.status == "unchanged"
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM note_block;")) == 2
    receipts = await repo_query("SELECT * FROM vault_sync_receipt;")
    assert len(receipts) == 2
    by_operation = {row["operation_id"]: row for row in receipts}
    unchanged = by_operation["integration-unchanged"]
    assert unchanged["status"] == "unchanged"
    assert unchanged["before_hash"] == "a" * 64
    assert unchanged["after_hash"] == "a" * 64

    await repository.mark_missing(
        "vault_mount:integration",
        "Pages/Alpha.md",
        "integration-missing",
    )
    await repository.mark_missing(
        "vault_mount:integration",
        "Pages/Alpha.md",
        "integration-missing-repeat",
    )
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM note_block;")) == 2
    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    assert file_row["deleted_state"] == "missing"
    assert note_row["external_state"] == "stale"
    assert len(await repo_query("SELECT * FROM vault_sync_receipt;")) == 3


def _single_note_work(
    *,
    vault_id: str,
    relative_path: str,
    title: str,
    content_hash: str,
    modified_ns: int,
) -> VaultWorkItem:
    content = f"# {title}".encode()
    return VaultWorkItem(
        vault_id=vault_id,
        relative_path=relative_path,
        file_kind="markdown",
        protected=False,
        content=content,
        content_hash=content_hash,
        byte_size=len(content),
        modified_ns=modified_ns,
    )


def _single_note_document(
    *,
    relative_path: str,
    title: str,
    content_hash: str,
) -> ParsedDocument:
    markdown = f"# {title}"
    return ParsedDocument(
        relative_path=relative_path,
        source_format="obsidian",
        title=title,
        markdown=markdown,
        content_hash=content_hash,
        newline="none",
        blocks=[
            ParsedBlock(
                parser_id="heading",
                position=0,
                block_kind="heading",
                markdown=markdown,
                plain_text=title,
                source_start=0,
                source_end=len(markdown.encode()),
            )
        ],
    )


async def _create_named_mount(
    *,
    vault_id: str,
    name: str,
    root_path: str,
) -> VaultMount:
    mount = VaultMount(
        id=vault_id,
        name=name,
        root_path=root_path,
        format_mode="obsidian",
        status="ready-read-only",
        watch_enabled=True,
        write_policy="read-only",
        protected_globs=[],
        parser_version="integration",
    )
    data = mount.model_dump(exclude={"id", "parent_vault_id"})
    await repo_query(
        "CREATE $mount_id CONTENT $mount;",
        {"mount_id": ensure_record_id(vault_id), "mount": data},
    )
    return mount


async def test_task_dates_round_trip_as_utc_datetimes(clean_namespace):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    parsed = _document().model_copy(
        update={
            "tasks": [
                ParsedTask(
                    block_parser_id="task",
                    status="done",
                    scheduled=date(2026, 7, 28),
                    due=date(2026, 7, 29),
                    completed=date(2026, 7, 30),
                )
            ]
        }
    )

    await repository.project_document(
        _mount(), _work(), parsed, "integration-task-dates"
    )

    task = (await repo_query("SELECT * FROM knowledge_task;"))[0]
    assert task["scheduled"] == datetime(2026, 7, 28, tzinfo=timezone.utc)
    assert task["due"] == datetime(2026, 7, 29, tzinfo=timezone.utc)
    assert task["completed"] == datetime(2026, 7, 30, tzinfo=timezone.utc)
    for field in ("scheduled", "due", "completed"):
        assert task[field].tzinfo is not None
        assert task[field].utcoffset() == timezone.utc.utcoffset(task[field])


async def test_changed_projection_failure_stales_but_preserves_prior_graph(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    await repository.project_document(
        _mount(), _work("a" * 64, modified_ns=100), _document(), "prior-success"
    )

    failing_repository = VaultRepository(
        connection_factory=_failure_connection,
        embedding_submitter=lambda *_args: None,
    )
    with pytest.raises(Exception, match="database query failed"):
        await failing_repository.project_document(
            _mount(),
            _work("b" * 64, modified_ns=200),
            _document("b" * 64),
            "changed-failure",
        )

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    blocks = await repo_query("SELECT * FROM note_block ORDER BY position;")
    assert file_row["content_hash"] == "b" * 64
    assert file_row["modified_ns"] == 200
    assert file_row["parse_status"] == "invalid"
    assert file_row["parse_error_code"] == "projection_failed"
    assert note_row["source_hash"] == "a" * 64
    assert note_row["external_state"] == "stale"
    assert note_row["content"] == _document().markdown
    assert [row["parser_id"] for row in blocks] == ["heading", "task"]


async def test_late_target_duplicate_ambiguity_and_rename_reconcile_links(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    source = await repository.project_document(
        _mount(),
        _work("a" * 64, modified_ns=100),
        _document(),
        "link-source",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is False
    assert link.get("target_note_id") is None

    beta = await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Beta.md",
            title="  Beta  ",
            content_hash="b" * 64,
            modified_ns=200,
        ),
        _single_note_document(
            relative_path="Pages/Beta.md",
            title="  Beta  ",
            content_hash="b" * 64,
        ),
        "late-beta",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is True
    assert str(link["target_note_id"]) == beta.note_id

    duplicate = await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Fullwidth-Beta.md",
            title="ＢＥＴＡ",
            content_hash="c" * 64,
            modified_ns=300,
        ),
        _single_note_document(
            relative_path="Pages/Fullwidth-Beta.md",
            title="ＢＥＴＡ",
            content_hash="c" * 64,
        ),
        "duplicate-beta",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is False
    assert link.get("target_note_id") is None

    await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Fullwidth-Beta.md",
            title="Gamma",
            content_hash="d" * 64,
            modified_ns=400,
        ),
        _single_note_document(
            relative_path="Pages/Fullwidth-Beta.md",
            title="Gamma",
            content_hash="d" * 64,
        ),
        "rename-duplicate",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is True
    assert str(link["target_note_id"]) == beta.note_id

    await repository.project_document(
        _mount(),
        _single_note_work(
            vault_id=_mount().id,
            relative_path="Pages/Beta.md",
            title="Delta",
            content_hash="e" * 64,
            modified_ns=500,
        ),
        _single_note_document(
            relative_path="Pages/Beta.md",
            title="Delta",
            content_hash="e" * 64,
        ),
        "rename-beta",
    )
    link = (await repo_query("SELECT * FROM note_link;"))[0]
    assert link["resolved"] is False
    assert link.get("target_note_id") is None
    assert source.note_id != duplicate.note_id


async def test_link_reads_and_graph_reject_corrupt_cross_mount_target(clean_namespace):
    first = await _create_named_mount(
        vault_id="vault_mount:integration",
        name="First",
        root_path="/synthetic/first",
    )
    second = await _create_named_mount(
        vault_id="vault_mount:second",
        name="Second",
        root_path="/synthetic/second",
    )
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    source = await repository.project_document(
        first, _work(), _document(), "cross-source"
    )
    target = await repository.project_document(
        second,
        _single_note_work(
            vault_id=second.id,
            relative_path="Beta.md",
            title="Beta",
            content_hash="b" * 64,
            modified_ns=200,
        ),
        _single_note_document(
            relative_path="Beta.md",
            title="Beta",
            content_hash="b" * 64,
        ),
        "cross-target",
    )
    await repo_query(
        "UPDATE note_link SET target_note_id = $target, resolved = true;",
        {"target": ensure_record_id(target.note_id)},
    )

    assert await repository.outgoing_links(first.id, source.note_id) == []
    with pytest.raises(LookupError, match="vault_note_not_found"):
        await repository.backlinks(first.id, target.note_id)
    graph = await repository.graph(first.id, source.note_id, depth=2, limit=10)
    assert [node["id"] for node in graph.nodes] == [source.note_id]
    assert graph.edges == []


async def test_link_reads_reject_cross_vault_target_file_corruption(clean_namespace):
    first = await _create_named_mount(
        vault_id="vault_mount:integration",
        name="First",
        root_path="/synthetic/first",
    )
    second = await _create_named_mount(
        vault_id="vault_mount:second",
        name="Second",
        root_path="/synthetic/second",
    )
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    source = await repository.project_document(
        first, _work(), _document(), "cross-file-source"
    )
    target = await repository.project_document(
        first,
        _single_note_work(
            vault_id=first.id,
            relative_path="Beta.md",
            title="Beta",
            content_hash="b" * 64,
            modified_ns=200,
        ),
        _single_note_document(
            relative_path="Beta.md",
            title="Beta",
            content_hash="b" * 64,
        ),
        "cross-file-target",
    )
    foreign = await repository.project_document(
        second,
        _single_note_work(
            vault_id=second.id,
            relative_path="Foreign.md",
            title="Foreign",
            content_hash="c" * 64,
            modified_ns=300,
        ),
        _single_note_document(
            relative_path="Foreign.md",
            title="Foreign",
            content_hash="c" * 64,
        ),
        "cross-file-foreign",
    )
    await repo_query(
        "DELETE $foreign_note;",
        {"foreign_note": ensure_record_id(foreign.note_id)},
    )
    await repo_query(
        "UPDATE $target SET vault_file_id = $foreign_file;",
        {
            "target": ensure_record_id(target.note_id),
            "foreign_file": ensure_record_id(foreign.vault_file_id),
        },
    )

    with pytest.raises(VaultProjectionError, match="vault_link_target_invalid"):
        await repository.outgoing_links(first.id, source.note_id)


class _DelayedOrLostResponseConnection:
    def __init__(
        self,
        connection,
        *,
        delay_modified_ns: int | None = None,
        delay_content_hash: str | None = None,
        lose_operation_id: str | None = None,
        query_started: asyncio.Event | None = None,
        query_terminal: asyncio.Event | None = None,
    ) -> None:
        self._connection = connection
        self._delay_modified_ns = delay_modified_ns
        self._delay_content_hash = delay_content_hash
        self._lose_operation_id = lose_operation_id
        self._query_started = query_started
        self._query_terminal = query_terminal

    async def query(self, statement, variables=None):
        variables = variables or {}
        if self._query_started is not None and "LET $existing_file" in statement:
            self._query_started.set()
        if (
            self._delay_modified_ns is not None
            and variables.get("observed_modified_ns") == self._delay_modified_ns
        ) or (
            self._delay_content_hash is not None
            and variables.get("content_hash") == self._delay_content_hash
        ):
            await asyncio.sleep(0.05)
        try:
            result = await self._connection.query(statement, variables)
            receipt = variables.get("success_receipt") or {}
            if receipt.get("operation_id") == self._lose_operation_id:
                raise ConnectionError("synthetic response lost after commit")
            return result
        finally:
            if self._query_terminal is not None and "LET $existing_file" in statement:
                self._query_terminal.set()


def _ordered_connection_factory(
    *,
    delay_modified_ns: int | None = None,
    delay_content_hash: str | None = None,
    lose_operation_id: str | None = None,
    query_started: asyncio.Event | None = None,
    query_terminal: asyncio.Event | None = None,
):
    @asynccontextmanager
    async def factory():
        async with db_connection() as connection:
            yield _DelayedOrLostResponseConnection(
                connection,
                delay_modified_ns=delay_modified_ns,
                delay_content_hash=delay_content_hash,
                lose_operation_id=lose_operation_id,
                query_started=query_started,
                query_terminal=query_terminal,
            )

    return factory


async def test_concurrent_stale_projection_and_lost_response_keep_newest(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(
        connection_factory=_ordered_connection_factory(
            delay_modified_ns=100,
            lose_operation_id="older-lost-response",
        ),
        embedding_submitter=lambda *_args: None,
    )

    older = asyncio.create_task(
        repository.project_document(
            _mount(),
            _work("a" * 64, modified_ns=100),
            _document("a" * 64),
            "older-lost-response",
        )
    )
    newer = asyncio.create_task(
        repository.project_document(
            _mount(),
            _work("b" * 64, modified_ns=200),
            _document("b" * 64),
            "newer-success",
        )
    )
    older_result, newer_result = await asyncio.gather(older, newer)

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    receipts = await repo_query(
        "SELECT operation_id, status, after_hash FROM vault_sync_receipt;"
    )
    assert file_row["content_hash"] == "b" * 64
    assert file_row["modified_ns"] == 200
    assert note_row["source_hash"] == "b" * 64
    assert newer_result.status == "projected"
    assert older_result.status == "superseded"
    assert {row["status"] for row in receipts} == {"success", "superseded"}


async def test_delayed_equal_timestamp_projection_conflicts_without_overwrite(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(
        connection_factory=_ordered_connection_factory(
            delay_content_hash="a" * 64,
        ),
        embedding_submitter=lambda *_args: None,
    )

    delayed_a = asyncio.create_task(
        repository.project_document(
            _mount(),
            _work("a" * 64, modified_ns=200),
            _document("a" * 64),
            "delayed-equal-a",
        )
    )
    await asyncio.sleep(0)
    b_result = await repository.project_document(
        _mount(),
        _work("b" * 64, modified_ns=200),
        _document("b" * 64),
        "current-equal-b",
    )
    a_result = await delayed_a

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    receipts = await repo_query(
        "SELECT operation_id, status, error_code FROM vault_sync_receipt;"
    )
    by_operation = {row["operation_id"]: row for row in receipts}
    assert file_row["content_hash"] == "b" * 64
    assert file_row["modified_ns"] == 200
    assert note_row["source_hash"] == "b" * 64
    assert b_result.status == "projected"
    assert a_result.status == "conflict"
    assert a_result.reconciliation_required is True
    assert by_operation["delayed-equal-a"]["status"] == "conflict"
    assert by_operation["delayed-equal-a"]["error_code"] == "reconciliation_required"


async def test_equal_timestamp_failure_conflicts_without_invalidating_other_hash(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    await repository.project_document(
        _mount(),
        _work("b" * 64, modified_ns=200),
        _document("b" * 64),
        "current-success",
    )

    result = await repository.record_failure(
        _mount().id,
        _work("a" * 64, modified_ns=200),
        "conflicting-equal-timestamp-failure",
        "parse_failed",
    )

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    receipts = await repo_query(
        "SELECT operation_id, status, error_code FROM vault_sync_receipt;"
    )
    by_operation = {row["operation_id"]: row for row in receipts}
    assert file_row["content_hash"] == "b" * 64
    assert file_row["parse_status"] == "parsed"
    assert file_row["deleted_state"] == "present"
    assert result.status == "conflict"
    assert result.reconciliation_required is True
    assert by_operation["conflicting-equal-timestamp-failure"]["status"] == "conflict"
    assert (
        by_operation["conflicting-equal-timestamp-failure"]["error_code"]
        == "reconciliation_required"
    )


async def test_newer_failure_marks_file_stale_and_preserves_last_valid_graph(
    clean_namespace,
):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    await repository.project_document(
        _mount(),
        _work("b" * 64, modified_ns=200),
        _document("b" * 64),
        "valid-before-newer-failure",
    )
    before_counts = {
        table: len(await repo_query(f"SELECT * FROM {table};"))
        for table in ("note", "note_block", "note_link", "knowledge_task")
    }

    result = await repository.record_failure(
        _mount().id,
        _work("c" * 64, modified_ns=300),
        "newer-failure",
        "parse_failed",
    )

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    receipt = (
        await repo_query(
            "SELECT * FROM vault_sync_receipt WHERE operation_id = 'newer-failure';"
        )
    )[0]
    after_counts = {
        table: len(await repo_query(f"SELECT * FROM {table};"))
        for table in ("note", "note_block", "note_link", "knowledge_task")
    }
    assert file_row["content_hash"] == "c" * 64
    assert file_row["modified_ns"] == 300
    assert file_row["parse_status"] == "invalid"
    assert file_row["parse_error_code"] == "parse_failed"
    assert note_row["source_hash"] == "b" * 64
    assert note_row["external_state"] == "stale"
    assert before_counts == after_counts
    assert result.status == "stale-invalid"
    assert result.reconciliation_required is False
    assert receipt["status"] == "stale-invalid"


async def test_cancellation_waits_for_native_projection_and_embeds_once(
    clean_namespace,
):
    await _create_mount()
    started = asyncio.Event()
    terminal = asyncio.Event()
    embedding_calls: list[str] = []

    async def embed(_app, _command, payload):
        embedding_calls.append(payload["note_id"])

    repository = VaultRepository(
        connection_factory=_ordered_connection_factory(
            delay_modified_ns=100,
            query_started=started,
            query_terminal=terminal,
        ),
        embedding_submitter=embed,
    )
    projection = asyncio.create_task(
        repository.project_document(
            _mount(),
            _work("a" * 64, modified_ns=100),
            _document(),
            "cancel-native",
        )
    )
    await started.wait()
    projection.cancel()
    with pytest.raises(asyncio.CancelledError):
        await projection

    assert terminal.is_set()
    assert len(await repo_query("SELECT * FROM note;")) == 1
    assert len(await repo_query("SELECT * FROM vault_sync_receipt;")) == 1
    assert len(embedding_calls) == 1


async def test_missing_projection_corrective_missing_round_trip(clean_namespace):
    await _create_mount()
    repository = VaultRepository(embedding_submitter=lambda *_args: None)
    await repository.mark_missing(
        _mount().id, "Pages/Alpha.md", "missing-before-projection"
    )
    await repository.project_document(
        _mount(),
        _work("a" * 64, modified_ns=100),
        _document(),
        "projection-after-missing",
    )
    await repository.mark_missing(_mount().id, "Pages/Alpha.md", "corrective-missing")

    file_row = (await repo_query("SELECT * FROM vault_file;"))[0]
    note_row = (await repo_query("SELECT * FROM note;"))[0]
    assert file_row["parse_status"] == "missing"
    assert file_row["deleted_state"] == "missing"
    assert note_row["external_state"] == "stale"
    assert len(await repo_query("SELECT * FROM vault_sync_receipt;")) == 3


async def test_multi_record_trust_is_vault_scoped_and_idempotent(
    clean_namespace,
):
    root_path = ROOT / "tests/fixtures/vault/trust/multi-a"
    second_root_path = ROOT / "tests/fixtures/vault/trust/multi-b"
    first = await _create_named_mount(
        vault_id="vault_mount:trust_first",
        name="Trust first",
        root_path=str(root_path),
    )
    second = await _create_named_mount(
        vault_id="vault_mount:trust_second",
        name="Trust second",
        root_path=str(second_root_path),
    )
    approved = approve_vault_root(root_path)
    second_approved = approve_vault_root(second_root_path)
    repository = VaultRepository(
        approved_roots={first.id: approved, second.id: second_approved}
    )
    try:
        first_import = await repository.import_trust_manifest(
            first.id, "brain-engine/trust.json"
        )
        unchanged = await repository.import_trust_manifest(
            first.id, "brain-engine/trust.json"
        )
        second_import = await repository.import_trust_manifest(
            second.id, "brain-engine/trust.json"
        )
    finally:
        approved.close()
        second_approved.close()

    rows = await repo_query(
        "SELECT vault_id, manifest_relative_path, manifest_id, content_hash "
        "FROM vault_trust_record;"
    )
    assert first_import.changed == 2
    assert unchanged.unchanged == 2
    assert second_import.changed == 2
    assert len(rows) == 4
    assert {str(row["vault_id"]) for row in rows} == {first.id, second.id}
