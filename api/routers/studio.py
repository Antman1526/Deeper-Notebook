"""ONP v0.7.0 — Studio: one-shot "upload + mode → output" workflow.

The Studio endpoint accepts one or more uploaded documents and turns them
into either a structured study notebook (markdown) or a generated podcast
episode. Everything created is persisted as real Notebook + Source +
Note/Episode records so the user can continue working with the result in
the normal app (chat with sources, regenerate, export, etc.).

Design rationale:
  * REUSES existing primitives wherever possible — content_core for file
    parsing, save_uploaded_file for the streamed-chunk write (v0.6.16
    hardened), provision_langchain_model for LLM selection, PodcastService
    for podcast generation, Notebook/Source/Note domain models for storage.
  * The ONLY new pieces are:
      - this router (workflow orchestration)
      - the study-notebook prompt template (NOTEBOOK_SYSTEM_PROMPT below)
      - the frontend page in /studio/
  * Single endpoint covers both modes — the mode form field dispatches
    inside. Async non-blocking for both modes (the LLM call is awaited
    via to_thread/ainvoke; podcast generation submits a background job).

Flow:
  1. Validate inputs (mode, file types, file sizes)
  2. Create Notebook (placeholder title if user didn't supply one)
  3. For each file:
       - Stream-save to UPLOADS_FOLDER (chunk-based, v0.6.16)
       - Create Source record, link to Notebook
       - Call content_core.extract_content() to parse the file → full_text
       - source.save() → fire-and-forget vectorize() for chat-with-sources
  4. Dispatch by mode:
       - notebook: render NOTEBOOK_SYSTEM_PROMPT with combined source text
                   → LLM ainvoke → save result as a Note attached to Notebook
       - podcast:  submit PodcastService.submit_generation_job() against
                   the just-created notebook_id; return job_id for polling
  5. Return notebook_id + mode-specific result fields so the frontend can
     navigate to /notebooks/{id} immediately and poll for podcast progress.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel

from api.podcast_service import PodcastService
from api.routers.sources import save_uploaded_file
from open_notebook.ai.provision import provision_langchain_model
from open_notebook.domain.notebook import Asset, Note, Notebook, Source
from open_notebook.exceptions import InvalidInputError
from open_notebook.utils.text_utils import (
    clean_thinking_content,
    extract_text_content,
)


router = APIRouter(prefix="/studio", tags=["studio"])


# Restrict uploads to formats content_core handles well. Defense-in-depth
# even though content_core itself attempts to extract anything; this list
# matches what the spec promises ("pdf/docx/txt/md/pptx/html").
_ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".txt", ".md", ".markdown",
    ".pptx", ".html", ".htm",
}

# Per-file cap (50 MB). Combined with Next.js's 100 MB proxy limit
# (frontend/next.config.ts), this prevents a single huge file from
# starving downstream LLM context window.
_MAX_FILE_BYTES = 50 * 1024 * 1024

# Per-source extracted-text cap. Above this we truncate before prompting —
# the LLM context window is finite and the goal is a study notebook, not
# a full transcript. Caller can split a huge document into multiple uploads.
_MAX_EXTRACT_CHARS_PER_FILE = 50_000

# Cap on the total combined context. Below the 105k-token large-context
# threshold so we don't accidentally trigger the large-context model
# upgrade in provision_langchain_model — which on a self-hosted setup may
# not actually be configured.
_MAX_COMBINED_CHARS = 200_000


# -----------------------------------------------------------------------------
# Prompt template — Notebook mode
# -----------------------------------------------------------------------------
# Inline rather than under prompts/ because the format is tightly coupled to
# the response-parsing logic below. If we ever expose this prompt as a
# customizable template, move it to prompts/studio/notebook.jinja.
NOTEBOOK_SYSTEM_PROMPT = """\
You are an expert educator creating a structured study notebook from the \
supplied source documents.

# Your task

Synthesize the source material into a single coherent study notebook with \
the following structure:

1. **Title** — a concise descriptive title (10 words or fewer), \
formatted as a Markdown `# H1`.
2. **Overview** — 3-5 sentence executive summary of what the material \
covers.
3. **Section-by-section breakdown** — for each major theme present in \
the sources:
   - A clear `## H2` section heading
   - Key concepts explained in your own words
   - Important definitions marked with **bold** for the term
   - Concrete examples drawn from the sources (with the source name cited)
