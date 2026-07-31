from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UP = ROOT / "deeper_notebook/database/migrations/39.surrealql"
DOWN = ROOT / "deeper_notebook/database/migrations/39_down.surrealql"


def test_migration_39_defines_only_navigation_metadata_tables():
    sql = UP.read_text(encoding="utf-8")
    for table in (
        "knowledge_bookmark_folder",
        "knowledge_bookmark",
        "named_knowledge_workspace",
        "knowledge_navigation_operation_receipt",
    ):
        assert f"DEFINE TABLE IF NOT EXISTS {table} SCHEMAFULL;" in sql
    assert "absolute_root" not in sql
    assert "normalized_body" not in sql
    assert "canonical_bytes" not in sql


def test_migration_39_down_removes_only_navigation_metadata():
    sql = DOWN.read_text(encoding="utf-8")
    assert "REMOVE TABLE IF EXISTS knowledge_bookmark;" in sql
    assert "REMOVE TABLE IF EXISTS named_knowledge_workspace;" in sql
    assert "knowledge_engine_document" not in sql
    assert "overlay_note" not in sql
    assert "vault_file" not in sql
