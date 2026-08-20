"""
Async migration system for SurrealDB using the official Python client.
Based on patterns from sblpy migration system.
"""

from pathlib import Path
from typing import List

from loguru import logger

from .migration_33_vault_backfill import run_python_migration_hook
from .repository import db_connection, repo_query


class AsyncMigration:
    """
    Handles individual migration operations with async support.
    """

    def __init__(self, sql: str, *, version: int | None = None) -> None:
        """Initialize migration with SQL content."""
        self.sql = sql
        self.version = version

    @classmethod
    def from_file(cls, file_path: str) -> "AsyncMigration":
        """Create migration from SQL file."""
        with open(file_path, "r", encoding="utf-8") as file:
            raw_content = file.read()
            # Clean up SQL content
            lines = []
            for line in raw_content.split("\n"):
                line = line.strip()
                if line and not line.startswith("--"):
                    lines.append(line)
            sql = " ".join(lines)
            version = int(Path(file_path).stem.split("_", maxsplit=1)[0])
            return cls(sql, version=version)

    async def run(self, bump: bool = True) -> None:
        """Run the migration."""
        try:
            async with db_connection() as connection:
                await connection.query(self.sql)
                if bump and self.version is not None:
                    await run_python_migration_hook(self.version, connection)

            if bump:
                await bump_version()
            else:
                await lower_version()

        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            raise


class AsyncMigrationRunner:
    """
    Handles running multiple migrations in sequence.
    """

    def __init__(
        self,
        up_migrations: list[AsyncMigration],
        down_migrations: list[AsyncMigration],
    ) -> None:
        """Initialize runner with migration lists."""
        self.up_migrations = up_migrations
        self.down_migrations = down_migrations

    async def run_all(self) -> None:
        """Run all pending up migrations."""
        current_version = await get_latest_version()

        for i in range(current_version, len(self.up_migrations)):
            logger.info(f"Running migration {i + 1}")
            await self.up_migrations[i].run(bump=True)

    async def run_one_up(self) -> None:
        """Run one up migration."""
        current_version = await get_latest_version()

        if current_version < len(self.up_migrations):
            logger.info(f"Running migration {current_version + 1}")
            await self.up_migrations[current_version].run(bump=True)

    async def run_one_down(self) -> None:
        """Run one down migration.

        v0.6.12 — down_migrations is now indexed parallel to up_migrations
        with None for ups that lack a matching down file. Previously this
        method could IndexError or apply the wrong down by accident.
        """
        current_version = await get_latest_version()

        if current_version <= 0:
            return
        idx = current_version - 1
        if idx >= len(self.down_migrations):
            raise RuntimeError(
                f"Cannot rollback: down list has {len(self.down_migrations)} "
                f"entries but current_version is {current_version}."
            )
        down = self.down_migrations[idx]
        if down is None:
            raise RuntimeError(
                f"Cannot rollback migration {current_version}: no matching "
                f"{current_version}_down.surrealql in the migrations directory."
            )
        logger.info(f"Rolling back migration {current_version}")
        await down.run(bump=False)


