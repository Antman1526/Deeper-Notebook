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
from pydantic import BaseModel, ValidationError

from api.command_service import CommandService
from api.podcast_service import PodcastService
from api.routers.sources import save_uploaded_file
from api.schemas.studio import (
    StudioArtifactCreate,
    StudioArtifactResponse,
    StudioArtifactUpdate,
    StudioWorkflowRunCreate,
    StudioWorkflowRunResponse,
)
from deeper_notebook.ai.models import Model
from deeper_notebook.ai.provision import provision_langchain_model
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import (
    Asset,
    Note,
    Notebook,
    Source,
    StudioArtifact,
    StudioWorkflowRun,
)
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import InvalidInputError, NotFoundError
from deeper_notebook.feature_flags import evidence_studio_enabled
from deeper_notebook.identity import ACTIVITY_URN_PREFIX, PRODUCT_NAME
from deeper_notebook.local_models.inventory import enumerate_models
from deeper_notebook.local_models.role_routing import (
    inventory_model_match_keys,
    model_match_key,
    recommend_model_roles,
)
from deeper_notebook.studio import artifact_generation as artifact_generation_service
from deeper_notebook.studio.payloads import (
    build_structured_payload,
    parse_payload_document,
)
from deeper_notebook.studio.renderers import render_artifact_markdown
from deeper_notebook.utils.text_utils import (
    clean_thinking_content,
    extract_text_content,
)

from .common import (
    _MAX_EXTRACT_CHARS_PER_FILE,
    _artifact_response,
    _ensure_artifact_sources_ready,
    _notebook_record_exists,
    _require_evidence_studio,
    _sync_artifact_generation_service_dependencies,
    _workflow_run_response,
    router,
)

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
        resolve_env("DEEPER_NOTEBOOK_MODEL_DIR")
        or resolve_env("DEEPER_NOTEBOOK_MODEL_DIR_DEFAULT")
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
    return (
        bool(artifact.output_payload)
        or bool(artifact.citations)
        or bool(artifact.export_paths)
    )


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


def _citation_preview(text: str, limit: int = 280) -> str:
    preview = " ".join(text.split())
    if len(preview) <= limit:
        return preview
    return preview[: limit - 1].rstrip() + "…"


def _artifact_export_dir() -> Path:
    raw = resolve_env("DEEPER_NOTEBOOK_ARTIFACT_EXPORT_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()

    home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
    if home:
        return (
            Path(home)
            / "BrainPulseKnowledge"
            / "deeper-notebook-imports"
            / "evidence-studio"
        )
    return Path.cwd() / "deeper-notebook-imports" / "evidence-studio"


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
        lines.extend(
            f"  - {json.dumps(source_id, ensure_ascii=False)}"
            for source_id in source_ids
        )
    else:
        lines[-1] = "source_ids: []"
    lines.extend(["---", "", content.strip(), ""])

    if artifact.citations:
        lines.extend(["", "## Stored Citations", ""])
        for citation in artifact.citations:
            title = (
                citation.get("title") or citation.get("source_id") or "Untitled source"
            )
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
            text = text[len(prefix) :].lstrip()
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
                and not _strip_artifact_markdown_line(line)
                .lower()
                .startswith(
                    (
                        "learner handout",
                        "hands-on exercise",
                        "knowledge check",
                        "facilitator notes",
                        "instructor notes",
                    )
                )
            ),
            "",
        )
        module_content = "\n".join(current_lines)
        modules.append(
            {
                "title": current_title,
                "summary": summary,
                "has_facilitator_notes": bool(
                    re.search(
                        r"(facilitator notes?|instructor notes?|demo script)",
                        module_content,
                        re.IGNORECASE,
                    )
                ),
            }
        )
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
    return (
        "# Course Pack Assessment\n\nNo dedicated assessment sections were generated.\n"
    )


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


