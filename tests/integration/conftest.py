"""v0.7.129 — pytest fixtures for the real-SurrealDB integration suite.

Design goals (in priority order):

  1. **Safe by default.** If `SURREAL_INTEGRATION` is unset, EVERY test
     under `tests/integration/` is skipped at collection time — no
     accidental connections from a normal `uv run pytest` run.

  2. **Isolated from the developer's working namespace.** We never run
     against `SURREAL_NAMESPACE=open_notebook` (the real app data).
     Instead we mint a throwaway namespace `onp_test_<short-uuid>` per
     pytest session, patch the env vars to point at it, run migrations
     against it, and `REMOVE NAMESPACE` on teardown so the SurrealDB
     volume stays clean across runs.

  3. **No new fixtures in the hot path.** The fixture sets env vars
     and relies on the same `deeper_notebook.database.repository` pool
     the production code uses. That way every SurrealQL regression
     these tests catch is one the production code can hit too.

Connection params (read from env, with sensible local-dev defaults):

  * `SURREAL_URL`       defaults to `ws://localhost:8000/rpc`
  * `SURREAL_USER`      defaults to `root`
  * `SURREAL_PASSWORD`  defaults to `root`

Override any of these if your local SurrealDB uses different creds.
"""

from __future__ import annotations

import copy
import os
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
import pytest_asyncio
from surrealdb import AsyncSurreal  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Collection-time skip gate
#
# Without this, a developer running `uv run pytest` with the integration
# suite on disk but no DB available would burn ~30 s of timeouts before
# bailing out. The pytest_collection_modifyitems hook skips every item
# under this directory BEFORE the event loop starts — same UX as the
# `pytest -m "not integration_surreal"` they'd otherwise have to type.
# ---------------------------------------------------------------------------

_INTEGRATION_ENV = "SURREAL_INTEGRATION"


def _integration_enabled() -> bool:
    return os.environ.get(_INTEGRATION_ENV, "").lower() in {"1", "true", "yes", "on"}


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    """Skip every test in this directory unless SURREAL_INTEGRATION=1.

    We attach a single skip marker rather than deselecting items so the
    skip reason shows up in the pytest summary (helpful when a CI run
    is supposed to be running these and isn't).
    """
    if _integration_enabled():
        return
    skip_marker = pytest.mark.skip(
        reason=(
            f"set {_INTEGRATION_ENV}=1 (and start SurrealDB via `make database`) "
            "to run real-SurrealDB integration tests"
        )
    )
    for item in items:
        # Only mark items that actually live under tests/integration/. This
        # is defensive — pytest's rootdir + this conftest scope means the
        # function is only ever called with items under this dir, but if
        # someone moves the conftest we don't want it silently skipping
        # other tests.
        if "tests/integration" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Connection helpers — kept private so the only public surface is the
# `surreal_db` fixture below.
# ---------------------------------------------------------------------------


def _resolve_url() -> str:
    """Mirror deeper_notebook.database.repository.get_database_url() defaults
    for the integration suite. We don't import that function directly
    because it has side effects on first call (and we want tests to be
    able to override SURREAL_URL via env before the repo module touches
    the pool)."""
    url = os.environ.get("SURREAL_URL")
    if url:
        return url
    return "ws://localhost:8000/rpc"


def _resolve_creds() -> tuple[str, str]:
    user = os.environ.get("SURREAL_USER", "root")
    password = (
        os.environ.get("SURREAL_PASSWORD") or os.environ.get("SURREAL_PASS") or "root"
    )
    return user, password


