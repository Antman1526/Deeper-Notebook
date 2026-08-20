from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from loguru import logger
from pydantic import BaseModel, Field

from api.command_service import CommandService
from api.models import EmbedRequest, EmbedResponse
from deeper_notebook.ai.models import model_manager
from deeper_notebook.domain.notebook import Note, Notebook, Source
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import InvalidInputError, NotFoundError

router = APIRouter()


# v0.7.106 — Bulk per-notebook vectorize. Recovers from cases where a
# notebook's sources didn't get embedded (e.g. v0.7.94 import-time
# vectorize failure, embedding model swap, upgrade from a version
# without semantic search). Submits one embed_source command per
# source; fire-and-forget so the response returns immediately with
# command_ids the caller can poll.
class NotebookVectorizeRequest(BaseModel):
    only_missing: bool = Field(
        True,
        description=(
            "Skip sources that already have embeddings. Default True so "
            "re-running this endpoint is safe and fast. Set False to "
            "force re-embedding (useful after switching embedding models)."
        ),
    )


class NotebookVectorizeSourceEntry(BaseModel):
    source_id: str
    title: str
    queued: bool
    command_id: Optional[str] = None
    skip_reason: Optional[str] = None  # set when queued=False


class NotebookVectorizeResponse(BaseModel):
    notebook_id: str
    notebook_name: str
    total_sources: int
    queued: int
    skipped: int
    failed: int
    sources: list[NotebookVectorizeSourceEntry]  # capped at 100
    warnings: list[str] = []
    # v0.7.137 — Pagination fields so callers can systematically work
    # through notebooks with more sources than the per-request limit.
    # Before this release the request silently truncated after
    # DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES (default 500) and there was no
    # way to reach the remaining sources without raising the env var
    # OR running the endpoint multiple times against the same first-500
    # slice (which would re-process them, not paginate).
    offset: int = 0
    limit: int = 500
    # has_more lets a caller easily decide whether to continue paging
    # without computing `offset + limit < total_sources` themselves.
    has_more: bool = False


