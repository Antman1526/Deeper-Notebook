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

import asyncio  # v0.7.92 / v0.7.93 — wait_for + gather for parallel pages + timeouts
import csv
import html
import json
import os
import re
import zipfile
from io import StringIO
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel

from api.podcast_service import PodcastService
from api.routers.sources import save_uploaded_file
from api.schemas.studio import (
    StudioArtifactCreate,
    StudioArtifactResponse,
    StudioArtifactUpdate,
    StudioWorkflowRunCreate,
    StudioWorkflowRunResponse,
)
from open_notebook.ai.models import Model
from open_notebook.ai.provision import provision_langchain_model
from open_notebook.database.repository import ensure_record_id, repo_query
from open_notebook.domain.notebook import (
    Asset,
    Note,
    Notebook,
    Source,
    StudioArtifact,
    StudioWorkflowRun,
)
from open_notebook.exceptions import InvalidInputError, NotFoundError
from open_notebook.feature_flags import evidence_studio_enabled
from open_notebook.local_models.inventory import enumerate_models
from open_notebook.local_models.role_routing import (
    inventory_model_match_keys,
    model_match_key,
    recommend_model_roles,
)
from open_notebook.utils.text_utils import (
    clean_thinking_content,
    extract_text_content,
)

router = APIRouter(prefix="/studio", tags=["studio"])


def _require_evidence_studio() -> None:
    if not evidence_studio_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence Studio is not enabled",
        )


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _artifact_response(artifact: StudioArtifact) -> StudioArtifactResponse:
    return StudioArtifactResponse(
        id=str(artifact.id),
        notebook_id=str(artifact.notebook_id),
        artifact_type=artifact.artifact_type,
        title=artifact.title,
        status=artifact.status,
        source_ids=[str(source_id) for source_id in artifact.source_ids],
        prompt=artifact.prompt,
        model_id=artifact.model_id,
        provider=artifact.provider,
        output_format=artifact.output_format,
        output_payload=artifact.output_payload,
        citations=artifact.citations,
        export_paths=artifact.export_paths,
        revision_of_id=(
            str(artifact.revision_of_id) if artifact.revision_of_id is not None else None
        ),
        created=_iso(getattr(artifact, "created", None)),
        updated=_iso(getattr(artifact, "updated", None)),
    )


def _workflow_run_response(run: StudioWorkflowRun) -> StudioWorkflowRunResponse:
    return StudioWorkflowRunResponse(
        id=str(run.id),
        artifact_id=str(run.artifact_id),
        notebook_id=str(run.notebook_id),
        title=run.title,
        status=run.status,
        source_ids=[str(source_id) for source_id in run.source_ids],
        approval_required=run.approval_required,
        steps=run.steps,
        command_id=str(run.command_id) if run.command_id is not None else None,
        created=_iso(getattr(run, "created", None)),
        updated=_iso(getattr(run, "updated", None)),
    )


def _workflow_steps_for_artifact(
    artifact: StudioArtifact,
    *,
    approval_required: bool,
) -> list[dict[str, str]]:
    approval_status = "pending" if approval_required else "completed"
    model_status = "blocked" if approval_required else "pending"
    return [
        {"id": "context", "label": "Context built", "status": "completed"},
        {"id": "privacy_gate", "label": "Privacy gate", "status": approval_status},
        {
            "id": "model_route",
            "label": "Model route",
            "status": model_status,
        },
        {
            "id": "artifact_generation",
            "label": _artifact_type_label(artifact.artifact_type),
            "status": model_status,
        },
    ]


def _artifact_type_label(artifact_type: str) -> str:
    if artifact_type in {"course_pack", "training_guide"}:
        return "Course Pack"
    return artifact_type.replace("_", " ").title()


def _set_workflow_step_status(
    run: StudioWorkflowRun,
    step_ids: set[str],
    status_value: str,
) -> None:
    run.steps = [
        {
            **step,
            "status": status_value if step.get("id") in step_ids else step.get("status", "pending"),
        }
        for step in run.steps
    ]


async def _active_workflow_run_for_artifact(
    artifact_id: str,
) -> StudioWorkflowRun | None:
    try:
        runs = await StudioWorkflowRun.get_for_artifact(artifact_id)
    except Exception:
        logger.debug("Could not load Studio workflow runs for {}", artifact_id)
        return None

    active_statuses = {"queued", "awaiting_approval", "running"}
    return next((run for run in runs if run.status in active_statuses), None)


_ARTIFACT_TYPE_INSTRUCTIONS: dict[str, str] = {
    "report": (
        "Create a concise executive report with a title, summary, key findings, "
        "risks, recommendations, and open questions."
    ),
    "study_guide": (
        "Create a practical study guide with an overview, key concepts, glossary, "
        "review questions, and source-grounded examples."
    ),
    "course_pack": (
        "Create an instructor-ready Course Pack in markdown from the provided "
        "linked and uploaded source content. Include audience, learning outcomes, "
        "prerequisite knowledge, source readiness notes, a module roadmap, timed "
        "lesson blocks, hands-on exercises, facilitator notes, learner handouts, "
        "knowledge checks, a final assessment, source citations, and follow-up "
        "resources. Treat video and audio sources as lesson segments, PDFs and "
        "documents as readings or reference modules, and links as external "
        "resources or source-backed exercises. Warn when transcript/source text "
        "appears thin. Ground every substantive lesson point in citation markers."
    ),
    "training_guide": (
        "Create an instructor-ready Course Pack in markdown from the provided "
        "linked and uploaded source content. Include audience, learning outcomes, "
        "prerequisite knowledge, source readiness notes, a module roadmap, timed "
        "lesson blocks, hands-on exercises, facilitator notes, learner handouts, "
        "knowledge checks, a final assessment, source citations, and follow-up "
        "resources. Treat video and audio sources as lesson segments, PDFs and "
        "documents as readings or reference modules, and links as external "
        "resources or source-backed exercises. Warn when transcript/source text "
        "appears thin. Ground every substantive lesson point in citation markers. "
        "This artifact type is a legacy alias for Course Pack."
    ),
    "briefing": (
        "Create a short briefing with the essential facts, implications, and "
        "recommended next actions."
    ),
    "faq": "Create a source-grounded FAQ with direct, useful answers.",
    "timeline": "Create a chronological timeline of source-backed events and milestones.",
    "flashcards": (
        "Create source-grounded flashcards in markdown. Each card must include "
        "a front prompt, a back answer, and the source title that supports it."
    ),
    "quiz": (
        "Create a source-grounded quiz in markdown with multiple-choice questions, "
        "an answer key, and short explanations tied to the cited sources."
    ),
    "data_table": (
        "Create a source-grounded Data Table in markdown. Return one concise "
        "markdown table with columns for Topic, Evidence, Source, Confidence, "
        "and Notes. Every evidence cell must include a source marker such as "
        "[S1]. Prefer comparable facts, dates, claims, numbers, entities, or "
        "decisions that help a reader scan the sources like a spreadsheet."
    ),
    "mind_map": (
        "Create a source-grounded mind map as a nested markdown outline. Start "
        "with a central concept, group related branches beneath it, name the "
        "relationships between branches, and cite source markers on each major "
        "node."
    ),
    "slide_deck": (
        "Create a source-grounded slide deck outline in markdown. Include a "
        "title slide, 5-8 numbered slides, concise slide bullets, speaker notes "
        "for each slide, and citation markers for source-backed claims."
    ),
    "infographic": (
        "Create a source-grounded infographic brief in markdown. Organize it "
        "into clear visual sections, include hierarchy, labels, data callouts, "
        "caption text, and citation markers for each major claim."
    ),
    "podcast_outline": (
        "Create a source-grounded podcast outline for an audio overview in "
        "markdown. Include a cold open, host segments, key beats, transitions, "
        "listener takeaways, questions for discussion, and citation markers for "
        "source-backed claims."
    ),
    "research_run": (
        "Create a source-grounded Research Run in markdown. Treat it as a "
        "multi-step investigation: state the research objective, list working "
        "hypotheses, extract evidence-backed findings, identify contradictions "
        "or gaps, propose follow-up questions, and end with recommended next "
        "actions. Use citation markers on every evidence-backed claim."
    ),
}


def _artifact_instruction(artifact: StudioArtifact) -> str:
    base = _ARTIFACT_TYPE_INSTRUCTIONS.get(
        artifact.artifact_type,
        "Create a useful source-grounded markdown artifact.",
    )
    if artifact.prompt:
        return f"{base}\n\nUser steering prompt:\n{artifact.prompt}"
    return base


_ARTIFACT_TYPE_MODEL_ROLE: dict[str, str] = {
    "report": "source_synthesis",
    "study_guide": "source_synthesis",
    "course_pack": "source_synthesis",
    "training_guide": "source_synthesis",
    "briefing": "source_synthesis",
    "faq": "source_synthesis",
    "timeline": "source_synthesis",
    "data_table": "source_synthesis",
    "mind_map": "source_synthesis",
    "infographic": "source_synthesis",
    "slide_deck": "source_synthesis",
    "podcast_outline": "source_synthesis",
    "research_run": "source_synthesis",
    "flashcards": "study_fast",
    "quiz": "study_fast",
}

_COURSE_PACK_ARTIFACT_TYPES = {"course_pack", "training_guide"}


def _artifact_model_role(artifact_type: str) -> str:
    return _ARTIFACT_TYPE_MODEL_ROLE.get(artifact_type, "chat")


def _configured_model_dir() -> Path | None:
    raw = (
        os.environ.get("OPEN_NOTEBOOK_MODEL_DIR")
        or os.environ.get("OPEN_NOTEBOOK_MODEL_DIR_DEFAULT")
        or ""
    ).strip()
    if not raw:
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
        raw = str(Path(home) / "Desktop" / "AI_Models") if home else ""
    if not raw:
        return None
    model_dir = Path(raw)
    return model_dir if model_dir.exists() and model_dir.is_dir() else None


async def _resolve_artifact_model_route(
    artifact: StudioArtifact,
) -> tuple[str | None, str | None]:
    """Return the model id/provider to use for artifact generation.

    Manual artifact.model_id remains authoritative. Auto-routing is deliberately
    conservative: inventory recommendations only become actionable when the
    recommended local file can be matched to a registered language model.
    """
    if artifact.model_id:
        return artifact.model_id, artifact.provider

    model_dir = _configured_model_dir()
    if model_dir is None:
        return None, artifact.provider

    role = _artifact_model_role(artifact.artifact_type)
    try:
        local_models = await asyncio.to_thread(enumerate_models, model_dir)
        routes = await asyncio.to_thread(recommend_model_roles, local_models)
        route = next((item for item in routes if item.role == role), None)
        if route is None or route.model is None:
            return None, artifact.provider

        match_keys = inventory_model_match_keys(route.model.name, route.model.path)
        registered_models = await Model.get_models_by_type("language")
    except Exception as exc:
        logger.debug("Evidence Studio role routing skipped: {}", exc)
        return None, artifact.provider

    for model in registered_models:
        if model_match_key(getattr(model, "name", "")) in match_keys:
            model_id = str(getattr(model, "id", "") or "")
            if model_id:
                return model_id, getattr(model, "provider", None) or artifact.provider

    return None, artifact.provider