# ---------------------------------------------------------------------------
# Session-scoped namespace fixture
#
# Strategy:
#   1. Mint a per-session namespace + database name. Using BOTH a unique
#      namespace AND a unique database is belt-and-suspenders — REMOVE
#      NAMESPACE on teardown wipes everything inside regardless, but if
#      teardown fails (kill -9, network blip), the next run still gets
#      a fresh DB instead of inheriting half-migrated state.
#   2. Patch SURREAL_NAMESPACE / SURREAL_DATABASE in os.environ BEFORE
#      importing anything that touches the repo pool, so the pool's
#      first connection (lazy) uses the test namespace.
#   3. Run AsyncMigrationManager.run_migration_up() — same path as the
#      production API startup. This is what catches schema-ordering
#      regressions that pure SurrealQL-string unit tests can't.
#   4. Yield.
#   5. Teardown: close the repo pool, then connect as root and REMOVE
#      NAMESPACE <ns> to nuke every record/edge/migration history.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def surreal_db() -> AsyncIterator[dict[str, Any]]:
    """Bring up a throwaway namespace and run migrations against it.

    Yields a dict with the connection metadata so tests that need to
    open a side-channel connection (e.g. to verify edge-table contents
    directly) can do so without re-parsing env vars.
    """
    if not _integration_enabled():
        # Belt-and-suspenders — the collection hook above should have
        # already skipped, but a `pytest tests/integration/foo.py::bar`
        # invocation that bypasses collection-level modifications could
        # still reach here. Skip loudly rather than try to connect.
        pytest.skip(f"{_INTEGRATION_ENV} not set")

    short = uuid.uuid4().hex[:8]
    ns = f"onp_test_{short}"
    db = f"onp_test_{short}"

    url = _resolve_url()
    user, password = _resolve_creds()

    # Patch env BEFORE importing repo / migration modules so their first
    # use of os.environ sees our throwaway namespace, not whatever the
    # developer has set in `.env`.
    # v0.7.129 — also explicitly clear the connection pool in case the
    # repo module was already imported by some upstream conftest. The
    # pool caches connections that have already called `USE NS/DB`, so
    # without a reset they'd target the wrong namespace.
    old_env = {
        k: os.environ.get(k)
        for k in (
            "SURREAL_URL",
            "SURREAL_USER",
            "SURREAL_PASSWORD",
            "SURREAL_NAMESPACE",
            "SURREAL_DATABASE",
        )
    }
    os.environ["SURREAL_URL"] = url
    os.environ["SURREAL_USER"] = user
    os.environ["SURREAL_PASSWORD"] = password
    os.environ["SURREAL_NAMESPACE"] = ns
    os.environ["SURREAL_DATABASE"] = db

    # Import here, after env is patched, so the pool's lazy init reads
    # the test namespace on first acquire.
    from deeper_notebook.database import repository as repo_mod
    from deeper_notebook.database.async_migrate import AsyncMigrationManager

    await repo_mod.close_pool()  # idempotent if not yet initialized

    # Verify connectivity with a direct connection BEFORE migrations
    # run — a clear "couldn't reach SurrealDB" error is much more
    # actionable than a half-migrated namespace and a confusing query
    # failure later.
    probe = AsyncSurreal(url)
    try:
        await probe.signin({"username": user, "password": password})
        # Bootstrap the namespace + database. SurrealDB auto-creates
        # them on first `USE` with root creds, but doing it explicitly
        # surfaces auth/permission errors here, not deep inside a
        # migration query.
        await probe.use(ns, db)
        # Touch a no-op query to make sure auth landed.
        await probe.query("INFO FOR DB;")
    finally:
        try:
            await probe.close()
        except Exception:
            pass

    # Run all forward migrations against the fresh namespace.
    manager = AsyncMigrationManager()
    await manager.run_migration_up()
    # pytest-asyncio runs the session fixture and each test fixture on
    # different event loops by default. The production pool is correctly
    # loop-bound, so discard the migration loop's pool before test queries.
    await repo_mod.close_pool()

    meta = {
        "url": url,
        "user": user,
        "password": password,
        "namespace": ns,
        "database": db,
    }

    try:
        yield meta
    finally:
        # Teardown order matters:
        #   1. Drain the production pool so no in-flight queries hold
        #      a reference to the namespace we're about to nuke.
        #   2. Open a fresh root-level connection and REMOVE NAMESPACE.
        #      (REMOVE NAMESPACE cascades to every database / table /
        #      record / edge inside, so we don't have to enumerate.)
        #   3. Restore the original env vars so subsequent test files
        #      in the same session (if any) start from a clean slate.
        try:
            await repo_mod.close_pool()
        except Exception:
            pass

        cleanup = AsyncSurreal(url)
        try:
            await cleanup.signin({"username": user, "password": password})
            # REMOVE NAMESPACE must run at root scope (no USE first),
            # so we don't `await cleanup.use(...)` here.
            await cleanup.query(f"REMOVE NAMESPACE IF EXISTS {ns};")
        except Exception:
            # We never want a teardown failure to mask a real test
            # failure. Log and move on — the next session's per-uuid
            # namespace name means leftover state can't poison it.
            pass
        finally:
            try:
                await cleanup.close()
            except Exception:
                pass

        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# v0.7.131 — Tables we must NEVER truncate between tests, even though
# they live in the test namespace. `_sbl_migrations` tracks which
# migrations have been applied; wiping it would force the migration
# runner to re-execute on the next test (slow, and could fail if the
# schema is already in place). Any other underscore-prefixed table is
# treated as a SurrealDB system / internal table.
_PROTECTED_TABLE_PREFIXES = ("_",)
_PROTECTED_TABLE_NAMES = frozenset(
    {
        "_sbl_migrations",  # explicit guard even though the prefix catches it
    }
)
_TABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


