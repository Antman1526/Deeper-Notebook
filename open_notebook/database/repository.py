import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeVar, Union

from loguru import logger
from surrealdb import AsyncSurreal, RecordID  # type: ignore

T = TypeVar("T", Dict[str, Any], List[Dict[str, Any]])


# ---------------------------------------------------------------------------
# v0.7.18 — SurrealDB connection pool
#
# Before v0.7.18, every repo_query / repo_create / etc. opened a fresh
# AsyncSurreal WebSocket, performed SCRAM auth, selected namespace +
# database, ran one query, and closed. A single chat turn fans out
# dozens of repo_query calls through ContextBuilder; on a local
# SurrealDB instance this cumulative handshake overhead is 50-200 ms
# per chat turn that we just don't need to pay.
#
# The pool design:
#   - asyncio.Queue holds idle, pre-authenticated AsyncSurreal clients.
#   - On acquire: pop the queue; if empty AND we haven't hit the cap,
#     spin up a new connection (lazy growth). If empty AND at cap,
#     block on the queue.
#   - On release: put the client back. If the client raised mid-query,
#     mark it dead and let the pool create a fresh one next time.
#   - Disable via ONP_DB_POOL_DISABLED=1 for debugging or to fall back
#     to the old per-query behavior.
#   - Pool size via ONP_DB_POOL_SIZE (default 4). Local use rarely
#     needs more; the chat graph + background workers usually share
#     less than 4 concurrent connections.
# ---------------------------------------------------------------------------

_DB_POOL_SIZE_DEFAULT = 4
_DB_POOL_MIN = 1
_DB_POOL_MAX = 32


def _db_pool_size() -> int:
    raw = os.environ.get("ONP_DB_POOL_SIZE")
    if not raw:
        return _DB_POOL_SIZE_DEFAULT
    try:
        val = int(raw)
        if val < _DB_POOL_MIN or val > _DB_POOL_MAX:
            logger.warning(
                f"ONP_DB_POOL_SIZE={raw} outside [{_DB_POOL_MIN}, "
                f"{_DB_POOL_MAX}]; using default {_DB_POOL_SIZE_DEFAULT}"
            )
            return _DB_POOL_SIZE_DEFAULT
        return val
    except ValueError:
        logger.warning(
            f"ONP_DB_POOL_SIZE={raw!r} not an int; using default "
            f"{_DB_POOL_SIZE_DEFAULT}"
        )
        return _DB_POOL_SIZE_DEFAULT


def _db_pool_disabled() -> bool:
    return os.environ.get("ONP_DB_POOL_DISABLED", "").lower() in {
        "1", "true", "yes", "on"
    }


# Module-level pool state. Lazily initialized on first acquire so the
# import doesn't try to talk to SurrealDB at module-load time.
_pool: Optional[asyncio.Queue] = None
_pool_lock: Optional[asyncio.Lock] = None
_pool_total: int = 0
_pool_cap: int = 0


async def _ensure_pool_init() -> None:
    """Idempotent lazy init for the pool's asyncio primitives.

    Must be called from inside an event loop (the asyncio primitives
    require one). All pool acquires go through this path.
    """
    global _pool, _pool_lock, _pool_cap
    if _pool is not None and _pool_lock is not None:
        return
    _pool_cap = _db_pool_size()
    _pool = asyncio.Queue(maxsize=_pool_cap)
    _pool_lock = asyncio.Lock()


async def _new_connection() -> AsyncSurreal:
    """Open + authenticate a fresh AsyncSurreal connection."""
    db = AsyncSurreal(get_database_url())
    await db.signin(
        {
            "username": os.environ.get("SURREAL_USER"),
            "password": get_database_password(),
        }
    )
    await db.use(
        os.environ.get("SURREAL_NAMESPACE"),
        os.environ.get("SURREAL_DATABASE"),
    )
    return db