def _has_generated_output(artifact: StudioArtifact) -> bool:
    return bool(artifact.output_payload) or bool(artifact.citations) or bool(artifact.export_paths)


async def _snapshot_artifact_revision(artifact: StudioArtifact) -> None:
    if artifact.status != "completed" or not _has_generated_output(artifact):
        return

    revision = StudioArtifact(
        notebook_id=str(artifact.notebook_id),
        artifact_type=artifact.artifact_type,
        title=f"{artifact.title} revision",
        status="completed",
        source_ids=[str(source_id) for source_id in artifact.source_ids],
        prompt=artifact.prompt,
        model_id=artifact.model_id,
        provider=artifact.provider,
        output_format=artifact.output_format,
        output_payload=dict(artifact.output_payload),
        citations=[dict(citation) for citation in artifact.citations],
        export_paths=dict(artifact.export_paths),
        revision_of_id=str(artifact.id),
    )
    await revision.save()


async def _artifact_sources(artifact: StudioArtifact) -> list[Source]:
    if artifact.source_ids:
        sources: list[Source] = []
        for source_id in artifact.source_ids:
            try:
                sources.append(await Source.get(source_id))
            except (KeyError, NotFoundError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Source not found: {source_id}",
                ) from exc
        return sources

    try:
        notebook = await Notebook.get(artifact.notebook_id)
    except (KeyError, NotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook not found: {artifact.notebook_id}",
        ) from exc
    return await notebook.get_sources()


async def _notebook_record_exists(notebook_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM $notebook_id LIMIT 1",
        {"notebook_id": ensure_record_id(notebook_id)},
    )
    return bool(rows)


def _citation_preview(text: str, limit: int = 280) -> str:
    preview = " ".join(text.split())
    if len(preview) <= limit:
        return preview
    return preview[: limit - 1].rstrip() + "…"


def _artifact_export_dir() -> Path:
    raw = os.environ.get("OPEN_NOTEBOOK_ARTIFACT_EXPORT_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()

    home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
    if home:
        return (
            Path(home)
            / "BrainPulseKnowledge"
            / "open-notebook-plus-imports"
            / "evidence-studio"
        )
    return Path.cwd() / "open-notebook-plus-imports" / "evidence-studio"


def _artifact_export_slug(value: object, *, fallback: str) -> str:
    text = str(value or "").strip().lower()
    chars: list[str] = []
    previous_dash = False
    for char in text:
        if char.isalnum():
            chars.append(char)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    slug = "".join(chars).strip("-")
    return slug or fallback


def _artifact_export_path(export_dir: Path, stem: str, suffix: str) -> Path:
    candidate = export_dir / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate

    for index in range(2, 1000):
        candidate = export_dir / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not allocate export path for {stem}{suffix}")


def _artifact_markdown_export(artifact: StudioArtifact, content: str) -> str:
    source_ids = [str(source_id) for source_id in artifact.source_ids]
    lines = [
        "---",
        f"artifact_id: {json.dumps(str(artifact.id), ensure_ascii=False)}",
        f"notebook_id: {json.dumps(str(artifact.notebook_id), ensure_ascii=False)}",
        f"title: {json.dumps(artifact.title, ensure_ascii=False)}",
        f"artifact_type: {json.dumps(artifact.artifact_type, ensure_ascii=False)}",
        f"status: {json.dumps(artifact.status, ensure_ascii=False)}",
        "source_ids:",
    ]
    if source_ids:
        lines.extend(f"  - {json.dumps(source_id, ensure_ascii=False)}" for source_id in source_ids)
    else:
        lines[-1] = "source_ids: []"
    lines.extend(["---", "", content.strip(), ""])

    if artifact.citations:
        lines.extend(["", "## Stored Citations", ""])
        for citation in artifact.citations:
            title = citation.get("title") or citation.get("source_id") or "Untitled source"
            source_id = citation.get("source_id") or ""
            marker = citation.get("marker") or ""
            preview = citation.get("preview") or ""
            marker_label = f" {marker}" if marker else ""
            lines.append(f"- **{title}**{marker_label} (`{source_id}`): {preview}")
        lines.append("")

    return "\n".join(lines)


def _strip_artifact_markdown_line(line: str) -> str:
    text = line.strip()
    while text.startswith("#"):
        text = text[1:].lstrip()
    for prefix in ("- ", "* "):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    return text.replace("**", "").strip()


def _research_run_stages(content: str) -> list[dict[str, object]]:
    stages: list[dict[str, object]] = []
    current_title = ""
    current_items: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_items
        if current_title and current_items:
            stages.append({"title": current_title, "items": current_items})
        current_title = ""
        current_items = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("##"):
            flush()
            current_title = _strip_artifact_markdown_line(line)
            continue
        if current_title:
            item = _strip_artifact_markdown_line(line)
            if item:
                current_items.append(item)

    flush()
    return stages


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    cells = stripped.strip("|").split("|")
    return [_strip_artifact_markdown_line(cell).strip() for cell in cells]


def _is_markdown_table_separator(cells: list[str]) -> bool:
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _data_table_rows(content: str) -> list[dict[str, str]]:
    header: list[str] = []
    rows: list[dict[str, str]] = []

    for raw_line in content.splitlines():
        cells = _split_markdown_table_row(raw_line)
        if not cells:
            if rows:
                break
            continue
        if _is_markdown_table_separator(cells):
            continue
        if not header:
            header = [cell or f"Column {index + 1}" for index, cell in enumerate(cells)]
            continue
        normalized = {
            header[index] if index < len(header) else f"Column {index + 1}": cell
            for index, cell in enumerate(cells)
        }
        if any(value for value in normalized.values()):
            rows.append(normalized)

    return rows


def _data_table_csv(content: str) -> str:
    rows = _data_table_rows(content)
    if not rows:
        return ""

    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _markdown_heading_level(line: str) -> int:
    match = re.match(r"^(#{1,6})\s+", line.strip())
    return len(match.group(1)) if match else 0


def _markdown_heading_title(line: str) -> str:
    return _strip_artifact_markdown_line(line)


def _course_pack_modules(content: str) -> list[dict[str, object]]:
    modules: list[dict[str, object]] = []
    current_title = ""
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_title, current_lines
        if not current_title:
            return
        summary = next(
            (
                _strip_artifact_markdown_line(line)
                for line in current_lines
                if _strip_artifact_markdown_line(line)
                and not _strip_artifact_markdown_line(line).lower().startswith((
                    "learner handout",
                    "hands-on exercise",
                    "knowledge check",
                    "facilitator notes",
                    "instructor notes",
                ))
            ),
            "",
        )
        module_content = "\n".join(current_lines)
        modules.append({
            "title": current_title,
            "summary": summary,
            "has_facilitator_notes": bool(
                re.search(
                    r"(facilitator notes?|instructor notes?|demo script)",
                    module_content,
                    re.IGNORECASE,
                )
            ),
        })
        current_title = ""
        current_lines = []

    for raw_line in content.splitlines():
        title = _markdown_heading_title(raw_line)
        if _markdown_heading_level(raw_line) in {2, 3} and re.match(
            r"module\s*\d*(?:[:\-.]\s*)?",
            title,
            re.IGNORECASE,
        ):
            flush()
            current_title = title
            current_lines = []
            continue
        if current_title:
            current_lines.append(raw_line)

    flush()
    return modules


def _course_pack_learner_markdown(content: str) -> str:
    visible: list[str] = []
    hidden_level = 0

    for raw_line in content.splitlines():
        level = _markdown_heading_level(raw_line)
        title = _markdown_heading_title(raw_line)
        if level:
            hidden_level = 0
            if re.search(
                r"(facilitator notes?|instructor notes?|demo script)",
                title,
                re.IGNORECASE,
            ):
                hidden_level = level
                continue
        if hidden_level:
            if level and level <= hidden_level:
                hidden_level = 0
            else:
                continue
        visible.append(raw_line)

    return "\n".join(visible).strip()


def _course_pack_assessment_markdown(content: str) -> str:
    selected: list[str] = []
    collecting_level = 0

    for raw_line in content.splitlines():
        level = _markdown_heading_level(raw_line)
        title = _markdown_heading_title(raw_line)
        if level:
            if collecting_level and level <= collecting_level:
                collecting_level = 0
            if re.search(
                r"(knowledge check|assessment|quiz|final assessment)",
                title,
                re.IGNORECASE,
            ):
                collecting_level = level
                selected.append(raw_line)
                continue
        if collecting_level:
            selected.append(raw_line)

    body = "\n".join(selected).strip()
    if body:
        return "# Course Pack Assessment\n\n" + body + "\n"
    return "# Course Pack Assessment\n\nNo dedicated assessment sections were generated.\n"


def _citation_warnings(
    content: str,
    citations: list[dict[str, str]] | None,
) -> dict[str, list[str]]:
    valid_markers = {
        str(citation.get("marker"))
        for citation in (citations or [])
        if citation.get("marker")
    }
    seen_markers = set(re.findall(r"\[S[1-9]\d*\]", content))
    unsupported_markers = sorted(
        seen_markers - valid_markers,
        key=lambda marker: int(marker.removeprefix("[S").removesuffix("]")),
    )
    warnings: dict[str, list[str]] = {}
    if unsupported_markers:
        warnings["unsupported_markers"] = unsupported_markers
    return warnings


def _artifact_output_payload(
    artifact: StudioArtifact,
    content: str,
    citations: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {"content": content}
    if artifact.artifact_type == "data_table":
        rows = _data_table_rows(content)
        if rows:
            payload["data_table_rows"] = rows
    if artifact.artifact_type == "research_run":
        stages = _research_run_stages(content)
        if stages:
            payload["research_stages"] = stages
    if artifact.artifact_type in _COURSE_PACK_ARTIFACT_TYPES:
        modules = _course_pack_modules(content)
        if modules:
            payload["course_pack_modules"] = modules
    citation_warnings = _citation_warnings(content, citations)
    if citation_warnings:
        payload["citation_warnings"] = citation_warnings
    return payload


def _course_pack_checklist_export(artifact: StudioArtifact, modules: list[dict[str, object]]) -> dict[str, object]:
    return {
        "artifact_id": str(artifact.id),
        "notebook_id": str(artifact.notebook_id),
        "title": artifact.title,
        "artifact_type": artifact.artifact_type,
        "modules": [
            {
                "title": module["title"],
                "summary": module.get("summary", ""),
                "has_facilitator_notes": module.get("has_facilitator_notes", False),
                "complete": False,
            }
            for module in modules
        ],
    }


def _course_pack_lms_index_html(
    artifact: StudioArtifact,
    content: str,
    modules: list[dict[str, object]],
) -> str:
    module_items = "\n".join(
        f"<li>{html.escape(str(module['title']))}</li>"
        for module in modules
    ) or "<li>Course Pack content</li>"
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8" />',
        f"  <title>{html.escape(artifact.title)}</title>",
        '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
        "  <style>",
        "    body { font-family: system-ui, sans-serif; line-height: 1.55; margin: 2rem; max-width: 920px; }",
        "    pre { white-space: pre-wrap; border: 1px solid #ddd; padding: 1rem; overflow-wrap: anywhere; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>{html.escape(artifact.title)}</h1>",
        "  <p>Open Notebook Plus Course Pack export.</p>",
        "  <h2>Modules</h2>",
        f"  <ol>{module_items}</ol>",
        "  <h2>Course Pack Markdown</h2>",
        f"  <pre>{html.escape(content)}</pre>",
        "</body>",
        "</html>",
        "",
    ])


