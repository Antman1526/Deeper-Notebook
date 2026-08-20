import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger
from surreal_commands import get_command_status, submit_command

from api.utils.iso import iso  # v0.7.183 — Safari-safe datetime serialization
from deeper_notebook.environment import resolve_env


class CommandService:
    """Generic service layer for command operations"""

    @staticmethod
    async def submit_command_job(
        module_name: str,  # Actually app_name for surreal-commands
        command_name: str,
        command_args: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """Submit a generic command job for background processing"""
        try:
            # Ensure command modules are imported before submitting
            # This is needed because submit_command validates against local registry
            try:
                import commands.podcast_commands  # noqa: F401
            except ImportError as import_err:
                logger.error(f"Failed to import command modules: {import_err}")
                raise ValueError("Command modules not available")

            # v0.7.55 — wrap blocking submit_command (sync SurrealDB WS
            # call) in asyncio.to_thread so it doesn't stall the event
            # loop. Same root cause as podcast_service.py.
            # v0.7.115 — add a wait_for around the to_thread call.
            # The blocking submit_command is normally <500ms, but if
            # the SurrealDB pool is saturated or the WS handshake
            # hangs, the request would otherwise wait indefinitely.
            # 10s default is generous for a row-insert; tunable via
            # DEEPER_NOTEBOOK_SUBMIT_COMMAND_TIMEOUT_SEC.
            import os

            _submit_timeout = float(
                resolve_env("DEEPER_NOTEBOOK_SUBMIT_COMMAND_TIMEOUT_SEC", "10").strip()
                or 10
            )
            try:
                cmd_id = await asyncio.wait_for(
                    asyncio.to_thread(
                        submit_command,
                        module_name,  # actually the app name
                        command_name,
                        command_args,
                    ),
                    timeout=_submit_timeout,
                )
            except asyncio.TimeoutError as exc:
                raise ValueError(
                    f"Command submission timed out after {_submit_timeout:.0f}s. "
                    "The SurrealDB connection pool may be saturated. "
                    "Raise DEEPER_NOTEBOOK_SUBMIT_COMMAND_TIMEOUT_SEC or check pool health."
                ) from exc
            # Convert RecordID to string if needed
            if not cmd_id:
                raise ValueError("Failed to get cmd_id from submit_command")
            cmd_id_str = str(cmd_id)
            logger.info(
                f"Submitted command job: {cmd_id_str} for {module_name}.{command_name}"
            )
            return cmd_id_str

        except Exception as e:
            # v0.7.204 — re-raise as typed DeeperNotebookError so the
            # global FastAPI classifier in api/main.py emits a 500
            # with a structured payload instead of bubbling an
            # untyped Exception that the framework renders as
            # "Internal Server Error" with no detail. ValueError /
            # asyncio.TimeoutError (the explicit raises above) are
            # already typed and pass through unchanged because they
            # subclass Exception too — only untyped Exceptions get
            # wrapped. Logging stays at error level so ops have the
            # full stack.
            from deeper_notebook.exceptions import DeeperNotebookError

            logger.error(f"Failed to submit command job: {e}")
            if isinstance(e, (DeeperNotebookError, ValueError, asyncio.TimeoutError)):
                raise
            raise DeeperNotebookError(
                "Failed to submit command job. Check the API logs "
                "for the underlying error."
            ) from e

    @staticmethod
    async def get_command_status(job_id: str) -> Optional[dict[str, Any]]:
        """Get status of any command job.

        v0.7.87 — returns `None` for missing jobs instead of a synthetic
        `{"status": "unknown"}` payload, so the HTTP layer can return a
        real 404 instead of a 200 with a fake-OK shape. The previous
        behavior made the frontend special-case "unknown" everywhere
        instead of using standard error handling.
        """
        try:
            status = await get_command_status(job_id)
            # v0.8.70 — BUG FIX: surreal_commands.get_command_status raises
            # ValueError("Command <id> not found") for unknown/expired ids;
            # it never returns None. So the `status is None` branch below was
            # dead and the not-found ValueError fell through to the generic
            # `except` → re-raised → HTTP 500. Polling a stale job_id (common
            # after a restart or the lifespan stale-command reaper runs) now
            # returns None so the router can emit a real 404. Kept as a guard
            # in case a future upstream version returns None instead.
            if status is None:
                return None
            return {
                "job_id": job_id,
                "status": status.status,
                "result": status.result,
                "error_message": getattr(status, "error_message", None),
                # v0.7.183 — iso() for Safari new Date() compat. Same
                # pattern as podcast_service.py:171-176.
                "created": iso(status.created)
                if hasattr(status, "created") and status.created
                else None,
                "updated": iso(status.updated)
                if hasattr(status, "updated") and status.updated
                else None,
                "progress": getattr(status, "progress", None),
            }
        except ValueError as e:
            # v0.8.70 — a "not found" ValueError means the job id is unknown
            # or expired; map it to None so the HTTP layer returns 404 rather
            # than 500. Any other ValueError is a real error and re-raised.
            if "not found" in str(e).lower():
                logger.info(f"Command status: job {job_id} not found")
                return None
            logger.error(f"Failed to get command status: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to get command status: {e}")
            raise

    @staticmethod
    async def list_command_jobs(
        module_filter: Optional[str] = None,
        command_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List command jobs with optional filtering.

        v0.7.87 — was a stub returning []. Now reads from the
        `command` table populated by surreal_commands (every submitted
        job lands there with status/result/error_message/timestamps).
        Filters are applied in SurrealQL so we never load the whole
        table into Python.
        """
        from deeper_notebook.database.repository import ensure_record_id, repo_query

        clauses: list[str] = []
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 500))}
        if module_filter:
            clauses.append("app = $app")
            params["app"] = module_filter
        if command_filter:
            clauses.append("name = $name")
            params["name"] = command_filter
        if status_filter:
            clauses.append("status = $status")
            params["status"] = status_filter
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        try:
            rows = await repo_query(
                f"SELECT id, app, name, status, error_message, created, updated "  # nosec B608
                f"FROM command{where} "
                f"ORDER BY created DESC LIMIT $limit",
                params,
            )
        except Exception as exc:
            logger.warning(f"list_command_jobs query failed (returning []): {exc}")
            return []
        if not rows:
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "job_id": str(row.get("id", "")),
                    "app": row.get("app"),
                    "command": row.get("name"),
                    "status": row.get("status"),
                    "error_message": row.get("error_message"),
                    # v0.7.202 — was `str(row.get("created"))` which,
                    # depending on the surrealdb driver version,
                    # could render the column as `surrealdb.DateTime(...)`
                    # repr — breaks `new Date(...)` on Safari and
                    # any client that expects an ISO 8601 string.
                    # Use the iso() helper the rest of the codebase
                    # standardised on in v0.7.181-183.
                    "created": iso(row.get("created")),
                    "updated": iso(row.get("updated")),
                }
            )
        return out

    @staticmethod
    async def cancel_command_job(job_id: str) -> bool:
        """Cancel a running command job.

        v0.7.87 — was a no-op stub that returned True without doing
        anything; the frontend trusted the response, removed the job
        from the UI, and the underlying command kept running. Now
        marks the surreal_commands row as `canceled` via the same
        pattern used in `Source.delete` (v0.7.32). Only nudges jobs
        whose current status is in {new, queued, running} — completed
        and already-canceled jobs need no action. Returns False if
        the job wasn't found or wasn't in a cancellable state.

        Note: surreal_commands' worker poll loop is what actually halts
        execution — setting the row to `canceled` is the signal. For
        jobs that are mid-execution the worker may finish the current
        operation before noticing the cancel; that's the same
        cooperative-cancellation contract as Source.delete.
        """
        try:
            from surreal_commands import get_command_status as _gcs

            # v0.7.177 — `surreal_commands.core.service.get_command_service`
            # is a private API surface. Importing it directly couples us to
            # the upstream package's internal module layout, so an upstream
            # refactor that renames `core.service` → `service` (or moves
            # `get_command_service` elsewhere) would silently break all
            # job cancellation with an ImportError caught only by the
            # broad `except Exception` below. Wrap the private import in
            # try/ImportError and fall back to a direct repo_query UPDATE
            # on the `command` table — same pattern the lifespan stale-
            # command reaper at api/main.py:272-287 uses.
            try:
                from surreal_commands.core.service import (
                    get_command_service as _gcsvc,
                )

                _have_private_api = True
            except ImportError:
                _have_private_api = False
                logger.debug(
                    "cancel_command_job: surreal_commands.core.service "
                    "not importable, falling back to direct UPDATE on "
                    "the `command` table."
                )

            status = await _gcs(job_id)
            if status is None:
                logger.info(f"cancel_command_job: {job_id} not found")
                return False
            status_str = getattr(status, "status", "")
            if isinstance(status_str, str):
                status_str = status_str.lower()
            if status_str not in {"new", "queued", "running"}:
                logger.info(
                    f"cancel_command_job: {job_id} status={status_str!r} — "
                    "not in a cancellable state, skipping"
                )
                return False

            cancel_msg = "Cancelled by user via DELETE /commands/jobs/{job_id}"
            if _have_private_api:
                svc = _gcsvc()
                await svc.update_command_result(
                    job_id,
                    status="canceled",
                    result={},
                    error_message=cancel_msg,
                )
            else:
                # Direct SurrealDB fallback. Mirrors the structure of the
                # lifespan stale-command reaper. The `command:` prefix
                # handling matches what surreal_commands itself stores.
                # noqa block: isort would merge these two imports, but the
                # v0.7.177 shape guard pins the exact single-line repo_query
                # import literal for the fallback path.
                from deeper_notebook.database.repository import (  # noqa: I001
                    ensure_record_id,
                )
                from deeper_notebook.database.repository import repo_query

                # v0.8.87 (B608) — parse before interpolating: RecordID.parse
                # rejects anything that is not a well-formed record id, so a  # nosec B608
                # hostile job_id cannot smuggle SurrealQL into the UPDATE.
                record_id = ensure_record_id(
                    job_id if job_id.startswith("command:") else f"command:{job_id}"
                )
                await repo_query(
                    f"UPDATE {record_id} "  # nosec B608
                    "SET status = 'canceled', "
                    "    result = {}, "
                    "    error_message = $msg, "
                    "    updated = time::now()",
                    {"msg": cancel_msg},
                )
            logger.info(f"cancel_command_job: marked {job_id} as canceled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel command job: {e}")
            raise