async def _acquire() -> AsyncSurreal:
    """Get a connection from the pool, growing the pool if needed."""
    global _pool_total
    await _ensure_pool_init()
    assert _pool is not None and _pool_lock is not None
    # Fast path: idle connection ready to go.
    try:
        return _pool.get_nowait()
    except asyncio.QueueEmpty:
        pass
    # Slow path: under the lock, grow the pool if we're below cap.
    async with _pool_lock:
        if _pool_total < _pool_cap:
            conn = await _new_connection()
            _pool_total += 1
            return conn
    # At cap: wait for someone to release.
    return await _pool.get()


async def _release(conn: AsyncSurreal, *, broken: bool = False) -> None:
    """Return a connection to the pool (or drop it if broken)."""
    global _pool_total
    assert _pool is not None
    if broken:
        try:
            await conn.close()
        except Exception:
            pass  # already broken; close failure is fine to swallow
        _pool_total -= 1
        return
    try:
        _pool.put_nowait(conn)
    except asyncio.QueueFull:
        # Shouldn't happen — we never exceed the cap — but if it does,
        # close the extra rather than leak it.
        try:
            await conn.close()
        except Exception:
            pass
        _pool_total -= 1


async def close_pool() -> None:
    """Close every connection in the pool. Call from API/launcher
    shutdown hooks so we exit cleanly."""
    global _pool, _pool_lock, _pool_total
    if _pool is None:
        return
    while True:
        try:
            conn = _pool.get_nowait()
        except asyncio.QueueEmpty:
            break
        try:
            await conn.close()
        except Exception:
            pass
    _pool = None
    _pool_lock = None
    _pool_total = 0


async def _reset_pool_for_tests() -> None:
    """Test-only — drop the pool and force a fresh init on next use."""
    await close_pool()


def get_database_url():
    """Get database URL with backward compatibility.

    v0.7.6 — fixed a long-standing typo in the legacy fallback path:
    the previous version produced `ws://{address}/rpc:{port}` (port
    AFTER the path), which is not a valid WebSocket URL. SurrealDB's
    WebSocket endpoint is `ws://host:port/rpc` — port BEFORE path.
    Any deployment using SURREAL_ADDRESS + SURREAL_PORT without
    SURREAL_URL (legacy Docker setups, pre-2024 deploys) hit
    connection failures with cryptic URL-parse errors.

    The desktop bundle is unaffected because desktop/launcher.py
    always sets SURREAL_URL explicitly. This fix unblocks the
    documented backward-compat path.
    """
    surreal_url = os.getenv("SURREAL_URL")
    if surreal_url:
        return surreal_url

    # Fallback to old format - WebSocket URL format
    address = os.getenv("SURREAL_ADDRESS", "localhost")
    port = os.getenv("SURREAL_PORT", "8000")
    return f"ws://{address}:{port}/rpc"


def get_database_password():
    """Get password with backward compatibility"""
    return os.getenv("SURREAL_PASSWORD") or os.getenv("SURREAL_PASS")


