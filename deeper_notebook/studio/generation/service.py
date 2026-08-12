"""Artifact-generation orchestration behind a stable request contract."""

from __future__ import annotations

import asyncio
import inspect
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import HTTPException, status
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from deeper_notebook.domain.notebook import StudioArtifact, StudioWorkflowRun
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import InvalidInputError, NotFoundError
from deeper_notebook.studio.payloads import build_structured_payload
from deeper_notebook.studio.renderers import render_artifact_markdown
from deeper_notebook.studio.schemas import schema_for_artifact_type
from deeper_notebook.studio.structured_generation import (
    StructuredArtifactGenerationError,
    generate_structured_document,
)

from . import context, persistence
from .prompts import artifact_instruction

_PUBLISHABLE_ARTIFACT_TYPES = {
    "report",
    "study_guide",
    "course_pack",
    "training_guide",
    "briefing",
    "faq",
    "timeline",
    "infographic",
    "slide_deck",
    "podcast_outline",
    "research_run",
}


def _strict_evidence_required(artifact: StudioArtifact) -> bool:
    """Default strict verification on only for publishable Studio exports."""
    if artifact.artifact_type not in _PUBLISHABLE_ARTIFACT_TYPES:
        return False
    raw = resolve_env("DEEPER_NOTEBOOK_STUDIO_STRICT_EVIDENCE", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _citation_source_map(
    sources: list[object],
) -> tuple[dict[str, object], dict[str, str]]:
    """Bind verifier input to the exact source text supplied to Studio."""
    from deeper_notebook.evaluation.verifier import CitationSource

    markers: dict[str, object] = {}
    snapshots: dict[str, str] = {}
    for index, source in enumerate(sources, start=1):
        source_id = str(getattr(source, "id", ""))
        text = (getattr(source, "full_text", None) or "").strip()
        if not source_id or not text:
            continue
        # The verifier must assess the same bounded context that the model saw.
        snapshot = text[: context.MAX_EXTRACT_CHARS_PER_FILE]
        citation_source = CitationSource(source_id=source_id, text=snapshot)
        markers[f"[S{index}]"] = citation_source
        snapshots[source_id] = snapshot
    return markers, snapshots


def _critical_verdicts(content: str, sources: list[object]) -> list[object]:
    from deeper_notebook.evaluation.verifier import verify_response_claims

    markers, _ = _citation_source_map(sources)
    return [
        verdict
        for verdict in verify_response_claims(content, markers)
        if verdict.status in {"contradicted", "unsupported"}
    ]


def _store_generated_output(
    artifact: StudioArtifact, result: object, content: str, citations: list[dict[str, str]]
) -> None:
    """Update only existing artifact fields so evaluation stays out of payloads."""
    artifact.output_format = "markdown"
    artifact.citations = citations
    legacy_extras = persistence._artifact_output_payload(artifact, content, citations)
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


async def _persist_artifact_evaluation(
    *, artifact: StudioArtifact, content: str, sources: list[object]
) -> None:
    """Persist evaluation after completion without touching artifact payloads."""
    from deeper_notebook.evaluation.repository import EvaluationRepository
    from deeper_notebook.evaluation.verifier import verify_response_claims

    try:
        markers, snapshots = _citation_source_map(sources)
        verdicts = verify_response_claims(content, markers)
        counts = {
            status: 0
            for status in (
                "supported",
                "partial",
                "contradicted",
                "unsupported",
                "uncited",
            )
        }
        for verdict in verdicts:
            counts[verdict.status] += 1
        await EvaluationRepository().create_run(
            notebook_id=str(artifact.notebook_id),
            artifact_id=str(artifact.id),
            evaluator_version="deterministic-v1",
            model_id=artifact.model_id,
            source_snapshots=snapshots,
            verdicts=verdicts,
            metrics={"status": "completed", "surface": "studio", "counts": counts},
        )
    except Exception as exc:
        # Artifact output is already durable. Evaluation must remain a sidecar.
        logger.warning(
            "Studio evidence evaluation skipped for {}: {}", artifact.id, exc
        )


def _schedule_artifact_evaluation(
    *, artifact: StudioArtifact, content: str, sources: list[object]
) -> None:
    task = asyncio.create_task(
        _persist_artifact_evaluation(
            artifact=artifact, content=content, sources=sources
        )
    )
    task.add_done_callback(
        lambda completed: completed.exception() if not completed.cancelled() else None
    )


@dataclass(frozen=True)
class ArtifactGenerationRequest:
    artifact_id: str
    source_ids: list[str]
    requested_model_id: str | None = None
    # Study Workbench supplies these additive hooks to fence a long-running
    # generation owner.  Existing Studio callers leave them unset and retain
    # the established save behavior.
    before_persist: Callable[[StudioArtifact], Awaitable[None] | None] | None = None
    persist_artifact: Callable[
        [StudioArtifact], Awaitable[StudioArtifact | None] | StudioArtifact | None
    ] | None = None


class ArtifactGenerationOwnershipLost(RuntimeError):
    """The caller no longer owns the artifact's durable generation lease."""


async def _before_persist(
    request: ArtifactGenerationRequest, artifact: StudioArtifact
) -> None:
    callback = request.before_persist
    if callback is None:
        return
    result = callback(artifact)
    if inspect.isawaitable(result):
        await result


async def _persist_artifact(
    request: ArtifactGenerationRequest, artifact: StudioArtifact
) -> StudioArtifact:
    await _before_persist(request, artifact)
    callback = request.persist_artifact
    if callback is None:
        await artifact.save()
        return artifact
    result = callback(artifact)
    persisted = await result if inspect.isawaitable(result) else result
    return persisted if isinstance(persisted, StudioArtifact) else artifact


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
You are Evidence Studio inside Deeper Notebook.

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
    await _before_persist(request, artifact)
    artifact.status = "running"
    await _persist_artifact(request, artifact)
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
            await _before_persist(request, artifact)
            artifact.model_id = request.requested_model_id
        model_id, provider = await context.resolve_artifact_model_route(artifact)
        await _before_persist(request, artifact)
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
            timeout_seconds=context.env_int("DEEPER_NOTEBOOK_STUDIO_PAGE_TIMEOUT_SEC", 180),
        )
        content = render_artifact_markdown(result.document)
        await _before_persist(request, artifact)
        _store_generated_output(artifact, result, content, citations)
        if _strict_evidence_required(artifact):
            critical = _critical_verdicts(content, sources)
            if critical:
                try:
                    repaired = await generate_structured_document(
                        model=chain,
                        schema=schema,
                        messages=[
                            SystemMessage(
                                content=(
                                    _system_prompt(artifact)
                                    + "\n\nThis is the one permitted evidence repair. "
                                    "Rewrite every contradicted or unsupported material "
                                    "claim so it is exactly supported by the selected [S#] "
                                    "source markers, or remove the claim."
                                )
                            ),
                            HumanMessage(content=combined_context),
                        ],
                        timeout_seconds=context.env_int(
                            "DEEPER_NOTEBOOK_STUDIO_PAGE_TIMEOUT_SEC", 180
                        ),
                    )
                    result = repaired
                    content = render_artifact_markdown(repaired.document)
                    await _before_persist(request, artifact)
                    _store_generated_output(artifact, repaired, content, citations)
                    critical = _critical_verdicts(content, sources)
                except Exception as repair_exc:
                    # Retain the original structured output for review. A repair
                    # failure must not turn a generated artifact into an error blob.
                    logger.warning("Studio strict evidence repair failed: {}", repair_exc)
                # Keep the generated document reviewable, but do not publish it
                # while a material claim remains contradicted or unsupported.
                if critical:
                    await _before_persist(request, artifact)
                    artifact.status = "failed"
                    await _persist_artifact(request, artifact)
                    _schedule_artifact_evaluation(
                        artifact=artifact, content=content, sources=sources
                    )
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail={
                            "code": "strict_evidence_failed",
                            "message": "Publishable output contains contradicted or unsupported claims.",
                            "critical_claim_count": len(critical),
                        },
                    )
        await _before_persist(request, artifact)
        artifact.status = "completed"
        try:
            artifact.export_paths = await asyncio.to_thread(
                persistence.persist_artifact_exports, artifact, content
            )
        except Exception as export_exc:
            logger.warning("Evidence Studio artifact export failed: {}", export_exc)
            artifact.export_paths = {}
        await _persist_artifact(request, artifact)
        if workflow_run is not None:
            workflow_run.status = "completed"
            _set_workflow_step_status(
                workflow_run, {"model_route", "artifact_generation"}, "completed"
            )
            await workflow_run.save()
        _schedule_artifact_evaluation(
            artifact=artifact, content=content, sources=sources
        )
        return artifact
    except ArtifactGenerationOwnershipLost:
        # The Study adapter owns the conditional persistence boundary.  A
        # reclaimed lease must escape without a stale failure/status write.
        raise
    except HTTPException as exc:
        if (
            exc.status_code == status.HTTP_409_CONFLICT
            and isinstance(exc.detail, dict)
            and exc.detail.get("code") == "sources_not_ready"
        ):
            await _before_persist(request, artifact)
            artifact.status = "pending"
            await _persist_artifact(request, artifact)
            if workflow_run is not None:
                workflow_run.status = "queued"
                _set_workflow_step_status(
                    workflow_run, {"model_route", "artifact_generation"}, "pending"
                )
                await workflow_run.save()
            raise
        await _before_persist(request, artifact)
        artifact.status = "failed"
        await _persist_artifact(request, artifact)
        if workflow_run is not None:
            workflow_run.status = "failed"
            _set_workflow_step_status(workflow_run, {"artifact_generation"}, "failed")
            await workflow_run.save()
        raise
    except StructuredArtifactGenerationError as exc:
        await _before_persist(request, artifact)
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
        await _persist_artifact(request, artifact)
        if workflow_run is not None:
            workflow_run.status = "failed"
            _set_workflow_step_status(workflow_run, {"artifact_generation"}, "failed")
            await workflow_run.save()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Artifact generation failed"
        ) from exc
    except Exception as exc:
        logger.exception("Evidence Studio artifact generation failed")
        await _before_persist(request, artifact)
        artifact.status = "failed"
        artifact.output_payload = {"error": persistence._brief(exc)}
        await _persist_artifact(request, artifact)
        if workflow_run is not None:
            workflow_run.status = "failed"
            _set_workflow_step_status(workflow_run, {"artifact_generation"}, "failed")
            await workflow_run.save()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Artifact generation failed"
        ) from exc