async def _discover_tables() -> list[str]:
    """v0.7.131 — Query SurrealDB's INFO FOR DB to discover the live
    table set. Replaces the previous hardcoded 7-element list, which
    silently went stale every time a migration added a new domain
    table.

    Returns the list of non-system table names. Edge tables (reference,
    artifact, refers_to) show up here alongside node tables; DELETE on
    them works the same way.
    """
    from deeper_notebook.database.repository import repo_query

    rows = await repo_query("INFO FOR DB;")
    # SurrealDB's INFO FOR DB returns a dict-shaped result. The exact
    # shape varies slightly across versions, so we navigate it
    # defensively. v2 form:
    #   [{"tables": {"notebook": "...", "source": "...", ...}, ...}]
    # Older forms returned a top-level "tb" dict. Accept either.
    if not rows:
        return []
    head = rows[0] if isinstance(rows, list) else rows
    tables_section = head.get("tables") or head.get("tb") or {}
    discovered = list(tables_section.keys())

    # Apply the deny-list. We do this AFTER discovery so an unknown
    # underscore-prefixed table (a future migration adds, say,
    # `_audit_log`) is automatically excluded without requiring a
    # conftest edit.
    return [
        name
        for name in discovered
        if name not in _PROTECTED_TABLE_NAMES
        and not any(name.startswith(p) for p in _PROTECTED_TABLE_PREFIXES)
    ]


def _query_table_name(table: str) -> str:
    """Validate a schema-discovered table before using it as a query descriptor."""
    if not _TABLE_NAME.fullmatch(table):
        raise AssertionError(f"unsafe table name from INFO FOR DB: {table!r}")
    return table


async def _snapshot_table_data() -> dict[str, list[dict[str, Any]]]:
    """Capture raw rows so RecordID values survive failed-down recovery exactly."""
    data, _ = await _snapshot_rewind_state()
    return data


def _info_mapping(result: Any, description: str) -> dict[str, Any]:
    """Return one INFO mapping, rejecting an unexpected driver result shape."""
    if isinstance(result, list):
        if len(result) != 1:
            raise AssertionError(
                f"unexpected {description} result count: {len(result)}"
            )
        result = result[0]
    if not isinstance(result, dict):
        raise AssertionError(f"unexpected {description} result: {result!r}")
    return result


def _definition_strings(
    table: str, table_info: dict[str, Any], section: str
) -> tuple[str, ...]:
    """Extract normalized DDL strings from one INFO FOR TABLE section."""
    definitions = table_info.get(section, {})
    if not isinstance(definitions, dict):
        raise AssertionError(
            f"unexpected {section} definitions for table {table!r}: {definitions!r}"
        )
    if not all(isinstance(definition, str) for definition in definitions.values()):
        raise AssertionError(f"non-string {section} definition for table {table!r}")
    return tuple(definitions[name] for name in sorted(definitions))


async def _snapshot_rewind_state() -> tuple[
    dict[str, list[dict[str, Any]]], dict[str, dict[str, str | tuple[str, ...]]]
]:
    """Capture exact user rows plus the DDL needed to recreate their tables.

    Raw driver values are intentional: serializing through ``repo_query``
    would turn RecordIDs into strings and lose graph/reference fidelity.
    """
    from deeper_notebook.database.repository import db_connection

    snapshot: dict[str, list[dict[str, Any]]] = {}
    definitions: dict[str, dict[str, str | tuple[str, ...]]] = {}
    async with db_connection() as connection:
        database_info = _info_mapping(
            await connection.query("INFO FOR DB;"), "INFO FOR DB"
        )
        table_definitions = database_info.get("tables") or database_info.get("tb")
        if not isinstance(table_definitions, dict):
            raise AssertionError(
                f"unexpected INFO FOR DB table definitions: {table_definitions!r}"
            )
        tables = sorted(
            table
            for table in table_definitions
            if table not in _PROTECTED_TABLE_NAMES
            and not any(
                table.startswith(prefix) for prefix in _PROTECTED_TABLE_PREFIXES
            )
        )
        for table in tables:
            safe_table = _query_table_name(table)
            table_definition = table_definitions[safe_table]
            if not isinstance(table_definition, str):
                raise AssertionError(
                    f"non-string table definition for {safe_table!r}: {table_definition!r}"
                )
            rows = await connection.query(f"SELECT * FROM {safe_table} ORDER BY id;")
            if not isinstance(rows, list) or not all(
                isinstance(row, dict) for row in rows
            ):
                raise AssertionError(
                    f"unexpected row snapshot for table {safe_table!r}"
                )
            table_info = _info_mapping(
                await connection.query(f"INFO FOR TABLE {safe_table};"),
                f"INFO FOR TABLE {safe_table}",
            )
            unsupported = {
                section: table_info[section]
                for section in ("lives", "tables")
                if table_info.get(section)
            }
            if unsupported:
                raise AssertionError(
                    f"cannot exactly restore unsupported table metadata for "
                    f"{safe_table!r}: {unsupported!r}"
                )
            snapshot[safe_table] = copy.deepcopy(rows)
            definitions[safe_table] = {
                "table": table_definition,
                "fields": _definition_strings(safe_table, table_info, "fields"),
                "indexes": _definition_strings(safe_table, table_info, "indexes"),
                "events": _definition_strings(safe_table, table_info, "events"),
            }
    return snapshot, definitions