4. **Key terms glossary** — alphabetized list of technical terms with \
definitions. Use `### H3` for this section.
5. **Review questions** — 5-10 questions of varying difficulty (factual \
recall, conceptual, applied). Mix open-ended and short-answer forms.

# Constraints

- **Stay faithful to the source.** Do NOT invent facts, dates, names, \
quotes, or statistics that aren't in the input.
- **Cite specific claims.** When you draw a specific claim from one of \
the sources, cite it inline like `(source: <filename>)` so the reader \
can verify.
- **Surface disagreements.** If the sources conflict on a point, note \
the disagreement explicitly rather than silently picking a side.
- **Don't pad.** If the sources are insufficient for a section, say so \
plainly — don't fill with general knowledge.
- **Output clean Markdown.** Use `##` for section headings, `**bold**` \
for definitions and key terms, `>` for direct quotes from sources.
- Aim for ~1500-3000 words. Shorter is fine for thin source material; \
do not pad to hit a length target.
"""


# -----------------------------------------------------------------------------
# Prompt template — Podcast mode briefing suffix
# -----------------------------------------------------------------------------
# Appended to the episode profile's briefing so the generated podcast stays
# focused on the user's documents rather than drifting into general
# conversation. Episode profiles already define the host personas + style.
PODCAST_BRIEFING_SUFFIX = """\
Stay strictly grounded in the user's uploaded source documents below. \
Do not invent statistics, dates, or attributions that aren't in the sources. \
If a topic touches a gap in the sources, say so on-air ("the docs don't \
actually tell us X") rather than filling it with general knowledge.
"""


# -----------------------------------------------------------------------------
# Request / response models
# -----------------------------------------------------------------------------


class StudioGenerateResponse(BaseModel):
    """Returned to the frontend after a Studio generation request.

    The frontend uses `notebook_id` to navigate to the result. For podcast
    mode, `job_id` lets the frontend poll /api/commands/{job_id} for
    transcription + audio rendering progress.
    """

    notebook_id: str
    mode: str  # "notebook" | "podcast"
    note_id: Optional[str] = None  # notebook mode: the generated study-doc Note
    job_id: Optional[str] = None  # podcast mode: surreal_commands job id
    source_ids: list[str]
    title: str
    warnings: list[str] = []  # non-fatal issues (e.g. a file couldn't be extracted)


# -----------------------------------------------------------------------------
# Endpoint
# -----------------------------------------------------------------------------


@router.post("/generate", response_model=StudioGenerateResponse)
async def studio_generate(
    files: List[UploadFile] = File(..., description="One or more documents to ingest"),
    mode: str = Form(..., description="'notebook' or 'podcast'"),
    title: Optional[str] = Form(None, description="Notebook title; auto-generated if absent"),
    episode_profile_name: Optional[str] = Form(
        None,
        description="Required for podcast mode — name of an EpisodeProfile record",
    ),
    speaker_profile_name: Optional[str] = Form(
        None,
        description="Required for podcast mode — name of a SpeakerProfile record",
    ),
) -> StudioGenerateResponse:
    """One-shot upload → generate. See module docstring for the full flow."""

    # 1. Validate inputs upfront so we don't half-create a notebook then fail.
    if mode not in ("notebook", "podcast"):
        raise HTTPException(status_code=400, detail="mode must be 'notebook' or 'podcast'")
    if not files:
        raise HTTPException(status_code=400, detail="at least one file is required")
    if mode == "podcast":
        if not episode_profile_name or not speaker_profile_name:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Podcast mode requires both episode_profile_name and "
                    "speaker_profile_name. Available profiles can be fetched "
                    "from /api/episode-profiles and /api/speaker-profiles."
                ),
            )

    for f in files:
        if not f.filename:
            raise HTTPException(status_code=400, detail="all files must have a filename")
        ext = Path(f.filename).suffix.lower()
        if ext and ext not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported file type {ext!r} for {f.filename!r}. "
                    f"Allowed: {sorted(_ALLOWED_EXTENSIONS)}"
                ),
            )
        # size validation (UploadFile.size is in newer FastAPI; defensive)
        size = getattr(f, "size", None)
        if size is not None and size > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"File {f.filename!r} is {size} bytes; per-file cap is "
                    f"{_MAX_FILE_BYTES} bytes (~{_MAX_FILE_BYTES // 1024 // 1024} MB)."
                ),
            )

    # 2. Title default — use the first file's stem if user didn't supply one.
    if not title:
        first = Path(files[0].filename or "Untitled").stem  # type: ignore[arg-type]
        title = f"Studio: {first[:80]}"

    # 3. Create the Notebook record.
    try:
        notebook = Notebook(
            name=title[:200],
            description=f"Generated via Studio from {len(files)} file(s); mode={mode}",
        )
        await notebook.save()
    except InvalidInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Studio: failed to create notebook")
        raise HTTPException(status_code=500, detail=f"Could not create notebook: {exc}")
    notebook_id = str(notebook.id)

    # 4. Per-file: save → Source → extract → link.
    source_ids: list[str] = []
    extracted: list[tuple[str, str]] = []  # (filename, parsed_text)
    warnings: list[str] = []

    # Lazy import to avoid pulling content_core into module load
    from content_core import extract_content
    from content_core.common import ProcessSourceState

    for upload in files:
        filename = upload.filename or "upload"
        try:
            saved_path = await save_uploaded_file(upload)
        except Exception as exc:
            logger.warning("Studio: save_uploaded_file failed for %r: %s", filename, exc)
            warnings.append(f"Could not save {filename!r}: {exc}")
            continue

        # Create + link the Source first so it's visible even if extract fails
        try:
            source = Source(
                title=Path(filename).name,
                asset=Asset(file_path=saved_path),
                topics=[],
            )
            await source.save()
            await source.add_to_notebook(notebook_id)
            source_ids.append(str(source.id))
        except Exception as exc:
            logger.warning("Studio: source create failed for %r: %s", filename, exc)
            warnings.append(f"Could not create source for {filename!r}: {exc}")
            continue

        # Extract content via content_core (handles pdf/docx/pptx/html/md/txt)
        try:
            cs = ProcessSourceState(file_path=saved_path, output_format="markdown")
            processed = await extract_content(cs)
            text = (processed.content or "").strip()
            if not text:
                warnings.append(
                    f"No text could be extracted from {filename!r} — the file "
                    "may be empty, image-only (no OCR), or in a corrupt state."
                )
                continue
            # Truncate per-file
            if len(text) > _MAX_EXTRACT_CHARS_PER_FILE:
                logger.info(
                    "Studio: truncating %r from %d → %d chars",
                    filename, len(text), _MAX_EXTRACT_CHARS_PER_FILE,
                )
                text = text[:_MAX_EXTRACT_CHARS_PER_FILE] + "\n\n[…truncated…]"
            extracted.append((filename, text))
            # Persist to source for later chat-with-sources access
            source.full_text = text
            if processed.title and not source.title:
                source.title = processed.title
            await source.save()
            # Fire-and-forget vectorize so chat can use it later
            try:
                await source.vectorize()
            except Exception as exc:
                logger.warning("Studio: vectorize failed (non-fatal) for %r: %s", filename, exc)
        except Exception as exc:
            logger.exception("Studio: extract_content failed for %r", filename)
            warnings.append(f"Could not parse {filename!r}: {exc}")

    if not extracted:
        # We created an empty notebook + maybe some empty sources. That's
        # actually a valid state (user can manually add content), but the
        # user explicitly asked for a generated output and we have nothing
        # to feed the LLM. Surface as a clear error.
        raise HTTPException(
            status_code=400,
            detail=(
                f"No usable text could be extracted from the {len(files)} uploaded "
                f"file(s). Notebook {notebook_id} was created and contains the "
                "uploaded source records (visible in the UI), but generation was "
                "skipped. Warnings: " + "; ".join(warnings)
            ),
        )

    # Build combined context — clearly delimited per-source so the LLM can
    # cite the right one.
    combined_chunks: list[str] = []
    running = 0
    for name, text in extracted:
        block = f"\n\n---\n\n# Source: {name}\n\n{text}"
        if running + len(block) > _MAX_COMBINED_CHARS:
            warnings.append(
                f"Combined context capped at {_MAX_COMBINED_CHARS:,} chars; "
                f"{name!r} and any subsequent sources were excluded from "
                "the LLM prompt. They're still saved as Sources on the notebook."
            )
            break
        combined_chunks.append(block)
        running += len(block)
    combined_context = "".join(combined_chunks).lstrip()

    # 5. Dispatch by mode.
    if mode == "notebook":
        return await _dispatch_notebook_mode(
            notebook=notebook,
            combined_context=combined_context,
            title=title,
            source_ids=source_ids,
            warnings=warnings,
        )
    else:  # mode == "podcast"
        return await _dispatch_podcast_mode(
            notebook_id=notebook_id,
            episode_profile_name=episode_profile_name,  # type: ignore[arg-type]
            speaker_profile_name=speaker_profile_name,  # type: ignore[arg-type]
            title=title,
            source_ids=source_ids,
            warnings=warnings,
        )


# -----------------------------------------------------------------------------
# Mode dispatchers
# -----------------------------------------------------------------------------


async def _dispatch_notebook_mode(
    *,
    notebook: Notebook,
    combined_context: str,
    title: str,
    source_ids: list[str],
    warnings: list[str],
) -> StudioGenerateResponse:
    """Notebook mode: render the study-notebook prompt, save the LLM response
    as a Note attached to the notebook."""
    try:
        chain = await provision_langchain_model(
            combined_context, None, "chat", max_tokens=8192,
        )
        # Provision returns a LangChain BaseChatModel; ainvoke is async.
        messages = [
            SystemMessage(content=NOTEBOOK_SYSTEM_PROMPT),
            HumanMessage(content=combined_context),
        ]
        response = await chain.ainvoke(messages)
        raw_text = extract_text_content(response.content)
        clean_text = clean_thinking_content(raw_text)
    except Exception as exc:
        # If the LLM call fails, the notebook + sources are still saved.
        # Surface the error but include notebook_id so the frontend can
        # navigate to it (user keeps the uploaded content).
        logger.exception("Studio notebook mode: LLM call failed")
        raise HTTPException(
            status_code=502,
            detail=(
                f"Generation failed: {exc}. Notebook {notebook.id} was created "
                f"and contains your {len(source_ids)} uploaded source(s). Try "
                "regenerating, or check Settings → Models for a working LLM."
            ),
        )

    # Save the generated study notebook as an AI-authored Note.
    try:
        note = Note(
            title=f"{title} — Study Notes",
            content=clean_text or "(empty response from model)",
            note_type="ai",
        )
        await note.save()
        await note.add_to_notebook(str(notebook.id))
    except Exception as exc:
        # Same recovery story — notebook + sources are saved; only the
        # generated note couldn't be persisted. Tell the user to retry.
        logger.exception("Studio notebook mode: could not save Note")
        raise HTTPException(
            status_code=500,
            detail=f"Generated content but could not save it: {exc}",
        )

    return StudioGenerateResponse(
        notebook_id=str(notebook.id),
        mode="notebook",
        note_id=str(note.id),
        source_ids=source_ids,
        title=title,
        warnings=warnings,
    )


async def _dispatch_podcast_mode(
    *,
    notebook_id: str,
    episode_profile_name: str,
    speaker_profile_name: str,
    title: str,
    source_ids: list[str],
    warnings: list[str],
) -> StudioGenerateResponse:
    """Podcast mode: submit a generation job against the just-created notebook.

    PodcastService.submit_generation_job handles the whole pipeline:
    pulls notebook context, runs outline → transcript → audio via the
    selected episode + speaker profiles, persists the Episode record,
    fires off TTS via the configured TTS model (Piper on desktop bundle).
    """
    try:
        job_id = await PodcastService.submit_generation_job(
            episode_profile_name=episode_profile_name,
            speaker_profile_name=speaker_profile_name,
            episode_name=title,
            notebook_id=notebook_id,
            briefing_suffix=PODCAST_BRIEFING_SUFFIX,
        )
    except HTTPException:
        # podcast_service raises HTTPException directly; re-raise so its
        # detail message reaches the client.
        raise
    except Exception as exc:
        logger.exception("Studio podcast mode: submit failed")
        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not submit podcast generation: {exc}. Notebook "
                f"{notebook_id} was created with your sources; you can retry "
                "from /podcasts."
            ),
        )

    return StudioGenerateResponse(
        notebook_id=notebook_id,
        mode="podcast",
        job_id=str(job_id),
        source_ids=source_ids,
        title=title,
        warnings=warnings,
    )


# `asyncio` is imported above for symmetry with other routers; nothing
# currently uses it here. Future: wrap synchronous ai_prompter Prompter
# in asyncio.to_thread if we move NOTEBOOK_SYSTEM_PROMPT to a Jinja file.
_ = asyncio  # silence linters about unused import
