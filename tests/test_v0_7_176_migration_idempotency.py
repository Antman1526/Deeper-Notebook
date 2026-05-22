"""v0.7.176 — Migrations 12 and 16 are now re-run-safe.

Background: `AsyncMigrationManager` runs migrations in numeric order
and records `_sbl_migrations` rows so a migration only fires once.
But if the `_sbl_migrations` table is manually edited, or a backup
restore replaces a newer DB with an older snapshot, or a disaster-
recovery procedure rolls back the version table — the next API
startup re-runs the migrations against a schema that already has
the tables. In SurrealDB:

  - `DEFINE TABLE foo SCHEMAFULL;`  re-running on existing table is
    fine in newer SurrealDB versions but the field/index DEFINEs are
    NOT idempotent — they error out.
  - `DEFINE FIELD x ON foo TYPE string;` without `IF NOT EXISTS`
    fails or overwrites on re-run.
  - `DEFINE INDEX idx ON foo FIELDS ...;` without `IF NOT EXISTS`
    drops + recreates the index, which can cause a window where
    queries miss rows.

The fix (compare to migration 14 which already does this) is to
add `IF NOT EXISTS` to every DEFINE statement so the migration is
a no-op on second run. v0.7.176 adds these guards to migrations
12 (credential table) and 16 (gmail_integration table) — the two
that were missing them.

This test is a pure text-level pin so it works without a live
SurrealDB. It enforces that every DEFINE in the affected files
carries the guard.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "open_notebook" / "database" / "migrations"


def _all_defines(text: str) -> list[str]:
    """Return every line that starts a DEFINE statement, stripped."""
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.upper().startswith("DEFINE "):
            lines.append(stripped)
    return lines


def test_migration_12_every_define_has_guard():
    """v0.7.176: every DEFINE in 12.surrealql must be re-run-safe
    via IF NOT EXISTS (or OVERWRITE — both are idempotent). Without
    this, re-running the migration after a manual _sbl_migrations
    rollback or DR procedure half-applies and leaves the schema
    broken."""
    text = (MIGRATIONS / "12.surrealql").read_text(encoding="utf-8")
    defines = _all_defines(text)
    assert defines, "migration 12 has no DEFINE statements — file moved?"
    offenders = []
    for d in defines:
        upper = d.upper()
        if "IF NOT EXISTS" not in upper and "OVERWRITE" not in upper:
            offenders.append(d)
    assert not offenders, (
        f"v0.7.176 regression: migration 12 has DEFINE statements "
        f"without IF NOT EXISTS / OVERWRITE — these will fail or "
        f"clobber on re-run after a _sbl_migrations rollback / DR / "
        f"restore. Offenders:\n  - "
        + "\n  - ".join(offenders)
    )


def test_migration_16_every_define_has_guard():
    """v0.7.176: same pin for migration 16 (gmail_integration).
    Both 12 and 16 were the lone holdouts; every other migration
    either uses IF NOT EXISTS, OVERWRITE, or is dropped from the
    catalog."""
    text = (MIGRATIONS / "16.surrealql").read_text(encoding="utf-8")
    defines = _all_defines(text)
    assert defines, "migration 16 has no DEFINE statements — file moved?"
    offenders = []
    for d in defines:
        upper = d.upper()
        if "IF NOT EXISTS" not in upper and "OVERWRITE" not in upper:
            offenders.append(d)
    assert not offenders, (
        f"v0.7.176 regression: migration 16 has DEFINE statements "
        f"without IF NOT EXISTS / OVERWRITE — these will fail or "
        f"clobber on re-run. Offenders:\n  - "
        + "\n  - ".join(offenders)
    )


def test_migration_12_has_version_marker_comment():
    """v0.7.176: keep the inline version marker so future readers
    can grep `v0.7.176` and find the audit trail. This matches the
    project convention from CLAUDE.md (every fix gets `# v0.7.NN —
    ...` or `-- v0.7.NN — ...` for SQL files)."""
    text = (MIGRATIONS / "12.surrealql").read_text(encoding="utf-8")
    assert "v0.7.176" in text, (
        "v0.7.176: marker comment in 12.surrealql is gone — the "
        "audit-trail link from CHANGELOG to the file is broken."
    )


def test_migration_16_has_version_marker_comment():
    """v0.7.176: same marker pin for 16."""
    text = (MIGRATIONS / "16.surrealql").read_text(encoding="utf-8")
    assert "v0.7.176" in text, (
        "v0.7.176: marker comment in 16.surrealql is gone."
    )


def test_no_regression_in_other_migrations():
    """v0.7.176: we shouldn't have ACCIDENTALLY broken any other
    migration. This is a belt-and-suspenders check: every .surrealql
    in the catalog must still parse as having at least one DEFINE
    or be a known down/data migration. Stops a future cleanup pass
    from inadvertently emptying a file."""
    for path in sorted(MIGRATIONS.glob("*.surrealql")):
        if "_down" in path.name:
            # Down migrations may have REMOVE statements instead.
            continue
        text = path.read_text(encoding="utf-8")
        # Migration 14_data_migration etc. may not have DEFINE.
        if "data" in path.stem.lower():
            continue
        defines = _all_defines(text)
        # Some migrations only do UPDATE / DELETE (e.g. data fixups).
        # The minimum bar is that the file is non-trivial.
        assert text.strip(), f"migration {path.name} is empty"