def _table_overwrite_definition(table: str, definition: str) -> str:
    """Turn INFO's normalized table DDL into an explicit replacement DDL."""
    safe_table = _query_table_name(table)
    prefix = f"DEFINE TABLE {safe_table} "
    if not definition.startswith(prefix):
        raise AssertionError(
            f"unexpected INFO FOR DB definition for table {safe_table!r}: {definition!r}"
        )
    return f"DEFINE TABLE OVERWRITE {safe_table} {definition.removeprefix(prefix)}"


async def _restore_table_data(
    snapshot: dict[str, list[dict[str, Any]]],
    definitions: dict[str, dict[str, str | tuple[str, ...]]],
) -> None:
    """Restore rows exactly, without active VALUE clauses rewriting them.

    A direct DELETE/CREATE under the recovered schema can change fields with
    ``VALUE`` expressions (notably ``updated = time::now()``). Recreate every
    validated user table SCHEMALESS, restore raw RecordIDs and payloads, then
    apply its original captured DDL with explicit table overwrite semantics.
    """
    from deeper_notebook.database.repository import db_connection

    if set(snapshot) != set(definitions):
        raise AssertionError("row snapshot and table definitions disagree")

    tables = sorted(snapshot)
    statements = ["BEGIN TRANSACTION;"]
    variables: dict[str, Any] = {}
    record_index = 0
    for table in tables:
        for row in snapshot[table]:
            record = row.get("id")
            if record is None:
                raise AssertionError(f"snapshot row in {table!r} has no id")
            record_key = f"record_{record_index}"
            payload_key = f"payload_{record_index}"
            variables[record_key] = record
            variables[payload_key] = {
                key: value for key, value in row.items() if key != "id"
            }
            statements.append(f"CREATE ${record_key} CONTENT ${payload_key};")
            record_index += 1
    statements.append("COMMIT TRANSACTION;")

    async with db_connection() as connection:
        for table in tables:
            await connection.query(f"REMOVE TABLE {_query_table_name(table)};")
        for table in tables:
            await connection.query(
                f"DEFINE TABLE {_query_table_name(table)} SCHEMALESS;"
            )
        if record_index:
            await connection.query("\n".join(statements), variables)
        for table in tables:
            table_definitions = definitions[table]
            table_definition = table_definitions["table"]
            if not isinstance(table_definition, str):
                raise AssertionError(f"missing table definition for {table!r}")
            await connection.query(_table_overwrite_definition(table, table_definition))
            for section in ("fields", "indexes", "events"):
                section_definitions = table_definitions[section]
                if not isinstance(section_definitions, tuple):
                    raise AssertionError(
                        f"missing {section} definitions for table {table!r}"
                    )
                for definition in section_definitions:
                    await connection.query(definition)