def _course_pack_checklist_export(
    artifact: StudioArtifact, modules: list[dict[str, object]]
) -> dict[str, object]:
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
    module_items = (
        "\n".join(f"<li>{html.escape(str(module['title']))}</li>" for module in modules)
        or "<li>Course Pack content</li>"
    )
    return "\n".join(
        [
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
            f"  <p>{PRODUCT_NAME} Course Pack export.</p>",
            "  <h2>Modules</h2>",
            f"  <ol>{module_items}</ol>",
            "  <h2>Course Pack Markdown</h2>",
            f"  <pre>{html.escape(content)}</pre>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _course_pack_scorm_manifest(artifact: StudioArtifact) -> str:
    identifier = html.escape(_artifact_export_slug(artifact.id, fallback="course-pack"))
    title = html.escape(artifact.title)
    return "\n".join(
        [
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
            '  <organizations default="deeper-notebook-course-pack">',
            '    <organization identifier="deeper-notebook-course-pack">',
            f"      <title>{title}</title>",
            '      <item identifier="course-pack-launch" identifierref="course-pack-resource">',
            f"        <title>{title}</title>",
            "      </item>",
            "    </organization>",
            "  </organizations>",
            "  <resources>",
            '    <resource identifier="course-pack-resource" type="webcontent" adlcp:scormtype="sco" href="index.html">',
            '      <file href="index.html" />',
            '      <file href="instructor-guide.md" />',
            '      <file href="learner-handout.md" />',
            '      <file href="module-checklist.json" />',
            '      <file href="assessment.md" />',
            "    </resource>",
            "  </resources>",
            "</manifest>",
            "",
        ]
    )


def _course_pack_tincan_xml(artifact: StudioArtifact) -> str:
    title = html.escape(artifact.title)
    activity_id = html.escape(f"{ACTIVITY_URN_PREFIX}{artifact.id}")
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<tincan xmlns="http://projecttincan.com/tincan.xsd">',
            "  <activities>",
            f'    <activity id="{activity_id}" type="http://adlnet.gov/expapi/activities/course">',
            f"      <name>{title}</name>",
            f"      <description>{PRODUCT_NAME} Course Pack export.</description>",
            '      <launch lang="en-US">index.html</launch>',
            "    </activity>",
            "  </activities>",
            "</tincan>",
            "",
        ]
    )


def _course_pack_xapi_statements(
    artifact: StudioArtifact,
    modules: list[dict[str, object]],
) -> dict[str, object]:
    activity_id = f"{ACTIVITY_URN_PREFIX}{artifact.id}"
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
        instructor_path = _artifact_export_path(
            export_dir, f"{stem}-instructor-guide", ".md"
        )
        learner_path = _artifact_export_path(
            export_dir, f"{stem}-learner-handout", ".md"
        )
        checklist_path = _artifact_export_path(
            export_dir, f"{stem}-module-checklist", ".json"
        )
        assessment_path = _artifact_export_path(export_dir, f"{stem}-assessment", ".md")
        scorm_path = _artifact_export_path(export_dir, f"{stem}-scorm", ".zip")
        xapi_path = _artifact_export_path(export_dir, f"{stem}-xapi", ".zip")
        export_paths.update(
            {
                "instructor_guide": str(instructor_path),
                "learner_handout": str(learner_path),
                "module_checklist": str(checklist_path),
                "assessment": str(assessment_path),
                "scorm_package": str(scorm_path),
                "xapi_package": str(xapi_path),
            }
        )
    data_table_csv = (
        _data_table_csv(content) if artifact.artifact_type == "data_table" else ""
    )
    if data_table_csv:
        csv_path = _artifact_export_path(export_dir, f"{stem}-data-table", ".csv")
        export_paths["csv"] = str(csv_path)
    artifact.export_paths = export_paths
    markdown_path.write_text(
        _artifact_markdown_export(artifact, content), encoding="utf-8"
    )
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
            _artifact_markdown_export(
                artifact, _course_pack_assessment_markdown(content)
            ),
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
        json.dumps(
            _artifact_response(artifact).model_dump(), ensure_ascii=False, indent=2
        ),
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
        citations.append(
            {
                "source_id": source_id,
                "title": title,
                "marker": marker,
                "location": f"Source {marker}",
                "preview": _citation_preview(text),
            }
        )
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
        not_ready.append(
            {
                "source_id": str(getattr(source, "id", "")),
                "title": getattr(source, "title", None) or "Untitled source",
                "command_id": str(command) if command is not None else None,
            }
        )
    return not_ready