@router.post("/embed", response_model=EmbedResponse)
async def embed_content(embed_request: EmbedRequest):
    """Embed content for vector search."""
    try:
        # Check if embedding model is available
        if not await model_manager.get_embedding_model():
            raise HTTPException(
                status_code=400,
                detail="No embedding model configured. Please configure one in the Models section.",
            )

        item_id = embed_request.item_id
        item_type = embed_request.item_type.lower()

        # Validate item type
        if item_type not in ["source", "note"]:
            raise HTTPException(
                status_code=400, detail="Item type must be either 'source' or 'note'"
            )

        # Branch based on processing mode
        if embed_request.async_processing:
            # ASYNC PATH: Submit command for background processing
            logger.info(f"Using async processing for {item_type} {item_id}")

            try:
                # Import commands to ensure they're registered
                import commands.embedding_commands  # noqa: F401

                # Submit type-specific command
                if item_type == "source":
                    command_name = "embed_source"
                    command_input = {"source_id": item_id}
                else:  # note
                    command_name = "embed_note"
                    command_input = {"note_id": item_id}

                command_id = await CommandService.submit_command_job(
                    "open_notebook",
                    command_name,
                    command_input,
                )

                logger.info(f"Submitted async {command_name} command: {command_id}")

                return EmbedResponse(
                    success=True,
                    message="Embedding queued for background processing",
                    item_id=item_id,
                    item_type=item_type,
                    command_id=command_id,
                )

            except HTTPException:
                # v0.7.108 — re-raise typed HTTPExceptions so the next
                # `except Exception` doesn't clobber them to 500.
                raise
            except Exception as e:
                logger.error(f"Failed to submit async embedding command: {e}")
                raise HTTPException(status_code=500, detail="Failed to queue embedding")

        else:
            # DOMAIN MODEL PATH: Submit job via domain model convenience methods
            # These methods internally call submit_command() - still fire-and-forget
            logger.info(f"Using domain model path for {item_type} {item_id}")

            command_id = None

            # Get the item and submit embedding job
            if item_type == "source":
                source_item = await Source.get(item_id)
                if not source_item:
                    raise HTTPException(status_code=404, detail="Source not found")

                # Submit embed_source job (returns command_id for tracking)
                command_id = await source_item.vectorize()
                message = "Source embedding job submitted"

            elif item_type == "note":
                note_item = await Note.get(item_id)
                if not note_item:
                    raise HTTPException(status_code=404, detail="Note not found")

                # Note.save() internally submits embed_note command and returns command_id
                command_id = await note_item.save()
                message = "Note embedding job submitted"

            return EmbedResponse(
                success=True,
                message=message,
                item_id=item_id,
                item_type=item_type,
                command_id=command_id,
            )

    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.183 — bubble typed exceptions to the global handlers
        # (NotFoundError → 404, InvalidInputError → 400). Continuation
        # of the v0.7.179/181/182 sweep to the final routers.
        raise
    except Exception as e:
        logger.error(
            f"Error embedding {embed_request.item_type} {embed_request.item_id}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail="Error embedding content")


@router.post(
    "/notebooks/{notebook_id}/vectorize_sources",
    response_model=NotebookVectorizeResponse,
)
async def vectorize_notebook_sources(
    notebook_id: str,
    req: NotebookVectorizeRequest,
    response: Response,
    offset: int = Query(
        0,
        ge=0,
        description=(
            "Skip the first N sources. Use to paginate through "
            "notebooks with more sources than the per-request limit. "
            "Default 0 (first page)."
        ),
    ),
    limit: int = Query(
        500,
        ge=1,
        le=2000,
        description=(
            "Process at most N sources in this call. Default 500, max 2000. "
            "The hard ceiling exists so a single misclick can't spam the "
            "worker queue with tens of thousands of submissions; operators "
            "with larger notebooks should paginate with offset."
        ),
    ),
) -> NotebookVectorizeResponse:
    """v0.7.106 — Bulk re-embed every Source attached to a notebook.

    Submits one `embed_source` command per source (fire-and-forget) and
    returns immediately with the queued command_ids. The actual embedding
    happens in the background worker; poll `/commands/{command_id}` for
    per-source progress.

    With `only_missing=true` (default), sources that already have
    embeddings are skipped — re-running is a no-op. Set `only_missing
    =false` to force re-embedding (useful after switching embedding
    models in Settings → Models).

    v0.7.137 — Pagination added. Previously the endpoint silently
    truncated to DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES (default 500) and
    there was no way to reach beyond that without raising the env
    var. Now callers can use `?offset=` to step through notebooks
    of any size; the response includes `total_sources`, `offset`,
    `limit`, and `has_more` so the next page is trivial to request.
    `DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES` still acts as a hard per-call
    ceiling — if `limit` exceeds it, we clamp down + emit a warning
    so a misconfigured caller doesn't accidentally spam the worker.
    """
    notebook = await Notebook.get(notebook_id)
    if not notebook:
        raise HTTPException(
            status_code=404,
            detail=f"Notebook {notebook_id!r} not found",
        )

    # Embedding model must be configured before we queue anything —
    # otherwise the worker would just fail per source and the user
    # wouldn't know why until they polled each command.
    if not await model_manager.get_embedding_model():
        raise HTTPException(
            status_code=400,
            detail=(
                "No embedding model configured. Set one in Settings → "
                "Models before calling this endpoint, otherwise every "
                "queued embed_source job would fail."
            ),
        )

    all_sources = await notebook.get_sources()
    total_sources = len(all_sources)

    # v0.7.110 / v0.7.137 — Hard env-driven cap defends against
    # misconfigured callers passing massive `limit` values. Default
    # 500 unchanged. If the caller's `limit` exceeds the cap, clamp
    # down with a warning rather than reject — backward compat.
    _max_sources_cap = int(
        (
            resolve_env(
                "DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES",
                "500",
            )
            or "500"
        ).strip()
        or 500
    )
    effective_limit = min(limit, _max_sources_cap)

    warnings: list[str] = []
    if effective_limit < limit:
        warnings.append(
            f"Requested limit {limit} exceeds the per-call cap "
            f"({_max_sources_cap}); clamped down. Raise "
            "DEEPER_NOTEBOOK_BULK_VECTORIZE_MAX_SOURCES if you need bigger batches, "
            "or use pagination (?offset=) to walk the notebook in chunks."
        )

    # v0.7.137 — slice with offset+limit. Sources past `offset + limit`
    # are NOT processed in this call; the caller paginates with the
    # next offset value. The response's `has_more` field surfaces
    # whether continuation is needed.
    sources = all_sources[offset : offset + effective_limit]
    has_more = (offset + len(sources)) < total_sources

    entries: list[NotebookVectorizeSourceEntry] = []
    queued = 0
    skipped = 0
    failed = 0

    # Set pagination response headers matching the v0.7.130 podcasts
    # endpoint convention so frontends + curl users get consistent
    # affordances.
    response.headers["X-Total-Count"] = str(total_sources)
    response.headers["X-Offset"] = str(offset)
    response.headers["X-Limit"] = str(effective_limit)

    # Ensure embedding_commands is importable for surreal_commands.
    try:
        import commands.embedding_commands  # noqa: F401
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.183 — bubble typed exceptions to the global handlers.
        raise
    except Exception as exc:
        # Worker registry not available — fail loudly so the user knows
        # to check the worker process is running.
        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not load embedding command registry: {exc}. "
                "Check that the surreal_commands worker is running."
            ),
        )

    for source in sources:
        sid = str(source.id) if source.id else ""
        title = source.title or "(untitled)"
        # Skip-if-already-embedded path. We check the `embedded_chunks`
        # field if present (set by the embed_source command). A source
        # without that field has never been embedded.
        already_embedded = (getattr(source, "embedded_chunks", 0) or 0) > 0
        if req.only_missing and already_embedded:
            entries.append(
                NotebookVectorizeSourceEntry(
                    source_id=sid,
                    title=title,
                    queued=False,
                    skip_reason="already_embedded",
                )
            )
            skipped += 1
            continue

        # No full_text → embed_source job would no-op (or error). Skip
        # with a diagnostic warning so the user knows which sources
        # need re-extraction first.
        if not (source.full_text or "").strip():
            entries.append(
                NotebookVectorizeSourceEntry(
                    source_id=sid,
                    title=title,
                    queued=False,
                    skip_reason="no_text",
                )
            )
            skipped += 1
            warnings.append(
                f"Source {title!r} ({sid}) has no extracted text — "
                "re-process the source first (Sources → re-extract) "
                "before embedding."
            )
            continue

        try:
            command_id = await source.vectorize()
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            logger.warning(
                "Bulk vectorize: {} ({}) failed to queue: {}",
                title,
                sid,
                exc,
            )
            entries.append(
                NotebookVectorizeSourceEntry(
                    source_id=sid,
                    title=title,
                    queued=False,
                    skip_reason=f"submit_failed: {exc}",
                )
            )
            failed += 1
            warnings.append(f"Could not queue embedding for {title!r}: {exc}")
            continue
        entries.append(
            NotebookVectorizeSourceEntry(
                source_id=sid,
                title=title,
                queued=True,
                command_id=str(command_id) if command_id else None,
            )
        )
        queued += 1

    logger.info(
        "Bulk vectorize: notebook={} total={} queued={} skipped={} failed={}",
        notebook_id,
        len(sources),
        queued,
        skipped,
        failed,
    )
    return NotebookVectorizeResponse(
        notebook_id=notebook_id,
        notebook_name=notebook.name,
        # v0.7.137 — `total_sources` is the FULL notebook count, not the
        # slice we processed. Before pagination it conflated both
        # values; now `queued + skipped + failed` reflects this page's
        # work while total_sources tells the caller how much remains.
        total_sources=total_sources,
        queued=queued,
        skipped=skipped,
        failed=failed,
        sources=entries[:100],
        warnings=warnings,
        offset=offset,
        limit=effective_limit,
        has_more=has_more,
    )
