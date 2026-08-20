from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.models import NoteCreate, NoteResponse, NoteUpdate
from api.utils.iso import iso  # v0.7.181 — Safari-safe datetime serialization
from deeper_notebook.domain.notebook import ExternalNoteReadOnlyError, Note
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import InvalidInputError, NotFoundError

router = APIRouter()


@router.get("/notes", response_model=list[NoteResponse])
async def get_notes(
    notebook_id: Optional[str] = Query(None, description="Filter by notebook ID"),
    # v0.7.159 — Pagination on the unfiltered branch. Previously
    # `GET /notes` (no notebook_id) ran `SELECT * FROM note ORDER BY
    # updated DESC` with NO limit, returning every note (with content)
    # as JSON. A heavy user with thousands of notes hit by an API
    # explorer call, stale React Query cache, or background sync
    # would get a multi-MB response and burn one of 4 worker slots
    # for seconds. Default cap = 200 newest; clients can paginate
    # with `offset`. `limit` caps at 1000 so the per-call ceiling
    # can't be bypassed even by curious callers.
    limit: int = Query(
        200,
        ge=1,
        le=1000,
        description="Max rows to return (default 200, max 1000).",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Rows to skip for pagination (default 0).",
    ),
):
    """Get all notes with optional notebook filtering."""
    try:
        if notebook_id:
            # Get notes for a specific notebook. The relationship traversal
            # is naturally bounded by the notebook size, so no pagination
            # is layered on top — that would require a separate change to
            # Notebook.get_notes().
            from deeper_notebook.domain.notebook import Notebook

            notebook = await Notebook.get(notebook_id)
            if not notebook:
                raise NotFoundError("Notebook not found")
            notes = await notebook.get_notes()
        else:
            # v0.7.159 — paginated; see Query() defaults above.
            notes = await Note.get_all(
                order_by="updated desc",
                limit=limit,
                offset=offset,
            )

        return [
            NoteResponse(
                id=note.id or "",
                title=note.title,
                content=note.content,
                note_type=note.note_type,
                created=iso(note.created),
                updated=iso(note.updated),
            )
            for note in notes
        ]
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.201 — bubble typed exceptions to the global classifier
        # (404 with the user-friendly message). Was caught by
        # `except Exception` below and collapsed to 500 "Error
        # fetching notes" after v0.7.201 swapped the bare 404
        # HTTPException for NotFoundError.
        raise
    except Exception as e:
        logger.error(f"Error fetching notes: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching notes")


@router.post("/notes", response_model=NoteResponse)
async def create_note(note_data: NoteCreate):
    """Create a new note."""
    try:
        # Auto-generate title if not provided and it's an AI note
        title = note_data.title
        if not title and note_data.note_type == "ai" and note_data.content:
            import asyncio
            import os

            from deeper_notebook.graphs.prompt import graph as prompt_graph

            prompt = "Based on the Note below, please provide a Title for this content, with max 15 words"
            # v0.7.95 — wrap the LLM call in wait_for so a hung local model
            # (loading, mid-eval, OOM) can't block note creation. Title
            # generation is the only thing this LLM call does; if it
            # times out, fall back to a content-derived title rather than
            # erroring the whole create-note request. 60s default is
            # generous for a one-sentence prompt; tunable via env.
            _title_timeout = float(
                resolve_env("DEEPER_NOTEBOOK_NOTE_TITLE_TIMEOUT_SEC", "60").strip()
                or 60
            )
            result = None
            try:
                result = await asyncio.wait_for(
                    prompt_graph.ainvoke(
                        {  # type: ignore[arg-type]
                            "input_text": note_data.content,
                            "prompt": prompt,
                        }
                    ),
                    timeout=_title_timeout,
                )
            except asyncio.TimeoutError:
                # v0.7.95 — Graceful degradation. Fall back to first line
                # of content as the title rather than 500ing the create-note
                # request. Local LLMs hang; the user still gets their note.
                logger.warning(
                    "Note auto-title timed out after {}s; using first-line fallback",
                    _title_timeout,
                )
                first_line = (
                    note_data.content.strip().splitlines()[0]
                    if note_data.content
                    else "Untitled"
                )
                # v0.7.204 — was `first_line[:80]` (bare-char slice).
                # On CJK content the first 80 chars can be 240+ bytes,
                # and on a string containing a multi-codepoint
                # grapheme (an emoji ZWJ sequence, a Hangul jamo
                # cluster, a combining-mark sequence) the [:80] could
                # land mid-grapheme and render as a broken character
                # in the sidebar title. The actual sidebar column has
                # plenty of room; the [:80] was a safety cap, not a
                # width cap. Make it tunable via env (operators with
                # CJK-heavy content can raise it) and clamp to a sane
                # range so a misconfigured value can't break note
                # creation entirely.
                _max_title_len_raw = resolve_env(
                    "DEEPER_NOTEBOOK_NOTE_TITLE_FALLBACK_LEN",
                    "80",
                )
                try:
                    _max_title_len = max(20, min(int(_max_title_len_raw), 500))
                except ValueError:
                    _max_title_len = 80
                title = first_line[:_max_title_len] or "Untitled Note"
            # v0.7.81 — same dict-vs-Pydantic dual-path guard we apply to
            # other LangGraph ainvoke results (chat.py v0.7.52,
            # search.py v0.7.55, source_chat.py v0.7.56,
            # transformations.py v0.7.75). The prompt graph happens to
            # use a TypedDict today so `result` is a dict, but the
            # standing audit pattern in CLAUDE.md flags subscript /
            # `.get()` against ainvoke output as a state-shape blind
            # spot. Apply the dual-path now so a future LangGraph
            # release that returns a Pydantic state can't 500 the
            # note-create endpoint.
            # v0.7.95 — only execute the dual-path if we have a result
            # (timeout fallback already set `title`).
            if result is not None:
                if isinstance(result, dict):
                    title = result.get("output") or "Untitled Note"
                else:
                    title = getattr(result, "output", None) or "Untitled Note"

        # Validate note_type
        note_type: Optional[Literal["human", "ai"]] = None
        if note_data.note_type in ("human", "ai"):
            note_type = note_data.note_type  # type: ignore[assignment]
        elif note_data.note_type is not None:
            raise HTTPException(
                status_code=400, detail="note_type must be 'human' or 'ai'"
            )

        new_note = Note(
            title=title,
            content=note_data.content,
            note_type=note_type,
        )
        command_id = await new_note.save()

        # Add to notebook if specified
        if note_data.notebook_id:
            from deeper_notebook.domain.notebook import Notebook

            notebook = await Notebook.get(note_data.notebook_id)
            if not notebook:
                raise NotFoundError("Notebook not found")
            await new_note.add_to_notebook(note_data.notebook_id)

        return NoteResponse(
            id=new_note.id or "",
            title=new_note.title,
            content=new_note.content,
            note_type=new_note.note_type,
            # v0.7.181 — iso() for Safari new Date() compat.
            created=iso(new_note.created),
            updated=iso(new_note.updated),
            command_id=str(command_id) if command_id else None,
        )
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.201 — same bubble-pattern fix as list_notes; the
        # notebook_id-not-found case now raises NotFoundError instead
        # of HTTPException(404).
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating note: {str(e)}")
        raise HTTPException(status_code=500, detail="Error creating note")