# Restrict uploads to formats content_core handles well. Defense-in-depth
# even though content_core itself attempts to extract anything; this list
# matches what the spec promises for documents and common training media.
_ALLOWED_EXTENSIONS: set[str] = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".markdown",
    ".ppt",
    ".pptx",
    ".html",
    ".htm",
    ".mp3",
    ".mp4",
    ".m4a",
    ".wav",
    ".mov",
}

_MAX_STUDIO_LINKS = 20

# Per-file cap (50 MB). Combined with Next.js's 100 MB proxy limit
# (frontend/next.config.ts), this prevents a single huge file from
# starving downstream LLM context window.
_MAX_FILE_BYTES = 50 * 1024 * 1024


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

    updates = payload.model_dump(exclude_unset=True)
    output_payload = updates.get("output_payload")
    snapshot_before_update = False
    refresh_exports = False
    canonical_markdown = ""
    if isinstance(output_payload, dict) and "schema_version" in output_payload:
        try:
            document = parse_payload_document(
                artifact.artifact_type,
                output_payload,
            )
        except InvalidInputError as exc:
            code = (
                "unsupported_artifact_schema"
                if str(exc).startswith("Unsupported artifact schema version")
                else "invalid_artifact_document"
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": code,
                    "errors": [{"message": str(exc)[:240]}],
                },
            ) from exc
        except ValidationError as exc:
            errors = [
                {
                    "type": str(error.get("type", "validation_error"))[:120],
                    "location": [str(part)[:120] for part in error.get("loc", ())],
                    "message": str(error.get("msg", "Invalid value"))[:240],
                }
                for error in exc.errors(include_url=False)[:12]
            ]
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "invalid_artifact_document",
                    "errors": errors,
                },
            ) from exc

        if document is not None:
            previous_document = (
                artifact.output_payload.get("document")
                if isinstance(artifact.output_payload, dict)
                else None
            )
            snapshot_before_update = (
                artifact.status == "completed"
                and previous_document != document.model_dump(mode="json")
            )
            refresh_exports = snapshot_before_update and bool(artifact.export_paths)
            core_keys = {
                "schema_version",
                "document",
                "markdown",
                "content",
                "validation",
            }
            derived_keys = {
                "data_table_rows",
                "research_stages",
                "course_pack_modules",
                "citation_warnings",
            }
            extras = {
                key: value
                for key, value in output_payload.items()
                if key not in core_keys | derived_keys
            }
            previous_validation = output_payload.get("validation")
            validation: dict[str, object] = {
                "status": "valid",
                "errors": [],
            }
            if isinstance(previous_validation, dict):
                for key in ("strategy", "attempts"):
                    if key in previous_validation:
                        validation[key] = previous_validation[key]
            markdown = render_artifact_markdown(document)
            canonical_markdown = markdown
            derived_metadata = _artifact_output_payload(
                artifact,
                markdown,
                artifact.citations,
            )
            derived_metadata.pop("content", None)
            extras.update(derived_metadata)
            updates["output_payload"] = build_structured_payload(
                document,
                markdown,
                validation=validation,
                extras=extras,
            )

    if snapshot_before_update:
        await _snapshot_artifact_revision(artifact)
    for key, value in updates.items():
        setattr(artifact, key, value)
    if refresh_exports:
        artifact.export_paths = await asyncio.to_thread(
            artifact_generation_service.persist_artifact_exports,
            artifact,
            canonical_markdown,
        )
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
    _sync_artifact_generation_service_dependencies()
    artifact = await artifact_generation_service.generate_studio_artifact(artifact_id)
    return _artifact_response(artifact)


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
