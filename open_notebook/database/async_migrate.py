"""
Async migration system for SurrealDB using the official Python client.
Based on patterns from sblpy migration system.
"""

from typing import List

from loguru import logger

from .repository import db_connection, repo_query


class AsyncMigration:
    """
    Handles individual migration operations with async support.
    """

    def __init__(self, sql: str) -> None:
        """Initialize migration with SQL content."""
        self.sql = sql

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
            return cls(sql)

    async def run(self, bump: bool = True) -> None:
        """Run the migration."""
        try:
            async with db_connection() as connection:
                await connection.query(self.sql)

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
        up_migrations: List[AsyncMigration],
        down_migrations: List[AsyncMigration],
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
        """Run one down migration."""
        current_version = await get_latest_version()

        if current_version > 0:
            logger.info(f"Rolling back migration {current_version}")
            await self.down_migrations[current_version - 1].run(bump=False)


class AsyncMigrationManager:
    """
    Main migration manager with async support.
    """

    # P2-HIGH-01 audit fix: auto-discover migrations instead of the hard-coded
    # 1..N list. Each new migration just drops in as <n>.surrealql + optional
    # <n>_down.surrealql — no need to remember to also edit this file.
    @staticmethod
    def _discover_migrations() -> tuple[list[AsyncMigration], list[AsyncMigration]]:
        import re
        import os
        from pathlib import Path
        # Migration directory is relative to repo root (cwd is upstream_dir in
        # the frozen app, repo_root in dev — both produce the same relative
        # path since open_notebook/ lives at the same level either way).
        mig_dir = Path("open_notebook/database/migrations")
        files = sorted(
            (p for p in mig_dir.iterdir() if p.suffix == ".surrealql"),
            key=lambda p: int(re.match(r"(\d+)", p.stem).group(1))  # type: ignore[union-attr]
            if re.match(r"(\d+)", p.stem) else 999999,
        )
        ups: list[tuple[int, AsyncMigration]] = []
        downs_by_n: dict[int, AsyncMigration] = {}
        for f in files:
            m = re.match(r"(\d+)(_down)?$", f.stem)
            if not m:
                continue
            n = int(m.group(1))
            if m.group(2):
                downs_by_n[n] = AsyncMigration.from_file(str(f))
            else:
                ups.append((n, AsyncMigration.from_file(str(f))))
        # Up list must be contiguous from 1; pair each up with its down (skip
        # downs that have no matching up).
        ups.sort(key=lambda t: t[0])
        return [u for _, u in ups], [downs_by_n[n] for n, _ in ups if n in downs_by_n]

    def __init__(self):
        """Initialize migration manager — auto-discovers migrations from
        open_notebook/database/migrations/*.surrealql via _discover_migrations.
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


async def get_all_versions() -> List[dict]:
    """Get all versions from the migrations table."""
    try:
        result = await repo_query("SELECT * FROM _sbl_migrations ORDER BY version;")
        return result
    except Exception:
        # If table doesn't exist, return empty list
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