class AsyncMigrationManager:
    """
    Main migration manager with async support.
    """

    # P2-HIGH-01 audit fix: auto-discover migrations instead of the hard-coded
    # 1..N list. Each new migration just drops in as <n>.surrealql + optional
    # <n>_down.surrealql — no need to remember to also edit this file.
    @staticmethod
    def _discover_migrations(
        mig_dir: Path | None = None,
    ) -> tuple[list[AsyncMigration], list[AsyncMigration]]:
        """Scan the migrations directory and return parallel (ups, downs) lists.

        v0.6.12 changes:
          1. Enforce contiguous numbering from 1..N. A missing `4.surrealql`
             between `3` and `5` used to silently produce `[m1, m2, m3, m5]`
             with len=4 — so the DB would record "version 4" while the SQL
             actually run was migration #5. Then if `4.surrealql` got restored
             later, the manager would see 5 files, compute `needs_migration =
             current(4) < total(5)`, run index 4 (= the original m5 again),
             and either crash with "already exists" or silently re-apply.
          2. Build a downs list with the SAME LENGTH as ups (placeholders for
             ups that lack a matching down). Previously `run_one_down` could
             IndexError on a partial down set.
        """
        import re
        from pathlib import Path

        # Resolve migrations from the canonical installed package. This works
        # in development and in the frozen app without depending on process cwd.
        if mig_dir is None:
            mig_dir = Path(__file__).resolve().parent / "migrations"
        files = sorted(
            (p for p in mig_dir.iterdir() if p.suffix == ".surrealql"),
            key=lambda p: (
                int(re.match(r"(\d+)", p.stem).group(1))  # type: ignore[union-attr]
                if re.match(r"(\d+)", p.stem)
                else 999999
            ),
        )
        ups_by_n: dict[int, AsyncMigration] = {}
        downs_by_n: dict[int, AsyncMigration] = {}
        for f in files:
            m = re.match(r"(\d+)(_down)?$", f.stem)
            if not m:
                continue
            n = int(m.group(1))
            if m.group(2):
                downs_by_n[n] = AsyncMigration.from_file(str(f))
            else:
                ups_by_n[n] = AsyncMigration.from_file(str(f))

        if not ups_by_n:
            return [], []

        # Enforce contiguous 1..N — surfaces missing migration files LOUDLY.
        max_n = max(ups_by_n)
        missing = [n for n in range(1, max_n + 1) if n not in ups_by_n]
        if missing:
            raise RuntimeError(
                f"Migration directory {mig_dir} has gaps: missing "
                f"{', '.join(f'{n}.surrealql' for n in missing)}. "
                f"Migration numbering must be contiguous from 1; refusing to "
                f"run partial migration set."
            )

        # Parallel lists indexed 0..N-1 corresponding to migration versions 1..N.
        # Downs use a placeholder (the same up migration with bump=False sense
        # is wrong, so use None and let run_one_down check) when a matching
        # down file is absent. `run_one_down` now guards on missing entries.
        ups = [ups_by_n[n] for n in range(1, max_n + 1)]
        downs = [downs_by_n.get(n) for n in range(1, max_n + 1)]
        return ups, downs  # type: ignore[return-value]

    def __init__(self):
        """Initialize migration manager — auto-discovers migrations from
        deeper_notebook/database/migrations/*.surrealql via _discover_migrations.
        """
        self.up_migrations, self.down_migrations = self._discover_migrations()
        self.runner = AsyncMigrationRunner(
            up_migrations=self.up_migrations,
            down_migrations=self.down_migrations,
        )

    async def get_current_version(self) -> int:
        """Get current database version."""
        return await get_latest_version()

    async def needs_migration(self) -> bool:
        """Check if migration is needed."""
        current_version = await self.get_current_version()
        return current_version < len(self.up_migrations)

    async def run_migration_up(self):
        """Run all pending migrations."""
        current_version = await self.get_current_version()
        logger.info(f"Current version before migration: {current_version}")

        if await self.needs_migration():
            try:
                await self.runner.run_all()
                new_version = await self.get_current_version()
                logger.info(f"Migration successful. New version: {new_version}")
            except Exception as e:
                logger.error(f"Migration failed: {str(e)}")
                raise
        else:
            logger.info("Database is already at the latest version")


# Database version management functions
async def get_latest_version() -> int:
    """Get the latest version from the migrations table."""
    try:
        versions = await get_all_versions()
        if not versions:
            return 0
        return max(version["version"] for version in versions)
    except Exception:
        # If migrations table doesn't exist, we're at version 0
        return 0


async def get_all_versions() -> list[dict]:
    """Get all versions from the migrations table."""
    try:
        result = await repo_query("SELECT * FROM _sbl_migrations ORDER BY version;")
        return result
    except Exception as exc:
        # v0.8.28 — classify like the v0.8.19 / v0.8.27 silent-swallow
        # fixes. Pre-v0.8.28 this just swallowed everything with a
        # comment claiming "table doesn't exist". On a fresh install
        # that's correct; but a connection drop, auth failure, or
        # SurrealDB schema bug all hit the same path and the migration
        # runner would think there are no versions — potentially
        # re-running every migration. DEBUG for the table-missing
        # bootstrap case; WARNING for anything else.
        msg = str(exc)
        if "Table missing" in msg or "table does not exist" in msg:
            logger.debug(
                "get_all_versions: _sbl_migrations table missing (bootstrap case): {}",
                exc,
            )
        else:
            logger.warning(
                "get_all_versions: unexpected error reading "
                "_sbl_migrations — treating as version 0, which may "
                "cause already-applied migrations to re-run. error={}",
                exc,
            )
        return []


async def bump_version() -> None:
    """Bump the version by adding a new entry to migrations table."""
    current_version = await get_latest_version()
    new_version = current_version + 1

    await repo_query(
        "CREATE type::thing('_sbl_migrations', $version) SET version = $version, applied_at = time::now();",
        {"version": new_version},
    )


async def lower_version() -> None:
    """Lower the version by removing the latest entry from migrations table."""
    current_version = await get_latest_version()
    if current_version > 0:
        await repo_query(
            "DELETE type::thing('_sbl_migrations', $version);",
            {"version": current_version},
        )
