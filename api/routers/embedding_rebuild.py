from fastapi import APIRouter, HTTPException
from loguru import logger
from surreal_commands import get_command_status

from api.command_service import CommandService
from api.models import (
    RebuildProgress,
    RebuildRequest,
    RebuildResponse,
    RebuildStats,
    RebuildStatusResponse,
)
from api.utils.iso import iso  # v0.7.182 — Safari-safe datetime serialization
from deeper_notebook.database.repository import repo_query

router = APIRouter()


# v0.7.160 — Shared helper that mirrors the dict/int dual-path the
# inline code repeated 3× before consolidation. SurrealDB sometimes
# returns `[{"count": N}]` and sometimes `[N]` depending on the
# `SELECT VALUE` / `GROUP ALL` interaction; this preserves the
# original tolerance without copy-paste drift.
def _extract_count(result) -> int:
    if not result:
        return 0
    if isinstance(result[0], dict):
        return int(result[0].get("count", 0) or 0)
    if isinstance(result[0], int):
        return result[0]
    return 0


@router.post("/rebuild", response_model=RebuildResponse)
async def start_rebuild(request: RebuildRequest):
    """
    Start a background job to rebuild embeddings.

    - **mode**: "existing" (re-embed items with embeddings) or "all" (embed everything)
    - **include_sources**: Include sources in rebuild (default: true)
    - **include_notes**: Include notes in rebuild (default: true)
    - **include_insights**: Include insights in rebuild (default: true)

    Returns command ID to track progress and estimated item count.
    """
    try:
        logger.info(f"Starting rebuild request: mode={request.mode}")

        # Import commands to ensure they're registered
        import commands.embedding_commands  # noqa: F401

        # v0.7.160 — Consolidated 6 round-trips (sources/notes/insights ×
        # existing/all) into one parallel asyncio.gather. Previously each
        # branch awaited its own repo_query sequentially, paying the
        # SurrealDB roundtrip latency 6× on every rebuild submission.
        # Now we issue all three counts in parallel and skip any branch
        # the caller opted out of. The total stays the same and the
        # per-row shape parsing is preserved verbatim.
        async def _count_sources() -> int:
            if request.mode == "existing":
                result = await repo_query(
                    """
                    SELECT VALUE count(array::distinct(
                        SELECT VALUE source.id
                        FROM source_embedding
                        WHERE embedding != none AND array::len(embedding) > 0
                    )) as count FROM {}
                    """
                )
            else:
                result = await repo_query(
                    "SELECT VALUE count() as count FROM source "
                    "WHERE full_text != none GROUP ALL"
                )
            return _extract_count(result)

        async def _count_notes() -> int:
            if request.mode == "existing":
                result = await repo_query(
                    "SELECT VALUE count() as count FROM note "
                    "WHERE embedding != none AND array::len(embedding) > 0 GROUP ALL"
                )
            else:
                result = await repo_query(
                    "SELECT VALUE count() as count FROM note "
                    "WHERE content != none GROUP ALL"
                )
            return _extract_count(result)

        async def _count_insights() -> int:
            if request.mode == "existing":
                result = await repo_query(
                    "SELECT VALUE count() as count FROM source_insight "
                    "WHERE embedding != none AND array::len(embedding) > 0 GROUP ALL"
                )
            else:
                result = await repo_query(
                    "SELECT VALUE count() as count FROM source_insight GROUP ALL"
                )
            return _extract_count(result)

        # Run the selected counts concurrently. asyncio.gather preserves
        # the input order, and skipped branches contribute 0 cleanly.
        import asyncio as _asyncio

        coros = []
        if request.include_sources:
            coros.append(_count_sources())
        if request.include_notes:
            coros.append(_count_notes())
        if request.include_insights:
            coros.append(_count_insights())
        counts = await _asyncio.gather(*coros) if coros else []
        total_estimate = sum(counts)

        logger.info(f"Estimated {total_estimate} items to process")

        # Submit command
        command_id = await CommandService.submit_command_job(
            "open_notebook",
            "rebuild_embeddings",
            {
                "mode": request.mode,
                "include_sources": request.include_sources,
                "include_notes": request.include_notes,
                "include_insights": request.include_insights,
            },
        )

        logger.info(f"Submitted rebuild command: {command_id}")

        return RebuildResponse(
            command_id=command_id,
            total_items=total_estimate,
            message=f"Rebuild operation started. Estimated {total_estimate} items to process.",
        )

    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Failed to start rebuild: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail="Failed to start rebuild operation")


@router.get("/rebuild/{command_id}/status", response_model=RebuildStatusResponse)
async def get_rebuild_status(command_id: str):
    """
    Get the status of a rebuild operation.

    Returns:
    - **status**: queued, running, completed, failed
    - **progress**: processed count, total count, percentage
    - **stats**: breakdown by type (sources, notes, insights, failed)
    - **timestamps**: started_at, completed_at
    """
    try:
        # Get command status from surreal_commands
        status = await get_command_status(command_id)

        if not status:
            raise HTTPException(status_code=404, detail="Rebuild command not found")

        # Build response based on status
        response = RebuildStatusResponse(
            command_id=command_id,
            status=status.status,
        )

        # Extract metadata from command result
        if status.result and isinstance(status.result, dict):
            result = status.result

            # Build progress info
            if "total_items" in result and "jobs_submitted" in result:
                total = result["total_items"]
                submitted = result["jobs_submitted"]
                response.progress = RebuildProgress(
                    processed=submitted,
                    total=total,
                    percentage=round((submitted / total * 100) if total > 0 else 0, 2),
                )

            # Build stats
            response.stats = RebuildStats(
                sources=result.get("sources_submitted", 0),
                notes=result.get("notes_submitted", 0),
                insights=result.get("insights_submitted", 0),
                failed=result.get("failed_submissions", 0),
            )

        # Add timestamps
        # v0.7.182 — iso() for Safari new Date() compat on the
        # rebuild-status timestamps the frontend renders.
        if hasattr(status, "created") and status.created:
            response.started_at = iso(status.created)
        if hasattr(status, "updated") and status.updated:
            response.completed_at = iso(status.updated)

        # Add error message if failed
        if (
            status.status == "failed"
            and status.result
            and isinstance(status.result, dict)
        ):
            response.error_message = status.result.get("error_message", "Unknown error")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get rebuild status: {e}")
        logger.exception(e)
        raise HTTPException(status_code=500, detail="Failed to get rebuild status")