@pytest_asyncio.fixture
async def clean_namespace(surreal_db: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """Per-test wipe of all user-data tables.

    The session fixture sets up the schema once (expensive — runs all
    forward migrations). This fixture keeps that schema but truncates
    the domain tables between tests so test_A's leftover notebook
    doesn't show up in test_B's `SELECT * FROM notebook`.

    v0.7.131 — table discovery is now dynamic via `INFO FOR DB`. The
    previous hardcoded 7-element list silently went stale whenever a
    migration added a new domain table (Area for Review #17). Edge
    tables (reference, artifact, refers_to) are discovered alongside
    node tables; DELETE works on both. Migration tracking tables
    (`_sbl_migrations` and any other underscore-prefixed system
    table) are explicitly protected — wiping them would force a
    migration re-run on the next test.
    """
    from deeper_notebook.database.repository import repo_query

    try:
        tables = await _discover_tables()
    except Exception:
        # If INFO FOR DB fails for any reason, fall back to a small
        # known-good list. Better degraded coverage than no isolation
        # at all. Don't crash the suite — the per-test test logic
        # will catch missing-isolation bugs faster than a broken
        # fixture would.
        tables = [
            "reference",
            "artifact",
            "refers_to",
            "source",
            "note",
            "notebook",
            "chat_session",
        ]

    for tbl in tables:
        try:
            await repo_query(f"DELETE {tbl};")
        except Exception:
            # Table may not exist yet (migrations are forward-only
            # and a test could be running before the table is added).
            # Silent skip — the test will fail on its own if the
            # table really is required.
            pass

    try:
        yield surreal_db
    finally:
        # Do not let a WebSocket or asyncio.Queue created for this test's loop
        # leak into the next test's loop.
        from deeper_notebook.database import repository as repo_mod

        await repo_mod.close_pool()


@pytest_asyncio.fixture
async def migration_rewind(
    clean_namespace: dict[str, Any],
) -> AsyncIterator[Callable[[int], Awaitable[int]]]:
    """Rewind migration tests through the canonical runner and restore its head.

    Historical migration tests need exact schema versions, but the test-session
    head advances whenever a new migration is added.  Record the real head
    before every rewind, use the production runner for each down migration,
    and restore that recorded head during fixture teardown even if the test
    body raises.
    """
    from deeper_notebook.database.async_migrate import AsyncMigrationManager

    async def schema_snapshot() -> dict[str, Any]:
        from deeper_notebook.database.repository import repo_query

        rows = await repo_query("INFO FOR DB;")
        database = rows[0] if isinstance(rows, list) else rows
        tables = database.get("tables") or database.get("tb") or {}
        table_info = {}
        for table in sorted(tables):
            rows = await repo_query(f"INFO FOR TABLE {table};")
            table_info[table] = rows[0] if isinstance(rows, list) else rows
        return {
            "database": _freeze_schema_snapshot(database),
            "tables": _freeze_schema_snapshot(table_info),
        }

    rewinds: list[dict[str, Any]] = []

    async def rewind_to(target_version: int) -> int:
        manager = AsyncMigrationManager()
        original_head = await manager.get_current_version()
        if not 0 <= target_version <= original_head:
            raise AssertionError(
                f"cannot rewind migration head {original_head} to {target_version}"
            )

        # Register before mutating state so teardown restores a partially
        # rewound database if a down migration itself raises. The snapshot is
        # schema authority, not only a migration-head proxy: a down migration
        # can alter DDL before it reaches lower_version().
        original_data, original_table_definitions = await _snapshot_rewind_state()
        rewind = {
            "manager": manager,
            "original_head": original_head,
            "original_schema": await schema_snapshot(),
            "original_data": original_data,
            "original_table_definitions": original_table_definitions,
            "failed_down_version": None,
        }
        rewinds.append(rewind)
        while await manager.get_current_version() > target_version:
            current_version = await manager.get_current_version()
            try:
                await manager.runner.run_one_down()
            except Exception:
                rewind["failed_down_version"] = current_version
                raise

        assert await manager.get_current_version() == target_version
        return original_head

    try:
        yield rewind_to
    finally:
        for rewind in reversed(rewinds):
            manager = rewind["manager"]
            original_head = rewind["original_head"]
            failed_down_version = rewind["failed_down_version"]
            if failed_down_version is not None:
                from deeper_notebook.database.repository import repo_query

                # A down migration can damage DDL before it reaches
                # lower_version(). Its tracker row is then still present, so a
                # normal forward run would skip that migration. Start recovery
                # by invalidating the attempted and later migrations, then
                # replay them exactly once. Running normally first would replay
                # successful earlier downs a second time, duplicating data from
                # migrations such as v47.
                for version in range(failed_down_version, original_head + 1):
                    await repo_query(
                        "DELETE type::thing('_sbl_migrations', $version);",
                        {"version": version},
                    )
                await manager.run_migration_up()
            else:
                await manager.run_migration_up()
            assert await manager.get_current_version() == original_head
            assert await schema_snapshot() == rewind["original_schema"]
            if failed_down_version is not None:
                await _restore_table_data(
                    rewind["original_data"], rewind["original_table_definitions"]
                )
                assert await _snapshot_table_data() == rewind["original_data"]
                assert await schema_snapshot() == rewind["original_schema"]


def _freeze_schema_snapshot(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _freeze_schema_snapshot(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_freeze_schema_snapshot(item) for item in value]
    return value