def _course_pack_scorm_manifest(artifact: StudioArtifact) -> str:
    identifier = html.escape(_artifact_export_slug(artifact.id, fallback="course-pack"))
    title = html.escape(artifact.title)
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<manifest identifier="{identifier}" version="1.0"',
        '  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"',
        '  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">',
        "  <metadata>",
        "    <schema>ADL SCORM</schema>",
        "    <schemaversion>1.2</schemaversion>",
        "  </metadata>",
        "  <organizations default=\"open-notebook-plus-course-pack\">",
        "    <organization identifier=\"open-notebook-plus-course-pack\">",
        f"      <title>{title}</title>",
        "      <item identifier=\"course-pack-launch\" identifierref=\"course-pack-resource\">",
        f"        <title>{title}</title>",
        "      </item>",
        "    </organization>",
        "  </organizations>",
        "  <resources>",
        "    <resource identifier=\"course-pack-resource\" type=\"webcontent\" adlcp:scormtype=\"sco\" href=\"index.html\">",
        "      <file href=\"index.html\" />",
        "      <file href=\"instructor-guide.md\" />",
        "      <file href=\"learner-handout.md\" />",
        "      <file href=\"module-checklist.json\" />",
        "      <file href=\"assessment.md\" />",
        "    </resource>",
        "  </resources>",
        "</manifest>",
        "",
    ])


def _course_pack_tincan_xml(artifact: StudioArtifact) -> str:
    title = html.escape(artifact.title)
    activity_id = html.escape(f"urn:open-notebook-plus:{artifact.id}")
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<tincan xmlns="http://projecttincan.com/tincan.xsd">',
        "  <activities>",
        f'    <activity id="{activity_id}" type="http://adlnet.gov/expapi/activities/course">',
        f"      <name>{title}</name>",
        "      <description>Open Notebook Plus Course Pack export.</description>",
        "      <launch lang=\"en-US\">index.html</launch>",
        "    </activity>",
        "  </activities>",
        "</tincan>",
        "",
    ])


def _course_pack_xapi_statements(
    artifact: StudioArtifact,
    modules: list[dict[str, object]],
) -> dict[str, object]:
    activity_id = f"urn:open-notebook-plus:{artifact.id}"
    return {
        "activity": {
            "id": activity_id,
            "name": artifact.title,
            "type": "http://adlnet.gov/expapi/activities/course",
        },
        "actor_placeholder": {
            "objectType": "Agent",
            "name": "Learner Name",
            "mbox": "mailto:learner@example.com",
        },
        "verbs": {
            "launched": "http://adlnet.gov/expapi/verbs/launched",
            "completed": "http://adlnet.gov/expapi/verbs/completed",
            "answered": "http://adlnet.gov/expapi/verbs/answered",
        },
        "modules": modules,
    }