def parse_record_ids(obj: Any) -> Any:
    """Recursively parse and convert RecordIDs into strings."""
    if isinstance(obj, dict):
        return {k: parse_record_ids(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [parse_record_ids(item) for item in obj]
    elif isinstance(obj, RecordID):
        return str(obj)
    return obj


def ensure_record_id(value: Union[str, RecordID]) -> RecordID:
    """Ensure a value is a RecordID."""
    if isinstance(value, RecordID):
        return value
    return RecordID.parse(value)


@asynccontextmanager
async def db_connection():
    """Acquire a SurrealDB connection.

    v0.7.18 — backed by a connection pool (see module-level pool docs).
    The interface is unchanged for callers — every `async with
    db_connection() as conn:` site continues to work — but the
    underlying client is now reused across calls, eliminating
    per-query handshake overhead. Set ONP_DB_POOL_DISABLED=1 to
    fall back to the pre-pool per-query open/close behavior for
    debugging.

    On exception during the wrapped block, the connection is marked
    broken and dropped from the pool — the next acquire will create
    a fresh one. This protects against zombie connections that
    SurrealDB has closed server-side but the client doesn't know it.
    """
    if _db_pool_disabled():
        # Fallback path: behave like pre-v0.7.18 — open, use, close.
        db = await _new_connection()
        try:
            yield db
        finally:
            await db.close()
        return

    conn = await _acquire()
    broken = False
    try:
        yield conn
    except Exception:
        broken = True
        raise
    finally:
        await _release(conn, broken=broken)


async def repo_query(
    query_str: str, vars: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Execute a SurrealQL query and return the results"""

    async with db_connection() as connection:
        try:
            result = parse_record_ids(await connection.query(query_str, vars))
            if isinstance(result, str):
                raise RuntimeError(result)
            return result
        except RuntimeError as e:
            # RuntimeError is raised for retriable transaction conflicts - log at debug to avoid noise
            logger.debug(str(e))
            raise
        except Exception as e:
            logger.exception(e)
            raise


async def repo_create(table: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new record in the specified table"""
    # Remove 'id' attribute if it exists in data
    data.pop("id", None)
    data["created"] = datetime.now(timezone.utc)
    data["updated"] = datetime.now(timezone.utc)
    try:
        async with db_connection() as connection:
            result = parse_record_ids(await connection.insert(table, data))
            # SurrealDB may return a string error message instead of the expected record
            if isinstance(result, str):
                raise RuntimeError(result)
            return result
    except RuntimeError as e:
        logger.error(str(e))
        raise
    except Exception as e:
        logger.exception(e)
        raise RuntimeError("Failed to create record")


async def repo_relate(
    source: str, relationship: str, target: str, data: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Create a relationship between two records with optional data"""
    if data is None:
        data = {}
    query = f"RELATE {source}->{relationship}->{target} CONTENT $data;"
    # logger.debug(f"Relate query: {query}")

    return await repo_query(
        query,
        {
            "data": data,
        },
    )


async def repo_upsert(
    table: str, id: Optional[str], data: Dict[str, Any], add_timestamp: bool = False
) -> List[Dict[str, Any]]:
    """Create or update a record in the specified table"""
    data.pop("id", None)
    if add_timestamp:
        data["updated"] = datetime.now(timezone.utc)
    query = f"UPSERT {id if id else table} MERGE $data;"
    return await repo_query(query, {"data": data})


async def repo_update(
    table: str, id: str, data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Update an existing record by table and id"""
    # If id already contains the table name, use it as is
    try:
        if isinstance(id, RecordID) or (":" in id and id.startswith(f"{table}:")):
            record_id = id
        else:
            record_id = f"{table}:{id}"
        data.pop("id", None)
        if "created" in data and isinstance(data["created"], str):
            data["created"] = datetime.fromisoformat(data["created"])
        data["updated"] = datetime.now(timezone.utc)
        query = f"UPDATE {record_id} MERGE $data;"
        # logger.debug(f"Update query: {query}")
        result = await repo_query(query, {"data": data})
        # if isinstance(result, list):
        #     return [_return_data(item) for item in result]
        return parse_record_ids(result)
    except Exception as e:
        raise RuntimeError(f"Failed to update record: {str(e)}")


async def repo_delete(record_id: Union[str, RecordID]):
    """Delete a record by record id"""

    try:
        async with db_connection() as connection:
            return await connection.delete(ensure_record_id(record_id))
    except Exception as e:
        logger.exception(e)
        raise RuntimeError(f"Failed to delete record: {str(e)}")


async def repo_insert(
    table: str, data: List[Dict[str, Any]], ignore_duplicates: bool = False
) -> List[Dict[str, Any]]:
    """Create a new record in the specified table"""
    try:
        async with db_connection() as connection:
            result = parse_record_ids(await connection.insert(table, data))
            # SurrealDB may return a string error message instead of the expected records
            if isinstance(result, str):
                raise RuntimeError(result)
            return result
    except RuntimeError as e:
        if ignore_duplicates and "already contains" in str(e):
            return []
        # Log transaction conflicts at debug level (they are expected during concurrent operations)
        error_str = str(e).lower()
        if "transaction" in error_str or "conflict" in error_str:
            logger.debug(str(e))
        else:
            logger.error(str(e))
        raise
    except Exception as e:
        if ignore_duplicates and "already contains" in str(e):
            return []
        logger.exception(e)
        raise RuntimeError("Failed to create record")
