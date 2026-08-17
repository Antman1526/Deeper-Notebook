"""Source, readiness, and model-routing helpers for Evidence Studio."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import HTTPException, status
from loguru import logger

from deeper_notebook.ai.models import Model
from deeper_notebook.ai.provision import provision_langchain_model
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.domain.notebook import Notebook, Source
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import NotFoundError
from deeper_notebook.local_models.inventory import enumerate_models
from deeper_notebook.local_models.role_routing import (
    inventory_model_match_keys,
    model_match_key,
    recommend_model_roles,
)

from .prompts import artifact_model_role


def env_int(name: str, default: int) -> int:
    raw = resolve_env(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        if value < 1:
            raise ValueError
        return value
    except ValueError:
        import logging

        logging.getLogger(__name__).warning(
            "Invalid %s=%r; using default %d", name, raw, default
        )
        return default


MAX_EXTRACT_CHARS_PER_FILE = env_int("DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS", 15_000)


def sources_not_ready_exception(
    not_ready_sources: list[dict[str, str | None]],
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "sources_not_ready",
            "message": "One or more selected sources are still processing. Wait for extraction to finish, then generate again.",
            "not_ready_sources": not_ready_sources,
        },
    )


async def artifact_sources(
    artifact: object,
    source_ids: list[str] | None = None,
    *,
    source_cls: type[Source] | None = None,
    notebook_cls: type[Notebook] | None = None,
) -> list[Source]:
    """Load an artifact's selected sources, or its notebook's when none are set.

    v0.8.99 — `source_cls` / `notebook_cls` let a caller supply the domain
    classes resolved in ITS own module namespace. This exists so
    `api/routers/studio/common.py` can delegate here instead of keeping a
    duplicate copy: the Evidence Studio API suite patches `Source` on that
    module (26 sites, plus the `_sync_legacy_patches` facade machinery), and a
    plain delegation would read this module's `Source` instead, escape the
    patch, and hit the live database. Injecting the class keeps that seam
    intact without the API package reaching in to mutate this module's globals
    — which would couple `deeper_notebook/` to `api/` and break the layering
    rule. Defaults preserve the original behaviour exactly.
    """
    source_type = source_cls or Source
    notebook_type = notebook_cls or Notebook
    selected_source_ids = (
        source_ids if source_ids is not None else getattr(artifact, "source_ids", [])
    )
    if selected_source_ids:
        # v0.8.98 — fetch concurrently. This ran a sequential `await` per
        # selected source, an N+1 on the path of EVERY Studio generation; with
        # a dozen sources that is a dozen serial round trips. The connection
        # pool (DEEPER_NOTEBOOK_DB_POOL_SIZE) already supports overlap.
        #
        # The 404 contract is preserved exactly: `gather` keeps result order,
        # and the first *id-order* failure is what raises — not whichever
        # request happened to fail first. Sources after a missing one now get
        # fetched too, which is harmless.
        results = await asyncio.gather(
            *(source_type.get(source_id) for source_id in selected_source_ids),
            return_exceptions=True,
        )
        sources: list[Source] = []
        for source_id, result in zip(selected_source_ids, results):
            if isinstance(result, (KeyError, NotFoundError)):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Source not found: {source_id}",
                ) from result
            if isinstance(result, BaseException):
                raise result
            sources.append(result)
        return sources
    try:
        notebook = await notebook_type.get(getattr(artifact, "notebook_id"))
    except (KeyError, NotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notebook not found: {getattr(artifact, 'notebook_id')}",
        ) from exc
    return await notebook.get_sources()


async def ensure_artifact_sources_ready(artifact: object) -> None:
    sources = await artifact_sources(artifact)
    not_ready_sources = artifact_not_ready_sources(sources)
    if not_ready_sources:
        raise sources_not_ready_exception(not_ready_sources)


async def notebook_record_exists(notebook_id: str) -> bool:
    rows = await repo_query(
        "SELECT id FROM $notebook_id LIMIT 1",
        {"notebook_id": ensure_record_id(notebook_id)},
    )
    return bool(rows)


def citation_preview(text: str, limit: int = 280) -> str:
    preview = " ".join(text.split())
    return preview if len(preview) <= limit else preview[: limit - 1].rstrip() + "…"


def artifact_context(sources: list[Source]) -> tuple[str, list[dict[str, str]]]:
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
                "preview": citation_preview(text),
            }
        )
        blocks.append(
            f"## Source {marker}: {title}\nSource ID: {source_id}\n\n"
            f"{text[:MAX_EXTRACT_CHARS_PER_FILE]}"
        )
    return "\n\n---\n\n".join(blocks), citations


def artifact_not_ready_sources(sources: list[Source]) -> list[dict[str, str | None]]:
    not_ready_sources: list[dict[str, str | None]] = []
    for source in sources:
        if (getattr(source, "full_text", None) or "").strip():
            continue
        command = getattr(source, "command", None)
        not_ready_sources.append(
            {
                "source_id": str(getattr(source, "id", "")),
                "title": getattr(source, "title", None) or "Untitled source",
                "command_id": str(command) if command is not None else None,
            }
        )
    return not_ready_sources


def configured_model_dir() -> Path | None:
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


async def resolve_artifact_model_route(
    artifact: object,
) -> tuple[str | None, str | None]:
    if getattr(artifact, "model_id", None):
        return artifact.model_id, getattr(artifact, "provider", None)
    model_dir = configured_model_dir()
    if model_dir is None:
        return None, getattr(artifact, "provider", None)
    try:
        local_models = await asyncio.to_thread(enumerate_models, model_dir)
        routes = await asyncio.to_thread(recommend_model_roles, local_models)
        route = next(
            (
                item
                for item in routes
                if item.role == artifact_model_role(artifact.artifact_type)
            ),
            None,
        )
        if route is None or route.model is None:
            return None, getattr(artifact, "provider", None)
        match_keys = inventory_model_match_keys(route.model.name, route.model.path)
        registered_models = await Model.get_models_by_type("language")
    except Exception as exc:
        logger.debug("Evidence Studio role routing skipped: {}", exc)
        return None, getattr(artifact, "provider", None)
    for model in registered_models:
        if model_match_key(getattr(model, "name", "")) in match_keys:
            model_id = str(getattr(model, "id", "") or "")
            if model_id:
                return model_id, getattr(model, "provider", None) or getattr(
                    artifact, "provider", None
                )
    return None, getattr(artifact, "provider", None)
