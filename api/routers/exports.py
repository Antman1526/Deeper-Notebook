"""ONP v0.7.90 — Notebook + note export to the host filesystem.

The Studio v0.7.89 feature now produces multi-page notebooks (overview
+ N per-topic pages, each with inline AI suggestions). Users want to
save that content out of the app and onto disk where they can version
it, share it, attach it to other tools (paperless-gpt, Logseq, etc.).

This module exposes two POST endpoints:

  * /notebooks/{id}/export — write the notebook to a folder (one .md
    per note) or a single .zip file
  * /notes/{id}/export — write one note to a single .md file

Both rely on the v0.7.90 filesystem router for path-safety validation
(`_resolve_and_validate`). The user picks the destination via the
filesystem-listing endpoints exposed at /fs/*.

Design choices:

  * Markdown is the universal export format. Every note in this app is
    Markdown-native; HTML/PDF rendering is out of scope here.
  * Folder layout (when format="folder"):
        {destination}/
            00-overview.md            # if a "📋 00 · …" overview note exists
            01-{slug}.md              # one per page note, in title-order
            02-{slug}.md
            …
            sources/                  # only if include_sources=True
                {source-id}.md        # source.full_text dumped as markdown
            manifest.json             # notebook + per-note metadata
  * Zip layout (when format="zip"):
        Same as folder but rolled into a single .zip file.
  * Filenames are slugified — the title `📄 01 · Architecture` becomes
    `01-architecture.md`. The slug logic is the SAME you'll find in
    Logseq / Obsidian / paperless: lowercase, ASCII, hyphenated.
  * The endpoint is idempotent under overwrite=True — re-running just
    rewrites the files. With overwrite=False the call 409s if any
    target file already exists.
  * Per-file writes are O(N); for a notebook with hundreds of notes,
    we stream the write rather than building the whole payload in
    memory.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from api.routers.filesystem import _resolve_and_validate
from open_notebook.domain.notebook import Note, Notebook, Source

router = APIRouter(tags=["exports"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class NotebookExportRequest(BaseModel):
    destination: str = Field(
        ...,
        description=(
            "Absolute path: a directory (for format='folder') or a .zip "
            "file path (for format='zip'). User's home is auto-expanded."
        ),
    )
    format: Literal["folder", "zip"] = "folder"
    include_sources: bool = Field(
        False,
        description="Include each Source's full_text as sources/{source-id}.md",
    )
    overwrite: bool = Field(
        False,
        description="Overwrite existing files / re-create existing folders.",
    )


class NoteExportRequest(BaseModel):
    destination: str = Field(
        ...,
        description=(
            "Absolute path of the .md file to write. Parent directory must "
            "already exist (use /api/fs/mkdir first if needed)."
        ),
    )
    overwrite: bool = False


class ExportFileEntry(BaseModel):
    relative_path: str
    bytes: int


class ExportResponse(BaseModel):
    destination: str            # final absolute path written
    format: str                 # "folder" | "zip" | "single"
    file_count: int             # number of files written (1 for note)
    total_bytes: int
    files: list[ExportFileEntry]  # per-file breakdown (capped at 100)
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Slug regex: keep ASCII alphanumeric + hyphens; everything else → hyphen.
_NON_SLUG = re.compile(r"[^a-z0-9]+")
# v0.7.90 — Strip leading numeric prefixes from titles before slugifying so
# v0.7.89 page titles like "📄 01 · Architecture" don't yield "01-architecture"
# and then get re-prefixed to "01-01-architecture.md". We catch:
#   - "NN " or "NN-" or "NN·" optionally followed by separators
#   - Up to 3 digits to allow page 100+ on huge notebooks
_LEADING_INDEX = re.compile(r"^[0-9]{1,3}[-\s·.]+")


def _slugify(text: str, *, fallback: str = "untitled") -> str:
    """Filesystem-safe slug. Strips emoji + non-ASCII via NFKD + ASCII
    encode. Matches the slug style used by Logseq / Obsidian so users
    can drop the exported folder into either without renaming.

    v0.7.90 — Strips leading numeric prefixes (`"01-"`, `"02 "`, etc.) so
    that pre-numbered titles don't end up double-prefixed when we wrap
    them in our own page-index. Without this, a v0.7.89 page titled
    `📄 01 · Architecture` would become `01-01-architecture.md`.
    """
    if not text:
        return fallback
    # Normalize unicode + drop non-ASCII (emoji, accents).
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = _NON_SLUG.sub("-", normalized.lower()).strip("-")
    # Repeatedly strip leading numeric prefixes (handles "01-01-arch" cases).
    while True:
        stripped = _LEADING_INDEX.sub("", slug).lstrip("-")
        if stripped == slug:
            break
        slug = stripped
    if not slug:
        return fallback
    # Cap to a reasonable filename length on macOS/Linux (255 bytes hard cap;
    # leave room for prefix + .md suffix).
    return slug[:80]


def _notebook_record_id_part(notebook_id: str) -> str:
    """Strip the 'notebook:' prefix from a SurrealDB record ID so the
    suffix is safe to use in filenames."""
    return notebook_id.split(":", 1)[1] if ":" in notebook_id else notebook_id


def _build_overview_path(note: Note) -> Optional[str]:
    """If this note looks like a v0.7.89 Overview note, return the
    canonical filename for it. Otherwise None and the caller will
    treat it as a regular page."""
    if not note.title:
        return None
    # v0.7.89 prefixes overview notes with "📋 00 · …"
    if note.title.startswith("📋 00") or "Overview" in note.title:
        return "00-overview.md"
    return None


def _note_filename(note: Note, *, index: int) -> str:
    """Generate a slugified filename for a non-overview note. Prefixed
    with a 2-digit index so the folder sorts in render order."""
    title = note.title or f"note-{index:02d}"
    return f"{index:02d}-{_slugify(title)}.md"


def _render_note_content(note: Note) -> str:
    """Build the full markdown for a single note: a frontmatter-style
    header with timestamps + note-type, then the body."""
    header_lines = [
        "---",
        f"title: {note.title or '(untitled)'}",
        f"type: {note.note_type or 'human'}",
    ]
    if getattr(note, "created", None):
        header_lines.append(f"created: {note.created}")
    if getattr(note, "updated", None):
        header_lines.append(f"updated: {note.updated}")
    if getattr(note, "id", None):
        header_lines.append(f"id: {note.id}")
    header_lines.append("---")
    header_lines.append("")
    body = note.content or "(no content)"
    return "\n".join(header_lines) + "\n" + body


def _render_source_content(source: Source) -> str:
    """Build markdown for a single Source — its title + full_text, with
    a metadata header pointing at the original asset."""
    asset_path = (
        source.asset.file_path if source.asset and source.asset.file_path else None
    )
    asset_url = (
        source.asset.url if source.asset and source.asset.url else None
    )
    header_lines = [
        "---",
        f"title: {source.title or '(untitled source)'}",
        f"source_id: {source.id}",
    ]
    if asset_path:
        header_lines.append(f"original_file: {asset_path}")
    if asset_url:
        header_lines.append(f"original_url: {asset_url}")
    header_lines.append("---")
    header_lines.append("")
    body = source.full_text or "(no extracted text)"
    return "\n".join(header_lines) + "\n" + body


def _build_manifest(
    notebook: Notebook, notes: list[Note], sources: list[Source],
) -> dict:
    """Manifest describes the export for downstream tools (Logseq importers,
    paperless ingestion, future "re-import into ONP" workflows)."""
    return {
        "open_notebook_plus_version": "0.7.90",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "notebook": {
            "id": str(notebook.id),
            "name": notebook.name,
            "description": notebook.description,
            "created": getattr(notebook, "created", None),
            "updated": getattr(notebook, "updated", None),
        },
        "notes": [
            {
                "id": str(n.id),
                "title": n.title,
                "type": n.note_type,
                "created": getattr(n, "created", None),
                "updated": getattr(n, "updated", None),
            }
            for n in notes
        ],
        "sources": [
            {
                "id": str(s.id),
                "title": s.title,
                "asset_path": s.asset.file_path if s.asset else None,
                "asset_url": s.asset.url if s.asset else None,
            }
            for s in sources
        ],
    }


def _check_overwrite(target: Path, *, overwrite: bool) -> None:
    """Refuse to overwrite without explicit consent. Raises 409 if the
    target exists and overwrite=False."""
    if target.exists() and not overwrite:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Target already exists: {target}. Pass overwrite=true to "
                "replace, or pick a different destination."
            ),
        )


def _plan_filenames(notes: list[Note]) -> list[tuple[str, Note]]:
    """Pick a filename for each note. The first overview-shaped note (if
    any) wins the canonical `00-overview.md`; everything else is indexed
    starting at 01.

    Returns a list of (filename, note) pairs in write order — overview
    first so it sorts to the top of any directory listing.
    """
    plan: list[tuple[str, Note]] = []
    overview_idx: Optional[int] = None
    for i, n in enumerate(notes):
        ov = _build_overview_path(n)
        if ov and overview_idx is None:
            plan.append((ov, n))
            overview_idx = i
    page_idx = 1
    for i, n in enumerate(notes):
        if i == overview_idx:
            continue
        plan.append((_note_filename(n, index=page_idx), n))
        page_idx += 1
    return plan


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/notebooks/{notebook_id}/export", response_model=ExportResponse)
async def export_notebook(
    notebook_id: str, req: NotebookExportRequest,
) -> ExportResponse:
    """Export a notebook's overview + all pages as markdown files.

    See module docstring for the on-disk layout. The endpoint is safe
    to re-run with overwrite=true; it produces the same output for the
    same notebook state.
    """
    notebook = await Notebook.get(notebook_id)
    if not notebook:
        raise HTTPException(status_code=404, detail=f"Notebook {notebook_id!r} not found")

    notes = await notebook.get_notes()
    if not notes and not req.include_sources:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Notebook {notebook.name!r} has no notes to export. Either add "
                "content first, or pass include_sources=true to export just the "
                "uploaded source documents."
            ),
        )

    sources: list[Source] = []
    if req.include_sources:
        sources = await notebook.get_sources()

    notes_sorted = sorted(notes, key=lambda n: (n.created or "", n.title or ""))
    plan = _plan_filenames(notes_sorted)
    manifest = _build_manifest(notebook, notes_sorted, sources)
    warnings: list[str] = []

    if req.format == "folder":
        target_dir = _resolve_and_validate(req.destination, must_exist=False)
        if target_dir.exists() and not target_dir.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Destination exists but is not a directory: {target_dir}",
            )
        # Create the target folder if missing.
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied creating {target_dir}: {exc}",
            )

        # Pre-flight overwrite check across all planned files. Better to
        # 409 BEFORE writing half the notebook than half-way through.
        if not req.overwrite:
            for filename, _ in plan:
                _check_overwrite(target_dir / filename, overwrite=False)
            if sources:
                for s in sources:
                    sid = _notebook_record_id_part(str(s.id))
                    _check_overwrite(
                        target_dir / "sources" / f"{sid}.md", overwrite=False,
                    )

        files_written: list[ExportFileEntry] = []
        total_bytes = 0

        for filename, note in plan:
            content = _render_note_content(note)
            payload = content.encode("utf-8")
            target = target_dir / filename
            try:
                target.write_bytes(payload)
            except OSError as exc:
                warnings.append(f"Could not write {filename}: {exc}")
                continue
            files_written.append(
                ExportFileEntry(relative_path=filename, bytes=len(payload))
            )
            total_bytes += len(payload)

        if sources:
            sources_dir = target_dir / "sources"
            sources_dir.mkdir(exist_ok=True)
            for s in sources:
                sid = _notebook_record_id_part(str(s.id))
                rel = f"sources/{sid}.md"
                content = _render_source_content(s)
                payload = content.encode("utf-8")
                try:
                    (sources_dir / f"{sid}.md").write_bytes(payload)
                except OSError as exc:
                    warnings.append(f"Could not write {rel}: {exc}")
                    continue
                files_written.append(
                    ExportFileEntry(relative_path=rel, bytes=len(payload))
                )
                total_bytes += len(payload)

        # Always write manifest last so partial exports are still readable.
        manifest_payload = json.dumps(manifest, indent=2).encode("utf-8")
        try:
            (target_dir / "manifest.json").write_bytes(manifest_payload)
            files_written.append(
                ExportFileEntry(relative_path="manifest.json", bytes=len(manifest_payload))
            )
            total_bytes += len(manifest_payload)
        except OSError as exc:
            warnings.append(f"Could not write manifest.json: {exc}")

        logger.info(
            "Notebook export: notebook={} files={} bytes={} → {}",
            notebook_id, len(files_written), total_bytes, str(target_dir),
        )
        return ExportResponse(
            destination=str(target_dir),
            format="folder",
            file_count=len(files_written),
            total_bytes=total_bytes,
            files=files_written[:100],
            warnings=warnings,
        )

    # format == "zip"
    target_zip = _resolve_and_validate(req.destination, must_exist=False)
    if target_zip.exists() and target_zip.is_dir():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Destination is a directory; pass a .zip file path for "
                f"format=zip: {target_zip}"
            ),
        )
    _check_overwrite(target_zip, overwrite=req.overwrite)
    # Parent directory must exist; we don't auto-create the parent for
    # zip exports because that's surprising — caller can /fs/mkdir first.
    if not target_zip.parent.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Parent directory does not exist: {target_zip.parent}. "
                "Create it via POST /api/fs/mkdir first."
            ),
        )

    files_written = []
    total_bytes = 0
    try:
        with zipfile.ZipFile(target_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for filename, note in plan:
                content = _render_note_content(note).encode("utf-8")
                zf.writestr(filename, content)
                files_written.append(
                    ExportFileEntry(relative_path=filename, bytes=len(content))
                )
                total_bytes += len(content)
            if sources:
                for s in sources:
                    sid = _notebook_record_id_part(str(s.id))
                    rel = f"sources/{sid}.md"
                    payload = _render_source_content(s).encode("utf-8")
                    zf.writestr(rel, payload)
                    files_written.append(
                        ExportFileEntry(relative_path=rel, bytes=len(payload))
                    )
                    total_bytes += len(payload)
            manifest_payload = json.dumps(manifest, indent=2).encode("utf-8")
            zf.writestr("manifest.json", manifest_payload)
            files_written.append(
                ExportFileEntry(relative_path="manifest.json", bytes=len(manifest_payload))
            )
            total_bytes += len(manifest_payload)
    except OSError as exc:
        # Clean up half-written zip so the user doesn't see a corrupted
        # archive on disk.
        try:
            if target_zip.exists():
                target_zip.unlink()
        except OSError:
            pass
        raise HTTPException(
            status_code=500, detail=f"Failed to write zip {target_zip}: {exc}",
        )

    logger.info(
        "Notebook export (zip): notebook={} files={} bytes={} → {}",
        notebook_id, len(files_written), total_bytes, str(target_zip),
    )
    return ExportResponse(
        destination=str(target_zip),
        format="zip",
        file_count=len(files_written),
        total_bytes=total_bytes,
        files=files_written[:100],
        warnings=warnings,
    )


@router.post("/notes/{note_id}/export", response_model=ExportResponse)
async def export_note(note_id: str, req: NoteExportRequest) -> ExportResponse:
    """Export a single note as a .md file."""
    note = await Note.get(note_id)
    if not note:
        raise HTTPException(status_code=404, detail=f"Note {note_id!r} not found")

    target = _resolve_and_validate(req.destination, must_exist=False)
    if target.exists() and target.is_dir():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Destination is a directory; pass a file path: {target}. "
                "Use /api/notebooks/{id}/export to export a whole notebook."
            ),
        )
    _check_overwrite(target, overwrite=req.overwrite)
    if not target.parent.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Parent directory does not exist: {target.parent}. "
                "Create it via POST /api/fs/mkdir first."
            ),
        )

    payload = _render_note_content(note).encode("utf-8")
    # Force .md extension if the user didn't include one — single-note
    # exports are always markdown.
    if target.suffix.lower() != ".md":
        target = target.with_suffix(".md")
        _check_overwrite(target, overwrite=req.overwrite)
    try:
        target.write_bytes(payload)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to write {target}: {exc}",
        )

    logger.info(
        "Note export: note={} bytes={} → {}",
        note_id, len(payload), str(target),
    )
    return ExportResponse(
        destination=str(target),
        format="single",
        file_count=1,
        total_bytes=len(payload),
        files=[ExportFileEntry(relative_path=os.path.basename(str(target)), bytes=len(payload))],
        warnings=[],
    )
