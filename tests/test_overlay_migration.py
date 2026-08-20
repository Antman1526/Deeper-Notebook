from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/36.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/36_down.surrealql"
INDEX_REPAIR = ROOT / "deeper_notebook/database/migrations/37.surrealql"
INDEX_REPAIR_DOWN = ROOT / "deeper_notebook/database/migrations/37_down.surrealql"

TABLES = (
    "overlay_space",
    "overlay_note",
    "overlay_revision",
    "overlay_mutation_receipt",
)


def test_migration_36_is_schemafull_idempotent_and_authority_explicit():
    sql = UP.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL;" in sql
    assert "source_authority ON TABLE note" in sql
    assert "overlay_space_id ON TABLE note" in sql
    assert "overlay_note_id ON TABLE note" in sql
    assert "idx_overlay_daily" in sql
    assert "idx_overlay_path" in sql
    assert "idx_overlay_idempotency" in sql
    assert "overlay_note_id ON TABLE note_block" in sql
    assert (
        "DEFINE FIELD OVERWRITE vault_file_id ON TABLE note_block "
        "TYPE option<record<vault_file>>;"
    ) in sql
    defines = [
        line.strip()
        for line in sql.splitlines()
        if line.strip().upper().startswith("DEFINE ")
        and "DEFINE FIELD OVERWRITE vault_file_id" not in line
    ]
    assert defines
    assert all("IF NOT EXISTS" in line.upper() for line in defines)


def test_migration_36_block_uniqueness_is_scoped_to_projected_note():
    """External blocks retain NONE overlay IDs, so uniqueness cannot use that ID."""
    sql = UP.read_text(encoding="utf-8")

    assert (
        "DEFINE INDEX IF NOT EXISTS idx_note_block_overlay ON TABLE note_block "
        "COLUMNS note_id, parser_id UNIQUE;"
    ) in sql
    assert "COLUMNS overlay_note_id, parser_id UNIQUE;" not in sql


def test_migration_36_down_removes_only_overlay_schema():
    sql = DOWN.read_text(encoding="utf-8")
    for table in TABLES:
        assert f"REMOVE TABLE IF EXISTS {table};" in sql
    assert "REMOVE TABLE IF EXISTS note;" not in sql
    assert "REMOVE TABLE IF EXISTS vault_mount;" not in sql
    assert "REMOVE TABLE IF EXISTS vault_file;" not in sql
    assert "DELETE note_block WHERE overlay_note_id != NONE;" in sql
    assert "DELETE note WHERE overlay_note_id != NONE;" in sql
    assert "DELETE knowledge_task WHERE note_id IN $projected_note_ids;" in sql
    assert "DELETE note_link WHERE source_note_id IN $projected_note_ids" in sql
    assert (
        "DEFINE FIELD OVERWRITE vault_file_id ON TABLE note_block "
        "TYPE record<vault_file>;"
    ) in sql
    for field in ("source_authority", "overlay_space_id", "overlay_note_id"):
        assert f"REMOVE FIELD IF EXISTS {field} ON TABLE note;" in sql


def test_migration_37_removes_none_colliding_daily_index():
    sql = INDEX_REPAIR.read_text(encoding="utf-8")
    down_sql = INDEX_REPAIR_DOWN.read_text(encoding="utf-8")

    assert "REMOVE INDEX IF EXISTS idx_overlay_daily ON TABLE overlay_note;" in sql
    assert "DEFINE INDEX" not in sql
    assert "idx_overlay_path" not in sql
    assert "idx_overlay_daily" in down_sql
    assert "DEFINE INDEX" not in down_sql
    assert "repaired_index_restored: false" in down_sql
