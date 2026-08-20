from __future__ import annotations

from pathlib import Path

from deeper_notebook.database.async_migrate import AsyncMigrationManager

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/38.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/38_down.surrealql"

TABLES = (
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
)

FIELDS = {
    "knowledge_engine_space": (
        "schema_version",
        "display_name",
        "authority_kind",
        "source_kind",
        "source_ref",
        "format_mode",
        "availability_state",
        "projection_state",
        "adapter_version",
        "parser_version",
        "policy_version",
        "capabilities",
        "created_at",
        "updated_at",
    ),
    "knowledge_engine_document": (
        "schema_version",
        "space_id",
        "source_native_id",
        "authority_kind",
        "relative_locator",
        "document_kind",
        "title",
        "normalized_body",
        "properties",
        "tags",
        "content_hash",
        "source_revision_id",
        "provenance",
        "availability",
        "parse_state",
        "journal_date",
        "capabilities",
        "created_at",
        "observed_at",
        "updated_at",
    ),
    "knowledge_engine_block": (
        "schema_version",
        "space_id",
        "document_id",
        "parent_block_id",
        "position",
        "source_key",
        "block_kind",
        "markdown",
        "plain_text",
        "properties",
        "raw_task_state",
        "normalized_task_state",
        "heading_path",
        "source_start",
        "source_end",
        "source_revision_id",
        "capabilities",
    ),
    "knowledge_engine_relation": (
        "schema_version",
        "space_id",
        "source_document_id",
        "source_block_id",
        "target_document_id",
        "target_block_id",
        "target_text",
        "target_heading",
        "target_block",
        "alias",
        "relation_kind",
        "resolved",
        "source_start",
        "source_end",
        "source_revision_id",
    ),
    "knowledge_engine_task": (
        "schema_version",
        "space_id",
        "document_id",
        "block_id",
        "raw_status",
        "normalized_status",
        "scheduled",
        "due",
        "completed",
        "priority",
        "recurrence",
        "tags",
        "properties",
        "source_start",
        "source_end",
        "source_revision_id",
        "capabilities",
    ),
    "knowledge_engine_asset": (
        "schema_version",
        "space_id",
        "source_document_id",
        "relative_locator",
        "media_kind",
        "content_hash",
        "byte_size",
        "availability",
        "metadata",
        "provenance",
        "source_revision_id",
        "capabilities",
    ),
    "knowledge_engine_view": (
        "schema_version",
        "space_id",
        "view_kind",
        "name",
        "revision",
        "target_ids",
        "definition",
        "view_state",
        "capabilities",
        "created_at",
        "updated_at",
    ),
    "knowledge_engine_source_revision": (
        "schema_version",
        "space_id",
        "document_id",
        "content_hash",
        "byte_size",
        "encoding",
        "newline",
        "observed_modified_ns",
        "adapter_version",
        "parser_version",
        "parse_status",
        "diagnostics",
        "observed_at",
        "created_at",
    ),
    "knowledge_engine_identity_map": (
        "schema_version",
        "legacy_kind",
        "legacy_id",
        "engine_kind",
        "engine_id",
        "source_revision_id",
        "claim_hash",
        "created_at",
    ),
    "knowledge_engine_projection_receipt": (
        "schema_version",
        "operation_id",
        "space_id",
        "document_id",
        "source_revision_id",
        "relative_locator",
        "input_hash",
        "output_hash",
        "adapter_version",
        "status",
        "error_code",
        "started_at",
        "completed_at",
    ),
    "knowledge_engine_backfill_checkpoint": (
        "schema_version",
        "space_id",
        "last_relative_locator",
        "last_source_hash",
        "status",
        "projected",
        "unchanged",
        "failed",
        "updated_at",
    ),
}

INDEXES = (
    "idx_ke_space_source",
    "idx_ke_document_locator",
    "idx_ke_document_native",
    "idx_ke_block_source",
    "idx_ke_relation_source_span",
    "idx_ke_task_block",
    "idx_ke_revision_hash",
    "idx_ke_identity_legacy",
    "idx_ke_receipt_operation",
    "idx_ke_checkpoint_space",
)


def test_migration_38_is_schemafull_and_idempotent():
    sql = UP.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL;" in sql
    definitions = [
        line.strip() for line in sql.splitlines() if line.strip().startswith("DEFINE ")
    ]
    assert definitions
    assert all("IF NOT EXISTS" in line for line in definitions)


def test_migration_38_matches_the_strict_shadow_schema_contract():
    sql = UP.read_text(encoding="utf-8")
    for table, fields in FIELDS.items():
        for field in fields:
            rendered_field = "`capabilities`" if field == "capabilities" else field
            assert (
                f"DEFINE FIELD IF NOT EXISTS {rendered_field} ON TABLE {table}" in sql
            )
    for index in INDEXES:
        assert f"DEFINE INDEX IF NOT EXISTS {index}" in sql
    for table in (
        "knowledge_engine_space",
        "knowledge_engine_document",
        "knowledge_engine_block",
        "knowledge_engine_task",
        "knowledge_engine_asset",
        "knowledge_engine_view",
    ):
        assert (
            f"DEFINE FIELD IF NOT EXISTS `capabilities` ON TABLE {table} "
            "TYPE array<string>"
        ) in sql
    assert "absolute_root" not in sql
    assert "canonical_bytes" not in sql


def test_migration_38_down_is_sticky_and_non_destructive():
    sql = DOWN.read_text(encoding="utf-8")
    assert "schema_preserved: true" in sql
    assert "REMOVE TABLE" not in sql
    assert "DELETE " not in sql


def test_migration_discovery_includes_unified_engine_38():
    ups, downs = AsyncMigrationManager._discover_migrations()
    assert ups[37].version == 38
    assert "knowledge_engine_document" in ups[37].sql
    assert downs[37] is not None
    assert "schema_preserved: true" in downs[37].sql
