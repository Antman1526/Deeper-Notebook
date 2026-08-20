"""Static contracts for the reversible Task 5 HNSW distance migration."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = REPOSITORY_ROOT / "deeper_notebook" / "database" / "migrations"
_INDEXES = (
    ("source_embedding", "source_embedding_hnsw"),
    ("source_insight", "source_insight_hnsw"),
    ("note", "note_hnsw"),
)


def _normalized(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split()).upper()


def _assert_rebuilt_with_distance(path: Path, distance: str) -> None:
    source = _normalized(path)
    for table, index in _INDEXES:
        assert (
            f"REMOVE INDEX IF EXISTS {index.upper()} ON TABLE {table.upper()};"
            in source
        )
        assert (
            f"DEFINE INDEX IF NOT EXISTS {index.upper()} ON {table.upper()} "
            f"FIELDS EMBEDDING HNSW DIMENSION 768 DIST {distance};"
        ) in source


def test_hnsw_distance_migration_rebuilds_all_cosine_candidate_indexes() -> None:
    _assert_rebuilt_with_distance(MIGRATIONS / "51.surrealql", "COSINE")


def test_hnsw_distance_migration_rollback_rebuilds_all_euclidean_indexes() -> None:
    _assert_rebuilt_with_distance(MIGRATIONS / "51_down.surrealql", "EUCLIDEAN")