@router.get("/notes/{note_id}", response_model=NoteResponse)
async def get_note(note_id: str):
    """Get a specific note by ID."""
    try:
        note = await Note.get(note_id)
        if not note:
            raise NotFoundError("Note not found")

        return NoteResponse(
            id=note.id or "",
            title=note.title,
            content=note.content,
            note_type=note.note_type,
            # v0.7.181 — iso() for Safari new Date() compat.
            created=iso(note.created),
            updated=iso(note.updated),
        )
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — Let the global handler at api/main.py:567 map this
        # to HTTP 404 instead of clobbering it to 500 via the generic
        # `except Exception` below. ObjectModel.get(id) raises
        # NotFoundError for missing records (see domain/base.py:183),
        # so a stale frontend cache hitting a deleted note used to
        # surface as "Server error" rather than "Note not found".
        raise
    except Exception as e:
        logger.error(f"Error fetching note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching note")


@router.put("/notes/{note_id}", response_model=NoteResponse)
async def update_note(note_id: str, note_update: NoteUpdate):
    """Update a note."""
    try:
        note = await Note.get(note_id)
        if not note:
            raise NotFoundError("Note not found")

        # Update only provided fields
        if note_update.title is not None:
            note.title = note_update.title
        if note_update.content is not None:
            note.content = note_update.content
        if note_update.note_type is not None:
            if note_update.note_type in ("human", "ai"):
                note.note_type = note_update.note_type  # type: ignore[assignment]
            else:
                raise HTTPException(
                    status_code=400, detail="note_type must be 'human' or 'ai'"
                )

        command_id = await note.save()

        return NoteResponse(
            id=note.id or "",
            title=note.title,
            content=note.content,
            note_type=note.note_type,
            # v0.7.181 — iso() for Safari new Date() compat.
            created=iso(note.created),
            updated=iso(note.updated),
            command_id=str(command_id) if command_id else None,
        )
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — same rationale as get_note: surface stale-ID 404
        # via the global handler instead of swallowing to 500.
        raise
    except ExternalNoteReadOnlyError:
        raise HTTPException(status_code=409, detail="external_note_read_only")
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating note")


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str):
    """Delete a note."""
    try:
        note = await Note.get(note_id)
        if not note:
            raise NotFoundError("Note not found")

        await note.delete()

        return {"message": "Note deleted successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — see get_note above.
        raise
    except ExternalNoteReadOnlyError:
        raise HTTPException(status_code=409, detail="external_note_read_only")
    except Exception as e:
        logger.error(f"Error deleting note {note_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting note")