def _write_course_pack_lms_packages(
    *,
    artifact: StudioArtifact,
    content: str,
    modules: list[dict[str, object]],
    scorm_path: Path,
    xapi_path: Path,
    assets: dict[str, Path],
) -> None:
    index_html = _course_pack_lms_index_html(artifact, content, modules)

    with zipfile.ZipFile(scorm_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("imsmanifest.xml", _course_pack_scorm_manifest(artifact))
        package.writestr("index.html", index_html)
        for arcname, path in assets.items():
            package.write(path, arcname)

    with zipfile.ZipFile(xapi_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("tincan.xml", _course_pack_tincan_xml(artifact))
        package.writestr("index.html", index_html)
        package.writestr(
            "xapi-statements.json",
            json.dumps(
                _course_pack_xapi_statements(artifact, modules),
                ensure_ascii=False,
                indent=2,
            ),
        )
        for arcname, path in assets.items():
            package.write(path, arcname)


def _persist_artifact_exports(artifact: StudioArtifact, content: str) -> dict[str, str]:
    export_dir = _artifact_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)

    artifact_slug = _artifact_export_slug(artifact.id, fallback="artifact")
    title_slug = _artifact_export_slug(artifact.title, fallback=artifact.artifact_type)
    stem = f"{artifact_slug}-{title_slug}"

    markdown_path = _artifact_export_path(export_dir, stem, ".md")
    json_path = _artifact_export_path(export_dir, stem, ".json")
    export_paths = {
        "markdown": str(markdown_path),
        "json": str(json_path),
    }
    course_pack_modules = _course_pack_modules(content)
    if artifact.artifact_type in _COURSE_PACK_ARTIFACT_TYPES:
        instructor_path = _artifact_export_path(export_dir, f"{stem}-instructor-guide", ".md")
        learner_path = _artifact_export_path(export_dir, f"{stem}-learner-handout", ".md")
        checklist_path = _artifact_export_path(export_dir, f"{stem}-module-checklist", ".json")
        assessment_path = _artifact_export_path(export_dir, f"{stem}-assessment", ".md")
        scorm_path = _artifact_export_path(export_dir, f"{stem}-scorm", ".zip")
        xapi_path = _artifact_export_path(export_dir, f"{stem}-xapi", ".zip")
        export_paths.update({
            "instructor_guide": str(instructor_path),
            "learner_handout": str(learner_path),
            "module_checklist": str(checklist_path),
            "assessment": str(assessment_path),
            "scorm_package": str(scorm_path),
            "xapi_package": str(xapi_path),
        })
    data_table_csv = _data_table_csv(content) if artifact.artifact_type == "data_table" else ""
    if data_table_csv:
        csv_path = _artifact_export_path(export_dir, f"{stem}-data-table", ".csv")
        export_paths["csv"] = str(csv_path)
    artifact.export_paths = export_paths
    markdown_path.write_text(_artifact_markdown_export(artifact, content), encoding="utf-8")
    if data_table_csv:
        csv_path.write_text(data_table_csv, encoding="utf-8")
    if artifact.artifact_type in _COURSE_PACK_ARTIFACT_TYPES:
        instructor_path.write_text(
            _artifact_markdown_export(artifact, content),
            encoding="utf-8",
        )
        learner_path.write_text(
            _artifact_markdown_export(artifact, _course_pack_learner_markdown(content)),
            encoding="utf-8",
        )
        checklist_path.write_text(
            json.dumps(
                _course_pack_checklist_export(artifact, course_pack_modules),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        assessment_path.write_text(
            _artifact_markdown_export(artifact, _course_pack_assessment_markdown(content)),
            encoding="utf-8",
        )
        _write_course_pack_lms_packages(
            artifact=artifact,
            content=content,
            modules=course_pack_modules,
            scorm_path=scorm_path,
            xapi_path=xapi_path,
            assets={
                "instructor-guide.md": instructor_path,
                "learner-handout.md": learner_path,
                "module-checklist.json": checklist_path,
                "assessment.md": assessment_path,
            },
        )
    json_path.write_text(
        json.dumps(_artifact_response(artifact).model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return export_paths


def _artifact_context(sources: list[Source]) -> tuple[str, list[dict[str, str]]]:
    blocks: list[str] = []
    citations: list[dict[str, str]] = []
    for index, source in enumerate(sources, start=1):
        text = (getattr(source, "full_text", None) or "").strip()
        if not text:
            continue
        marker = f"[S{index}]"
        source_id = str(getattr(source, "id", ""))
        title = getattr(source, "title", None) or source_id or "Untitled source"
        citations.append({
            "source_id": source_id,
            "title": title,
            "marker": marker,
            "location": f"Source {marker}",
            "preview": _citation_preview(text),
        })
        blocks.append(
            f"## Source {marker}: {title}\n"
            f"Source ID: {source_id}\n\n"
            f"{text[:_MAX_EXTRACT_CHARS_PER_FILE]}"
        )
    return "\n\n---\n\n".join(blocks), citations


def _artifact_not_ready_sources(sources: list[Source]) -> list[dict[str, str | None]]:
    not_ready: list[dict[str, str | None]] = []
    for source in sources:
        text = (getattr(source, "full_text", None) or "").strip()
        if text:
            continue
        command = getattr(source, "command", None)
        not_ready.append({
            "source_id": str(getattr(source, "id", "")),
            "title": getattr(source, "title", None) or "Untitled source",
            "command_id": str(command) if command is not None else None,
        })
    return not_ready


# Restrict uploads to formats content_core handles well. Defense-in-depth
# even though content_core itself attempts to extract anything; this list
# matches what the spec promises for documents and common training media.
_ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".doc", ".docx", ".txt", ".md", ".markdown",
    ".ppt", ".pptx", ".html", ".htm",
    ".mp3", ".mp4", ".m4a", ".wav", ".mov",
}

_MAX_STUDIO_LINKS = 20

# Per-file cap (50 MB). Combined with Next.js's 100 MB proxy limit
# (frontend/next.config.ts), this prevents a single huge file from
# starving downstream LLM context window.
_MAX_FILE_BYTES = 50 * 1024 * 1024


def _normalize_studio_links(raw_links: list[str] | None) -> list[str]:
    if not raw_links:
        return []

    expanded: list[str] = []
    for raw in raw_links:
        value = (raw or "").strip()
        if not value:
            continue
        if value.startswith("["):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                decoded = None
            if isinstance(decoded, list):
                expanded.extend(str(item).strip() for item in decoded)
                continue
        expanded.extend(part.strip() for part in re.split(r"[\n,]+", value))

    deduped: list[str] = []
    seen: set[str] = set()
    for link in expanded:
        if not link or link in seen:
            continue
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid Studio link {link!r}; use a full http(s) URL.",
            )
        seen.add(link)
        deduped.append(link)

    if len(deduped) > _MAX_STUDIO_LINKS:
        raise HTTPException(
            status_code=400,
            detail=f"Studio supports up to {_MAX_STUDIO_LINKS} links per generation.",
        )
    return deduped


def _studio_link_title(link: str) -> str:
    parsed = urlparse(link)
    path = parsed.path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else ""
    return tail or parsed.netloc or link


# v0.7.4 — Per-source / combined caps tuned for LOCAL MODEL deployments.
#
# ONP is documented as "privacy-focused, self-hosted alternative to Notebook
# LM" — the typical deployment runs llama-cpp-python locally with 7B-9B
# models at 8k-32k context. The previous v0.7.0 defaults (50k per-file,
# 200k combined) were cloud-sized: ~50k tokens, fine for GPT-4 / Claude /
# Gemini but overflowing a Hermes-3 / Qwen 2.5 7B at 8k context.
#
# New defaults (per char ≈ 0.25 tokens):
#   - per-file: 15,000 chars ≈ 3,750 tokens
#   - combined: 60,000 chars ≈ 15,000 tokens
#
# That leaves room for the ~1k-token system prompt and an 8k-token output
# budget within a 32k-context model — and degrades gracefully (input
# truncated, output capped) on 8k-context models too.
#
# Cloud users can opt out via env vars; the defaults still produce useful
# study notebooks for any single-document upload up to ~15 KB of text.
def _env_int(name: str, default: int) -> int:
    """Read a positive int from env; fall back to default on missing/invalid."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        if value < 1:
            raise ValueError
        return value
    except ValueError:
        # Don't crash startup over a bad env var; fall back loudly.
        import logging
        logging.getLogger(__name__).warning(
            "Invalid %s=%r; using default %d", name, raw, default,
        )
        return default


# Defaults sized for local 7B-9B models with 8k-32k context. Cloud users
# can raise these via env vars (e.g. ONP_STUDIO_MAX_COMBINED_CHARS=200000).
_MAX_EXTRACT_CHARS_PER_FILE = _env_int(
    "ONP_STUDIO_MAX_FILE_CHARS", 15_000,
)
_MAX_COMBINED_CHARS = _env_int(
    "ONP_STUDIO_MAX_COMBINED_CHARS", 60_000,
)

# v0.7.1 — Cap warning-message length. Parser libraries (PyMuPDF, mammoth)
# can produce KB-long error strings with paths and partial stack traces.
# 200 chars matches api/routers/gmail.py:406 — long enough to identify
# the cause, short enough to keep response payloads small and avoid
# leaking deep path info to the client.
_MAX_WARNING_LEN = 200


def _brief(exc: BaseException) -> str:
    """Truncate exception text for safe inclusion in user-visible warnings.

    v0.7.132 — Area for Review #10. The previous version did a flat
    character truncation at byte ~199, which on multi-line exceptions
    (PyMuPDF stack traces, mammoth error blocks with embedded paths,
    LangChain provider errors with chained-cause sections) would cut
    in the middle of line 1 and lose the rest entirely. The operator
    saw "could not parse foo.pdf: TypeError: cannot conver…" — no
    indication that the actual cause was 4 lines down.

    New behavior:
      * If exception text is single-line: same as before — truncate
        at _MAX_WARNING_LEN with the ellipsis suffix.
      * If exception text is multi-line: take the first line VERBATIM
        (up to _MAX_WARNING_LEN-32 to leave room for the suffix), then
        suffix with " (… N more lines)". The operator sees the actual
        error head and knows how much was elided.

    The 32-char headroom is sized for the longest realistic suffix
    "(… 999 more lines)" with a leading space. We could be tighter
    but 32 is a clean number and the loss is negligible for messages
    that need this branch (they're invariably hundreds-of-chars long).
    """
    s = str(exc)
    # Multi-line path first — the more interesting case.
    if "\n" in s:
        lines = s.split("\n")
        first = lines[0]
        extra = len(lines) - 1
        suffix = f" (… {extra} more line{'s' if extra != 1 else ''})"
        # Leave room for the suffix when truncating the first line.
        head_budget = _MAX_WARNING_LEN - len(suffix)
        if len(first) > head_budget:
            first = first[: head_budget - 1] + "…"
        return first + suffix

    # Single-line: original behavior.
    if len(s) <= _MAX_WARNING_LEN:
        return s
    return s[: _MAX_WARNING_LEN - 1] + "…"


# v0.7.4 — Common local-model error signatures. When llama-cpp-python /
# ollama / a generic OpenAI-compatible server rejects a request because
# the input is too long, the response usually contains one of these
# substrings. We pattern-match to surface an actionable hint instead of
# the raw error.
_LOCAL_OVERFLOW_PATTERNS = (
    "context length",
    "context window",
    "max_tokens",
    "context size",
    "tokens exceeded",
    "input too long",
    "prompt is too long",
    "exceeds the model's context",
)


def _studio_generation_error_detail(
    exc: BaseException, *, notebook_id: str, source_count: int,
) -> str:
    """Build the 502 detail string for LLM-call failures.

    Always includes the notebook_id so the user can navigate back to
    their uploaded content. When the failure looks like a context-window
    overflow (common for local 7B-9B models with 8k-context), prepend a
    pointer to the relevant env vars so the user knows how to fix it
    rather than just retrying the same prompt against the same model.
    """
    msg = str(exc).lower()
    hint = ""
    if any(pat in msg for pat in _LOCAL_OVERFLOW_PATTERNS):
        hint = (
            "Looks like the model's context window was exceeded. Smaller "
            "local models (Hermes-3 8k, Llama-3.2-3B 4k) can't fit large "
            "documents. Try uploading fewer/smaller files, or tighten the "
            "caps via ONP_STUDIO_MAX_FILE_CHARS / "
            "ONP_STUDIO_MAX_COMBINED_CHARS, or pick a chat model with a "
            "larger context window in Settings → Models. "
        )
    return (
        f"{hint}Generation failed: {_brief(exc)}. "
        f"Notebook {notebook_id} was created and contains your "
        f"{source_count} uploaded source(s). Try regenerating, or check "
        "Settings → Models for a working LLM."
    )


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
# v0.7.89 — Multi-page notebook generation
# -----------------------------------------------------------------------------
# Default ON. Falls back to the legacy single-note path (NOTEBOOK_SYSTEM_PROMPT
# above) if disabled OR if the outline pass returns un-parseable JSON.
_MULTIPAGE_ENABLED = (
    os.environ.get("ONP_STUDIO_NOTEBOOK_MULTIPAGE", "true").strip().lower()
    not in ("0", "false", "no", "off")
)
# Caps pages to bound LLM cost. Outline LLM is *also* told this number so it
# doesn't propose more than we can render.
_PAGES_MAX = _env_int("ONP_STUDIO_NOTEBOOK_PAGES_MAX", 6)
if _PAGES_MAX < 2:
    _PAGES_MAX = 2  # one overview + at least one detail page
if _PAGES_MAX > 12:
    _PAGES_MAX = 12  # rate-limit defense; local 7B-9Bs would crawl past this

# v0.7.92 — Optional parallel page generation. Default OFF because the
# desktop bundle's local-LLM dual-server (llama-cpp embed + chat) has
# limited concurrency and gathered ainvoke calls can OOM or starve
# tokens. Cloud users (OpenAI, Anthropic, etc.) can opt in for ~Nx
# speedup on multi-page generation. The trade-off: parallel calls
# mean per-page failures can interleave in logs, but the final result
# is identical (each page still gets its own warning on failure).
_PARALLEL_PAGES = (
    os.environ.get("ONP_STUDIO_NOTEBOOK_PARALLEL_PAGES", "false").strip().lower()
    in ("1", "true", "yes", "on")
)
# v0.7.93 — Per-page generation timeout. Local LLMs (especially the
# desktop bundle's llama-cpp chat server) can hang indefinitely when
# the model is mid-loading, mid-prompt-eval, or the prompt overflows
# context. Without a cap, ONE stuck page blocks the entire notebook
# generation request — including subsequent pages, the response, and
# the user's browser tab. Default: 180s, plenty for a 7B-9B at 8k
# context. Cloud users with stable APIs can raise via env.
_PAGE_TIMEOUT_SEC = _env_int("ONP_STUDIO_PAGE_TIMEOUT_SEC", 180)
# Outline pass gets its own (shorter) timeout — JSON-only response,
# small token budget, should be fast.
_OUTLINE_TIMEOUT_SEC = _env_int("ONP_STUDIO_OUTLINE_TIMEOUT_SEC", 90)

# Outline pass: small JSON response. Keep token budget tight — this prompt
# does NOT need to expand on any topic, just identify the structure.
NOTEBOOK_OUTLINE_PROMPT = """\
You are planning the structure of a multi-page study notebook from the \
supplied source documents. You will return ONLY a single JSON object — no \
prose before or after, no markdown fence — matching this schema EXACTLY:

{{
  "headline": "<one-sentence punchy summary of what these documents are about, ≤140 chars>",
  "summary": "<2-3 paragraph executive summary, plain prose, no bullets, no headings>",
  "pages": [
    {{
      "title": "<short page title, ≤60 chars, no markdown>",
      "focus": "<1-2 sentence description of what this page must cover>",
      "key_questions": ["<question 1>", "<question 2>", "..."]
    }}
  ],
  "top_suggestions": [
    "<concrete recommendation a reader should act on>",
    "..."
  ]
}}

# Rules

- Return strictly valid JSON. No trailing commas, no comments, no \
explanation, no markdown fence (`​`​`​`​`​`json … `​`​`​`).
- `pages` MUST have between 3 and {max_pages} entries — pick a count that \
genuinely fits the source material. A 5-paragraph press release deserves 3 \
pages, not 6. A dense technical white-paper can use all {max_pages}.
- Pages must be **distinct subjects** (e.g. "Architecture", "Backend \
internals", "Deployment", "Risks") — not generic ("Introduction", \
"Body", "Conclusion"). Read the source material and let the topics emerge.
- `key_questions` per page: 3-5 specific, source-grounded questions a \
reader of that page should be able to answer.
- `top_suggestions`: 3-6 concrete recommendations the user should consider \
based on what the documents reveal — gaps to fill, decisions to validate, \
risks to mitigate, follow-up reading. Real advice, not platitudes.
- `headline` + `summary` are the user's first impression. Make them \
information-dense and faithful to the sources.
- Stay grounded in the source. Do NOT invent facts. If the sources are \
thin, propose fewer pages — quality over quantity.
"""


# Per-page pass: produce ONE expanded page worth of content. The outline-pass
# decided what this page covers; this prompt fleshes it out. Each page ends
# with a "💡 AI Suggestions for this page" block so guidance shows up in
# context — not buried at the end of the notebook.
NOTEBOOK_PAGE_PROMPT = """\
You are writing **one page** of a multi-page study notebook. The notebook's \
overall topic is: **{notebook_title}**. Other pages cover the rest of the \
material; this page must focus EXCLUSIVELY on the subject below.

# This page

- **Page title:** {page_title}
- **Focus:** {page_focus}
- **Questions this page must answer:**
{page_questions}

# What to produce

Return clean Markdown for ONE page. Use this structure:

```
# {page_title}

<3-6 sentence intro framing what this page covers and why it matters>

## Key concepts
- **Concept** — explanation (source: <filename> if relevant)
- ...

## Details
<Substantive prose explaining the topic in depth, grounded in the sources.
Use ### subheadings if the page has natural sub-topics. Quote sources
with > blockquotes when reproducing exact wording.>

## Open questions for the reader
- <question> — <brief framing of what to look for in the sources to answer>
- ...

## 💡 AI Suggestions for this page
- **<Action verb> ...** — <concrete recommendation tied to what THIS page covered>
- ...
```

# Constraints

- **3-5 suggestions** in the AI Suggestions block, each starting with a verb \
("Verify", "Document", "Replace", "Investigate", "Add", "Defer"). Each one \
specific enough that a reader knows what to do next.
- Stay strictly within this page's focus. Do NOT cover other pages' topics.
- Cite sources inline as `(source: <filename>)` for specific factual claims.
- If the sources don't say enough to answer a key question, say so plainly \
in "Open questions for the reader" — don't pad with general knowledge.
- Output ONLY the Markdown for the page. No preamble like "Here is the \
page:". No closing remarks. Start with the `#` heading.
- Target ~400-900 words per page; thin sources → shorter is fine.
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

    v0.7.88 — `mode="both"` populates BOTH `note_id` and `job_id`. Either
    half can succeed independently; partial failures land in `warnings`
    so the user keeps whatever did succeed.

    v0.7.89 — notebook + both modes now generate a MULTI-PAGE notebook
    (one Overview note + N per-topic pages, each with an inline
    "💡 AI Suggestions" block). `note_id` continues to point at the
    Overview note for backward compatibility; `note_ids` carries every
    note id in render order (overview first, then pages). When the
    outline pass fails and we fall back to single-note output,
    `note_ids` contains just the one entry.
    """

    notebook_id: str
    mode: str  # "notebook" | "podcast" | "both"
    note_id: Optional[str] = None  # notebook + both: overview note (back-compat)
    note_ids: list[str] = []       # v0.7.89 — all notes in render order
    job_id: Optional[str] = None   # podcast  + both: surreal_commands job id
    source_ids: list[str]
    title: str
    warnings: list[str] = []  # non-fatal issues (e.g. a file couldn't be extracted)


# -----------------------------------------------------------------------------
# Artifact endpoints
# -----------------------------------------------------------------------------


@router.post(
    "/artifacts",
    response_model=StudioArtifactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_artifact(
    payload: StudioArtifactCreate,
) -> StudioArtifactResponse:
    _require_evidence_studio()
    artifact = StudioArtifact(**payload.model_dump())
    await artifact.save()
    return _artifact_response(artifact)


@router.get(
    "/notebooks/{notebook_id}/artifacts",
    response_model=list[StudioArtifactResponse],
)
async def list_studio_artifacts(
    notebook_id: str,
) -> list[StudioArtifactResponse]:
    _require_evidence_studio()
    if not await _notebook_record_exists(notebook_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notebook not found",
        )
    artifacts = await StudioArtifact.get_for_notebook(notebook_id)
    artifacts = [
        artifact
        for artifact in artifacts
        if getattr(artifact, "revision_of_id", None) is None
    ]
    return [_artifact_response(artifact) for artifact in artifacts]


@router.get(
    "/artifacts/{artifact_id}/revisions",
    response_model=list[StudioArtifactResponse],
)
async def list_studio_artifact_revisions(
    artifact_id: str,
) -> list[StudioArtifactResponse]:
    _require_evidence_studio()
    revisions = await StudioArtifact.get_revisions(artifact_id)
    return [_artifact_response(revision) for revision in revisions]


@router.post(
    "/artifacts/{artifact_id}/workflow-runs",
    response_model=StudioWorkflowRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_studio_workflow_run(
    artifact_id: str,
    payload: StudioWorkflowRunCreate,
) -> StudioWorkflowRunResponse:
    _require_evidence_studio()
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio artifact not found",
        )

    approval_required = payload.approval_required
    run = StudioWorkflowRun(
        artifact_id=str(artifact.id),
        notebook_id=str(artifact.notebook_id),
        title=payload.title,
        status="awaiting_approval" if approval_required else "queued",
        source_ids=payload.source_ids or [str(source_id) for source_id in artifact.source_ids],
        approval_required=approval_required,
        steps=_workflow_steps_for_artifact(
            artifact,
            approval_required=approval_required,
        ),
    )
    await run.save()
    return _workflow_run_response(run)


@router.get(
    "/artifacts/{artifact_id}/workflow-runs",
    response_model=list[StudioWorkflowRunResponse],
)
async def list_studio_workflow_runs(
    artifact_id: str,
) -> list[StudioWorkflowRunResponse]:
    _require_evidence_studio()
    try:
        await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio artifact not found",
        )

    runs = await StudioWorkflowRun.get_for_artifact(artifact_id)
    return [_workflow_run_response(run) for run in runs]


@router.post(
    "/workflow-runs/{run_id}/approve",
    response_model=StudioWorkflowRunResponse,
)
async def approve_studio_workflow_run(
    run_id: str,
) -> StudioWorkflowRunResponse:
    _require_evidence_studio()
    try:
        run = await StudioWorkflowRun.get(run_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio workflow run not found",
        )

    run.status = "queued"
    run.approval_required = False
    _set_workflow_step_status(run, {"privacy_gate"}, "completed")
    _set_workflow_step_status(run, {"model_route", "artifact_generation"}, "pending")
    await run.save()
    return _workflow_run_response(run)


@router.get(
    "/artifacts/{artifact_id}",
    response_model=StudioArtifactResponse,
)
async def get_studio_artifact(
    artifact_id: str,
) -> StudioArtifactResponse:
    _require_evidence_studio()
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio artifact not found",
        )
    return _artifact_response(artifact)


@router.patch(
    "/artifacts/{artifact_id}",
    response_model=StudioArtifactResponse,
)
async def update_studio_artifact(
    artifact_id: str,
    payload: StudioArtifactUpdate,
) -> StudioArtifactResponse:
    _require_evidence_studio()
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio artifact not found",
        )

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(artifact, key, value)
    await artifact.save()
    return _artifact_response(artifact)


@router.post(
    "/artifacts/{artifact_id}/generate",
    response_model=StudioArtifactResponse,
)
async def generate_studio_artifact(
    artifact_id: str,
) -> StudioArtifactResponse:
    _require_evidence_studio()
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio artifact not found",
        )

    workflow_run = await _active_workflow_run_for_artifact(str(artifact.id))
    if workflow_run is not None and workflow_run.status == "awaiting_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow run is awaiting approval",
        )

    await _snapshot_artifact_revision(artifact)

    artifact.status = "running"
    await artifact.save()
    if workflow_run is not None:
        workflow_run.status = "running"
        _set_workflow_step_status(workflow_run, {"model_route", "artifact_generation"}, "running")
        await workflow_run.save()

    try:
        sources = await _artifact_sources(artifact)
        not_ready_sources = _artifact_not_ready_sources(sources)
        if not_ready_sources:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "sources_not_ready",
                    "message": (
                        "One or more selected sources are still processing. "
                        "Wait for extraction to finish, then generate again."
                    ),
                    "not_ready_sources": not_ready_sources,
                },
            )
        combined_context, citations = _artifact_context(sources)
        if not combined_context.strip():
            raise InvalidInputError("No extracted source text is available")

        system_prompt = f"""\
You are Evidence Studio inside Open Notebook Plus.

{_artifact_instruction(artifact)}

Requirements:
- Stay faithful to the provided sources.
- Do not invent facts, dates, numbers, or quotes.
- Cite specific claims with the provided source markers.
- Use source markers like [S1] in the artifact body so readers can verify claims.
- If the sources are insufficient, say what is missing.
- Return markdown only.
"""
        model_id, provider = await _resolve_artifact_model_route(artifact)
        artifact.model_id = model_id
        artifact.provider = provider

        chain = await provision_langchain_model(
            combined_context,
            model_id,
            "chat",
            max_tokens=3072,
        )
        response = await asyncio.wait_for(
            chain.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=combined_context)]
            ),
            timeout=_PAGE_TIMEOUT_SEC,
        )
        content = clean_thinking_content(extract_text_content(response.content)).strip()
        if not content:
            raise InvalidInputError("Generated artifact output was empty")
        artifact.status = "completed"
        artifact.output_format = "markdown"
        artifact.citations = citations
        artifact.output_payload = _artifact_output_payload(artifact, content, citations)
        artifact.source_ids = [citation["source_id"] for citation in citations]
        try:
            artifact.export_paths = await asyncio.to_thread(
                _persist_artifact_exports,
                artifact,
                content,
            )
        except Exception as export_exc:
            logger.warning("Evidence Studio artifact export failed: {}", export_exc)
            artifact.export_paths = {}
        await artifact.save()
        if workflow_run is not None:
            workflow_run.status = "completed"
            _set_workflow_step_status(
                workflow_run,
                {"model_route", "artifact_generation"},
                "completed",
            )
            await workflow_run.save()
        return _artifact_response(artifact)
    except HTTPException as exc:
        if (
            exc.status_code == status.HTTP_409_CONFLICT
            and isinstance(exc.detail, dict)
            and exc.detail.get("code") == "sources_not_ready"
        ):
            artifact.status = "pending"
            await artifact.save()
            if workflow_run is not None:
                workflow_run.status = "queued"
                _set_workflow_step_status(
                    workflow_run,
                    {"model_route", "artifact_generation"},
                    "pending",
                )
                await workflow_run.save()
            raise

        artifact.status = "failed"
        await artifact.save()
        if workflow_run is not None:
            workflow_run.status = "failed"
            _set_workflow_step_status(workflow_run, {"artifact_generation"}, "failed")
            await workflow_run.save()
        raise
    except Exception as exc:
        logger.exception("Evidence Studio artifact generation failed")
        artifact.status = "failed"
        artifact.output_payload = {"error": _brief(exc)}
        await artifact.save()
        if workflow_run is not None:
            workflow_run.status = "failed"
            _set_workflow_step_status(workflow_run, {"artifact_generation"}, "failed")
            await workflow_run.save()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Artifact generation failed",
        ) from exc


@router.delete("/artifacts/{artifact_id}")
async def delete_studio_artifact(artifact_id: str) -> dict[str, object]:
    _require_evidence_studio()
    try:
        artifact = await StudioArtifact.get(artifact_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Studio artifact not found",
        )
    deleted = await artifact.delete()
    return {"deleted": deleted, "id": artifact_id}


# -----------------------------------------------------------------------------
# Generation endpoint
# -----------------------------------------------------------------------------


@router.post("/generate", response_model=StudioGenerateResponse)
async def studio_generate(
    files: Optional[list[UploadFile]] = File(None, description="One or more documents to ingest"),
    links: Optional[list[str]] = Form(None, description="Optional http(s) links to ingest"),
    mode: str = Form(..., description="'notebook', 'podcast', or 'both'"),
    title: Optional[str] = Form(None, description="Notebook title; auto-generated if absent"),
    episode_profile_name: Optional[str] = Form(
        None,
        description="Required for podcast / both — name of an EpisodeProfile record",
    ),
    speaker_profile_name: Optional[str] = Form(
        None,
        description="Required for podcast / both — name of a SpeakerProfile record",
    ),
) -> StudioGenerateResponse:
    """One-shot upload → generate. See module docstring for the full flow."""

    # 1. Validate inputs upfront so we don't half-create a notebook then fail.
    # v0.7.88 — `both` mode runs notebook generation synchronously and then
    # submits the podcast command. Either half can independently fail; the
    # warnings array carries any partial-failure context so the user keeps
    # whatever did succeed.
    if mode not in ("notebook", "podcast", "both"):
        raise HTTPException(
            status_code=400,
            detail="mode must be 'notebook', 'podcast', or 'both'",
        )
    files = files or []
    normalized_links = _normalize_studio_links(links)
    if not files and not normalized_links:
        raise HTTPException(status_code=400, detail="at least one file or link is required")
    if mode in ("podcast", "both"):
        if not episode_profile_name or not speaker_profile_name:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{mode.capitalize()} mode requires both episode_profile_name "
                    "and speaker_profile_name. Available profiles can be fetched "
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
        if files:
            first = Path(files[0].filename or "Untitled").stem
        else:
            first = _studio_link_title(normalized_links[0])
        title = f"Studio: {first[:80]}"

    # 3. Create the Notebook record.
    try:
        notebook = Notebook(
            name=title[:200],
            description=(
                f"Generated via Studio from {len(files)} file(s) and "
                f"{len(normalized_links)} link(s); mode={mode}"
            ),
        )
        await notebook.save()
    except InvalidInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.182 — bubble typed exceptions to the global handlers.
        raise
    except Exception as exc:
        # v0.7.178 — Sanitize 500 detail (same pattern as v0.7.168
        # / v0.7.177 sweeps). logger.exception above captures the
        # full traceback for ops; the client gets a generic message.
        logger.exception("Studio: failed to create notebook")
        raise HTTPException(status_code=500, detail="Could not create notebook")
    notebook_id = str(notebook.id)

    # 4. Per-input: save/link → Source → extract → link notebook.
    source_ids: list[str] = []
    extracted: list[tuple[str, str]] = []  # (filename, parsed_text)
    warnings: list[str] = []

    # Lazy import to avoid pulling content_core into module load
    from content_core import extract_content
    from content_core.common import ProcessSourceState

    async def _extract_and_persist_source(
        *,
        source: Source,
        label: str,
        process_state,
    ) -> None:
        try:
            _extract_timeout = float(
                os.environ.get("ONP_STUDIO_EXTRACT_TIMEOUT_SEC", "60").strip() or 60
            )
            try:
                processed = await asyncio.wait_for(
                    extract_content(process_state), timeout=_extract_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Studio: extract_content timed out for {!r} after {}s",
                    label, _extract_timeout,
                )
                warnings.append(
                    f"Parsing {label!r} timed out after {_extract_timeout:.0f}s. "
                    "The source may be inaccessible, malformed, or password-protected. "
                    "Raise ONP_STUDIO_EXTRACT_TIMEOUT_SEC or provide a cleaner source."
                )
                return
            text = (processed.content or "").strip()
            if not text:
                warnings.append(
                    f"No text could be extracted from {label!r} — the source may be "
                    "empty, inaccessible, image-only (no OCR), or in a corrupt state."
                )
                return
            if len(text) > _MAX_EXTRACT_CHARS_PER_FILE:
                logger.info(
                    "Studio: truncating {!r} from {} → {} chars",
                    label, len(text), _MAX_EXTRACT_CHARS_PER_FILE,
                )
                text = text[:_MAX_EXTRACT_CHARS_PER_FILE] + "\n\n[…truncated…]"
            extracted.append((label, text))
            source.full_text = text
            if processed.title and not source.title:
                source.title = processed.title
            extraction_provenance = {
                key: value
                for key, value in {
                    "content_source_type": getattr(processed, "source_type", None),
                    "identified_type": getattr(processed, "identified_type", None),
                    "extractor": "content_core",
                    "url": getattr(processed, "url", None),
                    "file_path": getattr(processed, "file_path", None),
                }.items()
                if value is not None
            }
            content_metadata = getattr(processed, "metadata", None)
            if isinstance(content_metadata, dict):
                extraction_provenance["content_metadata"] = content_metadata
            if extraction_provenance:
                source.provenance = {
                    **(source.provenance or {}),
                    "extraction": extraction_provenance,
                }
            await source.save()
            try:
                await source.vectorize()
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("Studio: vectorize failed (non-fatal) for {!r}: {}", label, exc)
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Studio: extract_content failed for {!r}", label)
            warnings.append(f"Could not parse {label!r}: {_brief(exc)}")

    for upload in files:
        filename = upload.filename or "upload"
        try:
            # v0.7.1 — pass max_bytes through so chunked-transfer-encoded
            # uploads can't bypass the size cap (UploadFile.size is None
            # for those, so the pre-check above silently skips).
            saved_path = await save_uploaded_file(upload, max_bytes=_MAX_FILE_BYTES)
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            logger.warning("Studio: save_uploaded_file failed for {!r}: {}", filename, exc)
            warnings.append(f"Could not save {filename!r}: {_brief(exc)}")
            continue

        # Create + link the Source first so it's visible even if extract fails
        try:
            source = Source(
                title=Path(filename).name,
                asset=Asset(file_path=saved_path),
                provenance={"origin": "studio_generate", "mode": mode},
                source_type="upload",
            )
            await source.save()
            await source.add_to_notebook(notebook_id)
            source_ids.append(str(source.id))
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            logger.warning("Studio: source create failed for {!r}: {}", filename, exc)
            warnings.append(f"Could not create source for {filename!r}: {_brief(exc)}")
            continue

        await _extract_and_persist_source(
            source=source,
            label=filename,
            process_state=ProcessSourceState(file_path=saved_path, output_format="markdown"),
        )

    for link in normalized_links:
        try:
            source = Source(
                title=_studio_link_title(link),
                asset=Asset(url=link),
                provenance={"origin": "studio_generate", "mode": mode, "url": link},
                source_type="link",
            )
            await source.save()
            await source.add_to_notebook(notebook_id)
            source_ids.append(str(source.id))
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Studio: link source create failed for {!r}: {}", link, exc)
            warnings.append(f"Could not create source for {link!r}: {_brief(exc)}")
            continue

        await _extract_and_persist_source(
            source=source,
            label=link,
            process_state=ProcessSourceState(url=link, output_format="markdown"),
        )

    if not extracted:
        # We created an empty notebook + maybe some empty sources. That's
        # actually a valid state (user can manually add content), but the
        # user explicitly asked for a generated output and we have nothing
        # to feed the LLM. Surface as a clear error.
        raise HTTPException(
            status_code=400,
            detail=(
                f"No usable text could be extracted from the {len(files)} uploaded "
                f"file(s) and {len(normalized_links)} link(s). Notebook {notebook_id} "
                "was created and contains the source records (visible in the UI), but generation was "
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
    #
    # v0.7.130 — wrap the dispatch in a try/except so we can emit
    # `studio_generations_total{mode, outcome}` even when the dispatcher
    # itself raises. The `outcome` heuristic:
    #   - 'success'  — dispatch returned with no warnings whose message
    #                  starts with "Podcast " / "Notebook " (those are
    #                  the partial-failure prefixes used inside
    #                  _dispatch_both_modes when one half fails).
    #   - 'partial'  — `both` mode where exactly one half succeeded.
    #                  Detected by the presence of one of the prefixed
    #                  warnings in the returned response.
    #   - 'failed'   — dispatch raised, OR the response indicates both
    #                  halves of a `both` request failed.
    # Best-effort: a metric increment failure must NEVER mask the
    # actual response (success or error) we're trying to give the user.
    def _record_outcome(outcome: str) -> None:
        try:
            from api.metrics import record_studio_generation
            record_studio_generation(mode, outcome)
        except Exception as exc:
            # v0.8.45 — best-effort metric increment must never mask the
            # user's response, but log at DEBUG so a broken metrics path
            # is discoverable (v0.8.27-v0.8.35f silent-except convention).
            logger.debug("Studio: record_studio_generation failed: {}", exc)

    def _classify_outcome(resp: "StudioGenerateResponse") -> str:
        # Look at the response warnings to decide success vs partial.
        # In 'notebook' / 'podcast' mode there's no "partial" — either
        # we returned a usable artifact or we raised. So success only.
        # In 'both' mode, a half-failure produces a warning prefixed
        # with "Podcast " or "Notebook " telling the user which side
        # broke. If both halves broke, the dispatcher itself raises.
        if mode != "both":
            return "success"
        partial_markers = ("Podcast ", "Notebook ")
        for w in resp.warnings or []:
            if any(w.startswith(p) for p in partial_markers):
                return "partial"
        return "success"

    try:
        if mode == "notebook":
            response = await _dispatch_notebook_mode(
                notebook=notebook,
                combined_context=combined_context,
                title=title,
                source_ids=source_ids,
                warnings=warnings,
            )
        elif mode == "podcast":
            response = await _dispatch_podcast_mode(
                notebook_id=notebook_id,
                episode_profile_name=episode_profile_name,  # type: ignore[arg-type]
                speaker_profile_name=speaker_profile_name,  # type: ignore[arg-type]
                title=title,
                source_ids=source_ids,
                warnings=warnings,
            )
        else:
            # v0.7.88 — mode == "both": run notebook synchronously, then
            # submit the podcast job. Half-failures degrade gracefully —
            # whichever half succeeded is preserved, and warnings carry
            # the diagnostic.
            response = await _dispatch_both_modes(
                notebook=notebook,
                notebook_id=notebook_id,
                combined_context=combined_context,
                episode_profile_name=episode_profile_name,  # type: ignore[arg-type]
                speaker_profile_name=speaker_profile_name,  # type: ignore[arg-type]
                title=title,
                source_ids=source_ids,
                warnings=warnings,
            )
    except HTTPException:
        # Typed HTTPExceptions (400/422 etc.) — count as 'failed' for
        # observability even though FastAPI returns them properly.
        _record_outcome("failed")
        raise
    except Exception:
        _record_outcome("failed")
        raise

    _record_outcome(_classify_outcome(response))
    return response


# -----------------------------------------------------------------------------
# Mode dispatchers
# -----------------------------------------------------------------------------


# v0.7.89 — Strip the common ways an LLM wraps a JSON payload (markdown
# fences, "Here is the JSON:" preambles, trailing commentary). Returns
# the raw JSON substring if found, else the original text.
def _strip_json_wrapper(text: str) -> str:
    s = (text or "").strip()
    # Strip ```json … ``` or ``` … ``` fences
    if s.startswith("```"):
        # Drop first fence line
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        # Drop trailing fence
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    # Slice from first { to last } to discard preamble/postamble
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        return s[first : last + 1]
    return s


# v0.7.89 — Validate and normalize the outline JSON. Returns (outline, error).
# A bad outline returns (None, "reason") so caller can fall back to single-note.
def _validate_outline(payload: dict, *, max_pages: int) -> tuple[Optional[dict], Optional[str]]:
    if not isinstance(payload, dict):
        return None, "outline is not a JSON object"
    headline = (payload.get("headline") or "").strip()
    summary = (payload.get("summary") or "").strip()
    pages = payload.get("pages") or []
    top_suggestions = payload.get("top_suggestions") or []
    if not headline:
        return None, "outline missing 'headline'"
    if not summary:
        return None, "outline missing 'summary'"
    if not isinstance(pages, list) or not pages:
        return None, "outline 'pages' must be a non-empty list"
    if len(pages) > max_pages:
        # Soft cap rather than reject — trim to the configured ceiling.
        pages = pages[:max_pages]
    cleaned_pages: list[dict] = []
    for i, p in enumerate(pages):
        if not isinstance(p, dict):
            continue
        ptitle = (p.get("title") or f"Page {i + 1}").strip()[:80]
        pfocus = (p.get("focus") or "").strip()
        pqs_raw = p.get("key_questions") or []
        pqs = [str(q).strip() for q in pqs_raw if str(q).strip()]
        if not pfocus and not pqs:
            # Page is empty — skip; LLM probably padded.
            continue
        cleaned_pages.append(
            {"title": ptitle, "focus": pfocus, "key_questions": pqs}
        )
    if not cleaned_pages:
        return None, "outline 'pages' had no usable entries after validation"
    if not isinstance(top_suggestions, list):
        top_suggestions = []
    top_suggestions = [str(s).strip() for s in top_suggestions if str(s).strip()]
    return (
        {
            "headline": headline[:200],
            "summary": summary,
            "pages": cleaned_pages,
            "top_suggestions": top_suggestions,
        },
        None,
    )


# v0.7.89 — Compose the Overview note's Markdown. This is the user's first
# stop in the multi-page notebook; it bundles headline, summary, table of
# contents (so they can scan), and top-level suggestions.
def _render_overview_note(*, title: str, outline: dict, page_titles: list[str]) -> str:
    headline = outline["headline"]
    summary = outline["summary"]
    top_suggestions = outline.get("top_suggestions") or []
    lines: list[str] = []
    lines.append(f"# 📋 {title} — Overview")
    lines.append("")
    lines.append(f"> **Headline:** {headline}")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(summary)
    lines.append("")
    if page_titles:
        lines.append("## Pages in this notebook")
        lines.append("")
        for i, pt in enumerate(page_titles, start=1):
            lines.append(f"{i}. **{pt}**")
        lines.append("")
    if top_suggestions:
        lines.append("## 💡 Top suggestions from the AI reviewer")
        lines.append("")
        for s in top_suggestions:
            lines.append(f"- {s}")
        lines.append("")
    lines.append(
        "_This notebook was generated by Studio (multi-page mode). Open the "
        "individual pages below for the deep dive on each topic; each one "
        "closes with its own 💡 suggestions block._"
    )
    return "\n".join(lines)


# v0.7.89 — Single LLM call → JSON outline. Wrapped so the caller can
# decide whether to fall back gracefully on failure.
async def _generate_outline(
    *,
    combined_context: str,
    notebook_id: str,
    source_count: int,
) -> dict:
    """Returns the validated outline dict. Raises HTTPException on hard failure."""
    import json

    # v0.7.89 — provision_langchain_model can itself raise on credential
    # config errors. Keep it inside the try/except so any failure (provision
    # or ainvoke) yields the proper 502+notebook_id message rather than a
    # bare 500.
    system_prompt = NOTEBOOK_OUTLINE_PROMPT.format(max_pages=_PAGES_MAX)
    try:
        chain = await provision_langchain_model(
            combined_context, None, "chat", max_tokens=2048,
        )
        # v0.7.93 — wrap in wait_for so a hung local LLM (stuck loading /
        # mid-prompt-eval / overflowed context) becomes a typed 502 with
        # an actionable hint instead of hanging the request indefinitely.
        response = await asyncio.wait_for(
            chain.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=combined_context)]
            ),
            timeout=_OUTLINE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError as exc:
        logger.warning(
            "Studio multi-page: outline pass timed out after {}s", _OUTLINE_TIMEOUT_SEC,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Outline generation timed out after {_OUTLINE_TIMEOUT_SEC}s. "
                "The chat model may be loading or overloaded. Try again, or "
                "raise ONP_STUDIO_OUTLINE_TIMEOUT_SEC. "
                f"Notebook {notebook_id} was created and contains your "
                f"{source_count} uploaded source(s)."
            ),
        ) from exc
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.182 — bubble typed exceptions to the global handlers.
        raise
    except Exception as exc:
        logger.exception("Studio multi-page: outline pass failed")
        raise HTTPException(
            status_code=502,
            detail=_studio_generation_error_detail(
                exc, notebook_id=notebook_id, source_count=source_count,
            ),
        )
    raw = extract_text_content(response.content)
    cleaned = clean_thinking_content(raw)
    json_text = _strip_json_wrapper(cleaned)
    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        # Don't raise — this is the signal for the caller to fall back to
        # legacy single-note generation. Log enough to diagnose.
        # v0.7.89 — loguru uses {} formatting, not %-style. (The existing
        # %s strings elsewhere in this file are silently broken — see
        # report.)
        logger.warning(
            "Studio multi-page: outline JSON parse failed ({}); raw={!r}",
            exc, cleaned[:500],
        )
        # v0.7.130 — emit the Prometheus counter. Best-effort: a metrics
        # import failure must not break the caller's fallback flow.
        try:
            from api.metrics import record_studio_outline_parse_failure
            record_studio_outline_parse_failure("json_decode")
        except Exception as metric_exc:
            # v0.8.45 — DEBUG log the swallowed metric failure (the
            # ValueError below is the real signal; this guard only
            # protects the metric increment). v0.8.35f convention.
            logger.debug(
                "Studio: record_studio_outline_parse_failure(json_decode) "
                "failed: {}", metric_exc,
            )
        raise ValueError(f"outline JSON parse failed: {exc}")
    outline, err = _validate_outline(payload, max_pages=_PAGES_MAX)
    if not outline:
        logger.warning(
            "Studio multi-page: outline validation failed ({}); raw={!r}",
            err, cleaned[:500],
        )
        # v0.7.130 — counterpart for the validation-failure path. Same
        # try/except shield so observability can't break the request.
        try:
            from api.metrics import record_studio_outline_parse_failure
            record_studio_outline_parse_failure("validation")
        except Exception as metric_exc:
            # v0.8.45 — DEBUG log the swallowed metric failure
            # (v0.8.35f convention; the ValueError below is the signal).
            logger.debug(
                "Studio: record_studio_outline_parse_failure(validation) "
                "failed: {}", metric_exc,
            )
        raise ValueError(f"outline validation failed: {err}")
    return outline


# v0.7.89 — Generate one page of markdown content for the multi-page notebook.
# Returns the (possibly empty) markdown string. Caller decides how to handle
# empties / exceptions.
async def _generate_page(
    *,
    combined_context: str,
    notebook_title: str,
    page_spec: dict,
) -> str:
    """Returns the page Markdown. Raises on LLM failure (caller turns into warning).

    v0.7.93 — wrapped in asyncio.wait_for so a stuck local LLM becomes a
    TimeoutError caught by the caller's per-page warning path instead of
    blocking the whole notebook generation request.
    """
    questions_md = "\n".join(f"  - {q}" for q in page_spec.get("key_questions", []))
    if not questions_md:
        questions_md = "  - (No specific questions listed; cover the focus area thoroughly.)"
    system_prompt = NOTEBOOK_PAGE_PROMPT.format(
        notebook_title=notebook_title,
        page_title=page_spec["title"],
        page_focus=page_spec.get("focus") or "(see questions below)",
        page_questions=questions_md,
    )
    chain = await provision_langchain_model(
        combined_context, None, "chat", max_tokens=3072,
    )
    response = await asyncio.wait_for(
        chain.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=combined_context)]
        ),
        timeout=_PAGE_TIMEOUT_SEC,
    )
    raw = extract_text_content(response.content)
    return clean_thinking_content(raw).strip()


# v0.7.92 / v0.7.93 — Generate every page in the outline, with sequential
# (default) or parallel (env-opt-in) execution AND per-page timeouts.
# Returns a list of (note_title, body) pairs in render order (page index
# order — sequential trivially preserves it; parallel mode preserves it
# via the result-zipping below). Failed pages become warnings; survivors
# still ship.
async def _generate_all_pages(
    *,
    combined_context: str,
    notebook_title: str,
    page_specs: list[dict],
    warnings: list[str],
) -> list[tuple[str, str]]:
    page_contents: list[tuple[str, str]] = []

    def _on_page_failure(i: int, page_spec: dict, exc: BaseException) -> None:
        # v0.7.93 — TimeoutError gets a more actionable warning than a
        # generic exception. The user needs to know "raise the timeout
        # or pick a faster model", not just "something failed".
        if isinstance(exc, asyncio.TimeoutError):
            logger.warning(
                "Studio multi-page: page {} ({!r}) timed out after {}s",
                i, page_spec["title"], _PAGE_TIMEOUT_SEC,
            )
            warnings.append(
                f"Page {i} ({page_spec['title']!r}) timed out after "
                f"{_PAGE_TIMEOUT_SEC}s. Raise ONP_STUDIO_PAGE_TIMEOUT_SEC, "
                "or switch to a faster chat model."
            )
        else:
            logger.warning(
                "Studio multi-page: page {} ({!r}) generation failed: {}",
                i, page_spec["title"], _brief(exc),
            )
            warnings.append(
                f"Page {i} ({page_spec['title']!r}) could not be generated: "
                f"{_brief(exc)}"
            )

    if _PARALLEL_PAGES:
        # All pages in flight at once. return_exceptions=True so a single
        # failure doesn't cancel the rest mid-way.
        coros = [
            _generate_page(
                combined_context=combined_context,
                notebook_title=notebook_title,
                page_spec=p,
            )
            for p in page_specs
        ]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for i, (page_spec, result) in enumerate(zip(page_specs, results), start=1):
            if isinstance(result, BaseException):
                _on_page_failure(i, page_spec, result)
                continue
            if not result:
                warnings.append(
                    f"Page {i} ({page_spec['title']!r}) returned empty content."
                )
                continue
            page_contents.append(
                (f"📄 {i:02d} · {page_spec['title']}", result)
            )
        return page_contents

    # Sequential (default, local-LLM-safe).
    for i, page_spec in enumerate(page_specs, start=1):
        try:
            body = await _generate_page(
                combined_context=combined_context,
                notebook_title=notebook_title,
                page_spec=page_spec,
            )
        except HTTPException:
            # v0.7.108 — re-raise typed HTTPExceptions so the next
            # `except Exception` doesn't clobber them to 500.
            raise
        except Exception as exc:
            _on_page_failure(i, page_spec, exc)
            continue
        if not body:
            warnings.append(
                f"Page {i} ({page_spec['title']!r}) returned empty content."
            )
            continue
        page_contents.append(
            (f"📄 {i:02d} · {page_spec['title']}", body)
        )
    return page_contents


# v0.7.89 — Save a list of (title, content) notes to the notebook. Returns
# the list of saved note IDs in input order. Stops on the first save failure
# so we don't leak partially-attached notes; partial successes are returned
# to the caller via the IDs already in the list.
async def _save_notebook_notes(
    *,
    notebook_id: str,
    notes_to_save: list[tuple[str, str]],
) -> list[str]:
    saved_ids: list[str] = []
    for note_title, note_content in notes_to_save:
        # v0.7.89 — Note.content_must_not_be_empty rejects empty/whitespace.
        # Substitute a sentinel so the user gets *something* attached to the
        # notebook rather than silently dropping the page.
        body = note_content.strip() if note_content else ""
        if not body:
            body = "(The model returned no content for this page.)"
        note = Note(title=note_title[:200], content=body, note_type="ai")
        await note.save()
        await note.add_to_notebook(notebook_id)
        saved_ids.append(str(note.id))
    return saved_ids


async def _dispatch_notebook_mode(
    *,
    notebook: Notebook,
    combined_context: str,
    title: str,
    source_ids: list[str],
    warnings: list[str],
) -> StudioGenerateResponse:
    """v0.7.89 — Multi-page notebook generation.

    Flow:
      1. Outline pass (one LLM call → JSON: headline, summary, pages,
         top_suggestions). On failure → fall back to legacy single-note.
      2. Per-page pass (one LLM call per page, sequential). Per-page
         failures become warnings; surviving pages still ship.
      3. Persist: one Overview note (headline + summary + TOC + top
         suggestions) + one note per page (each ending in
         "💡 AI Suggestions"). Saved in render order so the user sees
         the Overview first in the notebook UI.

    The legacy single-note path remains reachable via the
    ONP_STUDIO_NOTEBOOK_MULTIPAGE=false env var or whenever the
    outline pass returns un-parseable JSON. That keeps the user shielded
    from regressions during the rollout window.

    Returns a StudioGenerateResponse with `note_id` pointing at the
    Overview note (back-compat) and `note_ids` carrying all saved notes.
    """
    notebook_id = str(notebook.id)

    if not _MULTIPAGE_ENABLED:
        return await _dispatch_notebook_mode_singlenote(
            notebook=notebook,
            combined_context=combined_context,
            title=title,
            source_ids=source_ids,
            warnings=warnings,
        )

    # 1. Outline pass.
    try:
        outline = await _generate_outline(
            combined_context=combined_context,
            notebook_id=notebook_id,
            source_count=len(source_ids),
        )
    except ValueError as exc:
        # JSON parse / validation failure — fall back to single-note so
        # the user still gets a usable artifact.
        logger.warning(
            "Studio multi-page: falling back to single-note ({})", exc,
        )
        # v0.7.130 — emit the fallback counter. Specific outline-parse
        # failure reason (json_decode vs validation) was already recorded
        # inside _generate_outline; here we just track that we DID fall
        # back rather than crashing or succeeding multi-page.
        try:
            from api.metrics import record_studio_single_note_fallback
            record_studio_single_note_fallback()
        except Exception as metric_exc:
            # v0.8.45 — DEBUG log the swallowed metric failure
            # (v0.8.35f convention). Fallback proceeds regardless.
            logger.debug(
                "Studio: record_studio_single_note_fallback failed: {}",
                metric_exc,
            )
        warnings.append(
            "Multi-page outline could not be parsed; fell back to a single "
            "study-note. Try regenerating, or pick a stronger chat model."
        )
        return await _dispatch_notebook_mode_singlenote(
            notebook=notebook,
            combined_context=combined_context,
            title=title,
            source_ids=source_ids,
            warnings=warnings,
        )

    # 2. Per-page pass. Default sequential — slamming llama-cpp-python with
    #    concurrent requests degrades quality and can OOM the embed+chat
    #    dual-server desktop setup. Cloud users (OpenAI/Anthropic/etc.)
    #    can opt into v0.7.92's parallel mode via env knob. Either way,
    #    one page failing must not abort the rest, and timeouts are
    #    treated as failures (per-page warning) rather than fatal.
    page_specs = outline["pages"]
    page_contents = await _generate_all_pages(
        combined_context=combined_context,
        notebook_title=title,
        page_specs=page_specs,
        warnings=warnings,
    )

    # 3. Persist. Overview always goes first so it sorts at the top of
    #    the notebook UI's notes list.
    overview_md = _render_overview_note(
        title=title,
        outline=outline,
        page_titles=[p["title"] for p in page_specs],
    )
    notes_to_save: list[tuple[str, str]] = [
        (f"📋 00 · {title} — Overview", overview_md),
    ]
    notes_to_save.extend(page_contents)
    try:
        saved_ids = await _save_notebook_notes(
            notebook_id=notebook_id,
            notes_to_save=notes_to_save,
        )
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.182 — bubble typed exceptions to the global handlers.
        raise
    except Exception as exc:
        # Saving even the Overview note failed — surface a 500 so the
        # frontend doesn't claim success. Notebook + sources are intact.
        logger.exception("Studio multi-page: could not save notes")
        raise HTTPException(
            status_code=500,
            detail=(
                f"Generated content but could not save it: {exc}. "
                f"Notebook {notebook_id} was created and contains your "
                f"{len(source_ids)} uploaded source(s)."
            ),
        )

    if len(saved_ids) == 1:
        warnings.append(
            "All page-generation calls failed — only the Overview note "
            "was saved. Try regenerating, or switch to a chat model with "
            "a larger context window."
        )

    return StudioGenerateResponse(
        notebook_id=notebook_id,
        mode="notebook",
        note_id=saved_ids[0],  # overview — back-compat with v0.7.88
        note_ids=saved_ids,
        source_ids=source_ids,
        title=title,
        warnings=warnings,
    )


# v0.7.89 — Pre-v0.7.89 single-note path, preserved as a fallback. Reached
# when ONP_STUDIO_NOTEBOOK_MULTIPAGE=false OR when the outline pass returns
# un-parseable JSON. Identical to the original v0.7.0 implementation.
async def _dispatch_notebook_mode_singlenote(
    *,
    notebook: Notebook,
    combined_context: str,
    title: str,
    source_ids: list[str],
    warnings: list[str],
) -> StudioGenerateResponse:
    notebook_id = str(notebook.id)
    try:
        chain = await provision_langchain_model(
            combined_context, None, "chat", max_tokens=8192,
        )
        # v0.7.99 — same timeout protection as the multi-page paths.
        # Before this, the legacy fallback was the one ainvoke in this
        # module that could still hang indefinitely on a stuck local
        # LLM. Re-uses _PAGE_TIMEOUT_SEC (180s default) since the
        # output budget is comparable.
        response = await asyncio.wait_for(
            chain.ainvoke(
                [SystemMessage(content=NOTEBOOK_SYSTEM_PROMPT),
                 HumanMessage(content=combined_context)]
            ),
            timeout=_PAGE_TIMEOUT_SEC,
        )
        raw_text = extract_text_content(response.content)
        clean_text = clean_thinking_content(raw_text)
    except asyncio.TimeoutError as exc:
        logger.warning(
            "Studio notebook (single-note fallback): timed out after {}s",
            _PAGE_TIMEOUT_SEC,
        )
        raise HTTPException(
            status_code=504,
            detail=(
                f"Notebook generation timed out after {_PAGE_TIMEOUT_SEC}s. "
                "The chat model may be loading or overloaded. Raise "
                "ONP_STUDIO_PAGE_TIMEOUT_SEC, switch to a faster model, "
                f"or try again. Notebook {notebook_id} was created and "
                f"contains your {len(source_ids)} uploaded source(s)."
            ),
        ) from exc
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.182 — bubble typed exceptions to the global handlers.
        raise
    except Exception as exc:
        logger.exception("Studio notebook (single-note fallback): LLM call failed")
        raise HTTPException(
            status_code=502,
            detail=_studio_generation_error_detail(
                exc, notebook_id=notebook_id, source_count=len(source_ids),
            ),
        )
    try:
        note = Note(
            title=f"{title} — Study Notes",
            content=clean_text or "(empty response from model)",
            note_type="ai",
        )
        await note.save()
        await note.add_to_notebook(notebook_id)
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.182 — bubble typed exceptions to the global handlers.
        raise
    except Exception as exc:
        # v0.7.178 — Sanitize 500 detail (see above). logger.exception
        # captures the full traceback for ops.
        logger.exception("Studio notebook (single-note fallback): could not save Note")
        raise HTTPException(
            status_code=500,
            detail="Generated content but could not save it",
        )
    note_id = str(note.id)
    return StudioGenerateResponse(
        notebook_id=notebook_id,
        mode="notebook",
        note_id=note_id,
        note_ids=[note_id],
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


# v0.7.88 / v0.7.89 — mode="both": multi-page notebook generation AND a
# podcast job in one shot. Either half can fail independently. We never
# 502 just because one half broke; instead, the user gets a 200 with
# whatever succeeded populated and the failure described in `warnings`.
# The notebook + uploaded sources are durable regardless.
async def _dispatch_both_modes(
    *,
    notebook: Notebook,
    notebook_id: str,
    combined_context: str,
    episode_profile_name: str,
    speaker_profile_name: str,
    title: str,
    source_ids: list[str],
    warnings: list[str],
) -> StudioGenerateResponse:
    note_id: Optional[str] = None
    note_ids: list[str] = []
    job_id: Optional[str] = None

    # Notebook half — full multi-page pipeline. We catch HTTPException
    # here so a notebook failure doesn't prevent the podcast from being
    # submitted; partial success is the whole point of `both`.
    try:
        notebook_resp = await _dispatch_notebook_mode(
            notebook=notebook,
            combined_context=combined_context,
            title=title,
            source_ids=source_ids,
            warnings=warnings,
        )
        note_id = notebook_resp.note_id
        note_ids = notebook_resp.note_ids
        # _dispatch_notebook_mode may have appended its own warnings to
        # the shared list — those land here automatically.
    except HTTPException as exc:
        warnings.append(
            f"Notebook generation failed (HTTP {exc.status_code}): "
            f"{_brief(Exception(str(exc.detail)))}"
        )
    except Exception as exc:
        logger.exception("Studio both: notebook half raised unexpected error")
        warnings.append(f"Notebook generation failed: {_brief(exc)}")

    # Podcast half — independent submit. Same partial-failure rule.
    try:
        podcast_resp = await _dispatch_podcast_mode(
            notebook_id=notebook_id,
            episode_profile_name=episode_profile_name,
            speaker_profile_name=speaker_profile_name,
            title=title,
            source_ids=source_ids,
            warnings=warnings,
        )
        job_id = podcast_resp.job_id
    except HTTPException as exc:
        warnings.append(
            f"Podcast submission failed (HTTP {exc.status_code}): "
            f"{_brief(Exception(str(exc.detail)))}"
        )
    except Exception as exc:
        logger.exception("Studio both: podcast half raised unexpected error")
        warnings.append(f"Podcast submission failed: {_brief(exc)}")

    # Both halves failed → still a 200 so the user sees the notebook +
    # sources they uploaded. The warnings array carries the diagnostic.
    # If you wanted a 502 instead, this is where to gate it; current
    # design favours "user keeps their uploaded data" over loud failure.
    return StudioGenerateResponse(
        notebook_id=notebook_id,
        mode="both",
        note_id=note_id,
        note_ids=note_ids,
        job_id=job_id,
        source_ids=source_ids,
        title=title,
        warnings=warnings,
    )
