"""Artifact-generation orchestration behind a stable request contract."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from fastapi import HTTPException, status
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from open_notebook.domain.notebook import StudioArtifact, StudioWorkflowRun
from open_notebook.exceptions import InvalidInputError, NotFoundError
from open_notebook.studio.payloads import build_structured_payload
from open_notebook.studio.renderers import render_artifact_markdown
from open_notebook.studio.schemas import schema_for_artifact_type
from open_notebook.studio.structured_generation import (
    StructuredArtifactGenerationError,
    generate_structured_document,
)

from . import context, persistence
from .prompts import artifact_instruction


@dataclass(frozen=True)
class ArtifactGenerationRequest:
    artifact_id: str
    source_ids: list[str]
    requested_model_id: str | None = None


def _set_workflow_step_status(
    run: StudioWorkflowRun, step_ids: set[str], status_value: str
) -> None:
    run.steps = [
        {
            **step,
            "status": status_value
            if step.get("id") in step_ids
            else step.get("status", "pending"),
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
    return next(
        (
            run
            for run in runs
            if run.status in {"queued", "awaiting_approval", "running"}
        ),
        None,
    )


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


def _system_prompt(artifact: StudioArtifact) -> str:
    return f"""\
You are Evidence Studio inside Open Notebook Plus.

{artifact_instruction(artifact)}

Requirements:
- Stay faithful to the provided sources.
- Do not invent facts, dates, numbers, or quotes.
- Cite specific claims with the provided source markers.
- Use source markers like [S1] only in the schema's citation fields so readers can verify claims.
- If the sources are insufficient, say what is missing.
- Return data matching the required artifact schema.
"""


async def generate_artifact(request: ArtifactGenerationRequest) -> StudioArtifact:
    """Generate and persist one artifact using the request's optional source/model overrides."""
    try:
        artifact = await StudioArtifact.get(request.artifact_id)
    except (KeyError, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Studio artifact not found"
        )
    try:
        schema = schema_for_artifact_type(artifact.artifact_type)
    except InvalidInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

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
        _set_workflow_step_status(
            workflow_run, {"model_route", "artifact_generation"}, "running"
        )
        await workflow_run.save()

    try:
        selected_source_ids = request.source_ids or artifact.source_ids
        sources = await context.artifact_sources(artifact, selected_source_ids)
        not_ready_sources = context.artifact_not_ready_sources(sources)
        if not_ready_sources:
            raise context.sources_not_ready_exception(not_ready_sources)
        combined_context, citations = context.artifact_context(sources)
        if not combined_context.strip():
            raise InvalidInputError("No extracted source text is available")

        if request.requested_model_id is not None:
            artifact.model_id = request.requested_model_id
        model_id, provider = await context.resolve_artifact_model_route(artifact)
        artifact.model_id = model_id
        artifact.provider = provider
        chain = await context.provision_langchain_model(
            combined_context, model_id, "chat", max_tokens=3072
        )
        result = await generate_structured_document(
            model=chain,
            schema=schema,
            messages=[
                SystemMessage(content=_system_prompt(artifact)),
                HumanMessage(content=combined_context),
            ],
            timeout_seconds=context.env_int("ONP_STUDIO_PAGE_TIMEOUT_SEC", 180),
        )
        content = render_artifact_markdown(result.document)
        artifact.status = "completed"
        artifact.output_format = "markdown"
        artifact.citations = citations
        legacy_extras = persistence._artifact_output_payload(
            artifact, content, citations
        )
        legacy_extras.pop("content", None)
        artifact.output_payload = build_structured_payload(
            result.document,
            content,
            validation={
                "status": "valid",
                "errors": [],
                "strategy": result.strategy,
                "attempts": result.attempts,
            },
            extras=legacy_extras,
        )
        artifact.source_ids = [citation["source_id"] for citation in citations]
        try:
            artifact.export_paths = await asyncio.to_thread(
                persistence.persist_artifact_exports, artifact, content
            )
        except Exception as export_exc:
            logger.warning("Evidence Studio artifact export failed: {}", export_exc)
            artifact.export_paths = {}
        await artifact.save()
        if workflow_run is not None:
            workflow_run.status = "completed"
            _set_workflow_step_status(
                workflow_run, {"model_route", "artifact_generation"}, "completed"
            )
            await workflow_run.save()
        return artifact
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
                    workflow_run, {"model_route", "artifact_generation"}, "pending"
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
    except StructuredArtifactGenerationError as exc:
        artifact.status = "failed"
        artifact.output_payload = {
            "schema_version": 1,
            "validation": {
                "status": "invalid",
                "errors": exc.errors,
                "attempts": exc.attempts,
            },
            "error": "Artifact output did not match the required structure",
        }
        await artifact.save()
        if workflow_run is not None:
            workflow_run.status = "failed"
            _set_workflow_step_status(workflow_run, {"artifact_generation"}, "failed")
            await workflow_run.save()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Artifact generation failed"
        ) from exc
    except Exception as exc:
        logger.exception("Evidence Studio artifact generation failed")
        artifact.status = "failed"
        artifact.output_payload = {"error": persistence._brief(exc)}
        await artifact.save()
        if workflow_run is not None:
            workflow_run.status = "failed"
            _set_workflow_step_status(workflow_run, {"artifact_generation"}, "failed")
            await workflow_run.save()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Artifact generation failed"
        ) from exc
