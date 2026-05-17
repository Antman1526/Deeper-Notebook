from typing import Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from api.command_service import CommandService
from api.models import EmbedRequest, EmbedResponse
from open_notebook.ai.models import model_manager
from open_notebook.domain.notebook import Note, Notebook, Source

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
    skip_reason: Optional[str] = None    # set when queued=False


class NotebookVectorizeResponse(BaseModel):
    notebook_id: str
    notebook_name: str
    total_sources: int
    queued: int
    skipped: int
    failed: int
    sources: list[NotebookVectorizeSourceEntry]   # capped at 100
    warnings: list[str] = []


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
                raise HTTPException(
                    status_code=500, detail=f"Failed to queue embedding: {str(e)}"
                )

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
    except Exception as e:
        logger.error(
            f"Error embedding {embed_request.item_type} {embed_request.item_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=500, detail=f"Error embedding content: {str(e)}"
        )


@router.post(
    "/notebooks/{notebook_id}/vectorize_sources",
    response_model=NotebookVectorizeResponse,
)
async def vectorize_notebook_sources(
    notebook_id: str, req: NotebookVectorizeRequest,
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
    """
    notebook = await Notebook.get(notebook_id)
    if not notebook:
        raise HTTPException(
            status_code=404, detail=f"Notebook {notebook_id!r} not found",
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

    sources = await notebook.get_sources()
    # v0.7.110 — Hard cap on per-request size. A notebook with tens of
    # thousands of sources would spam the worker queue and pin the
    # request for a long time even though each submit is fast. 500 is
    # plenty for realistic notebooks (the FsList endpoint uses the
    # same cap); operators with bigger notebooks can raise via env or
    # call the endpoint multiple times.
    import os as _os_for_cap
    _max_sources = int(
        _os_for_cap.environ.get("ONP_BULK_VECTORIZE_MAX_SOURCES", "500").strip()
        or 500
    )
    truncation_warning: Optional[str] = None
    if len(sources) > _max_sources:
        truncation_warning = (
            f"Notebook has {len(sources)} sources; this call processed only "
            f"the first {_max_sources}. Raise ONP_BULK_VECTORIZE_MAX_SOURCES "
            "or call again to handle the rest."
        )
        sources = sources[:_max_sources]
    entries: list[NotebookVectorizeSourceEntry] = []
    queued = 0
    skipped = 0
    failed = 0
    warnings: list[str] = []
    if truncation_warning:
        warnings.append(truncation_warning)

    # Ensure embedding_commands is importable for surreal_commands.
    try:
        import commands.embedding_commands  # noqa: F401
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
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
        already_embedded = (
            getattr(source, "embedded_chunks", 0) or 0
        ) > 0
        if req.only_missing and already_embedded:
            entries.append(
                NotebookVectorizeSourceEntry(
                    source_id=sid, title=title, queued=False,
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
                    source_id=sid, title=title, queued=False,
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
                title, sid, exc,
            )
            entries.append(
                NotebookVectorizeSourceEntry(
                    source_id=sid, title=title, queued=False,
                    skip_reason=f"submit_failed: {exc}",
                )
            )
            failed += 1
            warnings.append(
                f"Could not queue embedding for {title!r}: {exc}"
            )
            continue
        entries.append(
            NotebookVectorizeSourceEntry(
                source_id=sid, title=title, queued=True,
                command_id=str(command_id) if command_id else None,
            )
        )
        queued += 1

    logger.info(
        "Bulk vectorize: notebook={} total={} queued={} skipped={} failed={}",
        notebook_id, len(sources), queued, skipped, failed,
    )
    return NotebookVectorizeResponse(
        notebook_id=notebook_id,
        notebook_name=notebook.name,
        total_sources=len(sources),
        queued=queued,
        skipped=skipped,
        failed=failed,
        sources=entries[:100],
        warnings=warnings,
    )
