"""One-shot legacy-edge deduplicator.

v0.7.85 — closes deferral #1 from the v0.7.81 plan document. Earlier
versions of Open Notebook (and the legacy ProviderConfig path) could
create duplicate `reference` / `artifact` edges between the same
source/note and notebook because the idempotency check was either
inverted (v0.7.60 fix) or absent (v0.7.73 fix). Existing databases
created before those fixes carry the leftover duplicates; new edges
created by current code are deduped at write time.

This module runs once per API startup, finds duplicate (in, out) edge
pairs on the two affected tables, keeps one canonical edge per pair
(the lexicographically-smallest id, for determinism), and deletes the
rest. Idempotent — on a clean database it executes one SELECT per
table and exits without writing.

Called from api/main.py lifespan AFTER `AsyncMigrationManager.run_migration_up`
completes, so the schema is guaranteed to be at the latest version
before we touch any data. Non-fatal — if it fails, the API still
boots and the existing v0.7.60/v0.7.73 fixes continue to prevent new
duplicates from forming. The next startup will retry the dedup.
"""

from __future__ import annotations

from loguru import logger

from deeper_notebook.database.repository import repo_query

# Edge tables that the dedup applies to. Each is the same edge shape
# (in, out, id) that the v0.7.60/v0.7.73 fixes guard.
_EDGE_TABLES = ("reference", "artifact")


async def _find_duplicate_groups(table: str) -> list[dict]:
    """Return groups with >1 edge sharing the same (in, out) pair.

    Returns: [{"in": <record>, "out": <record>, "ids": [<record>, ...]}, ...]
    Empty list on a clean table.
    """
    rows = await repo_query(
        f"""
        SELECT in, out, array::group(id) AS ids
        FROM {table}
        GROUP BY in, out
        """  # nosec B608
    )
    if not rows:
        return []
    return [
        {"in": r.get("in"), "out": r.get("out"), "ids": r.get("ids") or []}
        for r in rows
        if isinstance(r, dict) and len(r.get("ids") or []) > 1
    ]


async def _dedupe_table(table: str) -> int:
    """Dedup one table. Returns the number of edges deleted.

    v0.8.99 — `table` is interpolated into SurrealQL by
    `_find_duplicate_groups`, whose B608 suppression asserts the identifier is
    whitelisted. The only caller iterates `_EDGE_TABLES`, so that was true by
    convention; validate here so it is true by construction and the tag stops
    being a promise. Mirrors the guard in `evaluation.repository.latest_run`.
    """
    if table not in _EDGE_TABLES:
        raise ValueError(f"unknown edge table: {table!r}")
    groups = await _find_duplicate_groups(table)
    if not groups:
        return 0
    deleted = 0
    for g in groups:
        ids = g.get("ids") or []
        if len(ids) <= 1:
            continue
        # Deterministically pick the canonical edge: lexicographically
        # smallest stringified id. SurrealDB RecordID stringifies
        # consistently, so re-runs (if the first attempt partially
        # succeeded) keep the same survivor.
        ids_sorted = sorted(ids, key=lambda r: str(r))
        extras = ids_sorted[1:]
        for edge_id in extras:
            try:
                await repo_query(
                    "DELETE $edge_id",
                    {"edge_id": edge_id},
                )
                deleted += 1
            except Exception as exc:
                # Best-effort: a single failed delete shouldn't abort
                # the rest of the cleanup.
                logger.warning(
                    "dedup_edges: failed to delete duplicate {} edge {}: {}",
                    table,
                    edge_id,
                    exc,
                )
    return deleted


async def dedupe_legacy_edges() -> dict[str, int]:
    """Run the full dedup sweep across all affected edge tables.

    Returns a {table_name: deleted_count} dict. All-zero on a clean
    database. Errors at the per-table level are caught and logged so
    one bad table doesn't block the other.
    """
    results: dict[str, int] = {}
    for table in _EDGE_TABLES:
        try:
            n = await _dedupe_table(table)
            results[table] = n
            if n > 0:
                logger.info(
                    "dedup_edges: removed {} duplicate {} edge(s) "
                    "(pre-v0.7.60/73 legacy data)",
                    n,
                    table,
                )
        except Exception as exc:
            logger.warning(
                "dedup_edges: {} table sweep failed (non-fatal, will retry "
                "next startup): {}",
                table,
                exc,
            )
            results[table] = 0
    return results
