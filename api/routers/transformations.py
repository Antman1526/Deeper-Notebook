from typing import List

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from api.models import (
    DefaultPromptResponse,
    DefaultPromptUpdate,
    TransformationCreate,
    TransformationExecuteRequest,
    TransformationExecuteResponse,
    TransformationResponse,
    TransformationUpdate,
)
from api.utils.iso import iso  # v0.7.183 — Safari-safe datetime serialization
from deeper_notebook.ai.models import Model
from deeper_notebook.domain.transformation import DefaultPrompts, Transformation
from deeper_notebook.environment import resolve_env
from deeper_notebook.exceptions import (
    DeeperNotebookError,
    InvalidInputError,
    NotFoundError,
)
from deeper_notebook.graphs.transformation import graph as transformation_graph

router = APIRouter()


@router.get("/transformations", response_model=list[TransformationResponse])
async def get_transformations(
    # v0.7.163 — Pagination follow-through (same pattern as v0.7.159's
    # Note.get_all fix). Transformation tables are typically <50 entries
    # so this isn't a current crisis like /notes was, but
    # `SELECT * FROM transformation` with no LIMIT is the same shape
    # bug — an integration script populating thousands of rows could
    # silently return multi-MB JSON. Default cap = 200; hard ceiling
    # 1000 prevents bypass by curious callers.
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
    """Get all transformations."""
    try:
        transformations = await Transformation.get_all(
            order_by="name asc",
            limit=limit,
            offset=offset,
        )

        return [
            TransformationResponse(
                id=transformation.id or "",
                name=transformation.name,
                title=transformation.title,
                description=transformation.description,
                prompt=transformation.prompt,
                apply_default=transformation.apply_default,
                created=iso(transformation.created),
                updated=iso(transformation.updated),
            )
            for transformation in transformations
        ]
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error fetching transformations: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching transformations")


class OptimizePromptRequest(BaseModel):
    """v0.8.68 — SkillOpt prompt optimization (microsoft/SkillOpt, MIT)."""

    source_ids: list[str] = Field(..., min_length=2, max_length=10)
    criteria: str = Field(..., min_length=10, max_length=4000)
    epochs: int = Field(2, ge=1, le=4)
    edit_budget: int = Field(4, ge=1, le=8)


@router.post("/transformations/{transformation_id}/optimize")
async def optimize_transformation_prompt(
    transformation_id: str, request: OptimizePromptRequest
):
    """v0.8.68 — submit an async SkillOpt run that optimizes this
    transformation's prompt against example sources, judged by the given
    criteria. Returns a job id; poll /commands/{job_id}; the completed
    job's result carries original/optimized prompts for review — applying
    the result is an explicit PUT /transformations/{id} by the client."""
    import asyncio as _asyncio
    import os as _os

    from surreal_commands import submit_command

    from deeper_notebook.prompt_optimizer import skillopt_available

    try:
        if not skillopt_available():
            raise HTTPException(
                status_code=501,
                detail=(
                    "Prompt optimization requires the 'skillopt' package, "
                    "which is not installed in this environment."
                ),
            )
        transformation = await Transformation.get(transformation_id)
        if not transformation:
            raise HTTPException(status_code=404, detail="Transformation not found")

        try:
            import commands.prompt_optimizer_commands  # noqa: F401
        except ImportError as exc:
            logger.error(f"prompt optimizer command unavailable: {exc}")
            raise HTTPException(status_code=501, detail="Optimizer unavailable")

        _timeout = float(
            resolve_env("DEEPER_NOTEBOOK_SUBMIT_COMMAND_TIMEOUT_SEC", "10").strip()
            or 10
        )
        job_id = await _asyncio.wait_for(
            _asyncio.to_thread(
                submit_command,
                "open_notebook",
                "optimize_prompt",
                {
                    "transformation_id": transformation_id,
                    "source_ids": request.source_ids,
                    "criteria": request.criteria,
                    "epochs": request.epochs,
                    "edit_budget": request.edit_budget,
                },
            ),
            timeout=_timeout,
        )
        if not job_id:
            raise HTTPException(status_code=500, detail="Failed to submit job")
        return {
            "job_id": str(job_id),
            "message": "Prompt optimization started — this runs many model "
            "calls and can take several minutes.",
        }
    except HTTPException:
        raise
    except (NotFoundError, InvalidInputError):
        raise
    except _asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Job queue is saturated")
    except Exception as e:
        logger.error(f"Error submitting prompt optimization: {e}")
        raise HTTPException(status_code=500, detail="Failed to start optimization")


@router.post("/transformations", response_model=TransformationResponse)
async def create_transformation(transformation_data: TransformationCreate):
    """Create a new transformation."""
    try:
        new_transformation = Transformation(
            name=transformation_data.name,
            title=transformation_data.title,
            description=transformation_data.description,
            prompt=transformation_data.prompt,
            apply_default=transformation_data.apply_default,
        )
        await new_transformation.save()

        return TransformationResponse(
            id=new_transformation.id or "",
            name=new_transformation.name,
            title=new_transformation.title,
            description=new_transformation.description,
            prompt=new_transformation.prompt,
            apply_default=new_transformation.apply_default,
            created=iso(new_transformation.created),
            updated=iso(new_transformation.updated),
        )
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error creating transformation: {str(e)}")
        raise HTTPException(status_code=500, detail="Error creating transformation")


@router.post("/transformations/execute", response_model=TransformationExecuteResponse)
async def execute_transformation(execute_request: TransformationExecuteRequest):
    """Execute a transformation on input text."""
    try:
        # Validate transformation exists
        transformation = await Transformation.get(execute_request.transformation_id)
        if not transformation:
            raise HTTPException(status_code=404, detail="Transformation not found")

        # Validate model exists
        model = await Model.get(execute_request.model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        # v0.7.95 — wrap the LLM call in wait_for. Transformations are
        # user-defined prompts of arbitrary length; a stuck local model
        # would otherwise hang the request indefinitely. Default 180s
        # matches the Studio per-page timeout (same class of LLM call);
        # tunable via env for cloud users running heavy transformations.
        import asyncio
        import os

        _xform_timeout = float(
            resolve_env("DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC", "180").strip()
            or 180
        )
        try:
            result = await asyncio.wait_for(
                transformation_graph.ainvoke(
                    dict(  # type: ignore[arg-type]
                        input_text=execute_request.input_text,
                        transformation=transformation,
                    ),
                    config=dict(configurable={"model_id": execute_request.model_id}),
                ),
                timeout=_xform_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail=(
                    f"Transformation timed out after {_xform_timeout}s. "
                    "The chat model may be loading or overloaded. Try again, "
                    "or raise DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC."
                ),
            ) from exc

        # v0.7.75 — defensive access to `output`. The transformation graph
        # currently returns a TypedDict shape but the same generic chat
        # graphs were already bitten by the dict-vs-Pydantic variance
        # (fixed in v0.7.52/55/56). Use isinstance/getattr dual-path so
        # the endpoint can't 500 with KeyError just because LangGraph
        # changed the wrapper shape in a future release.
        if isinstance(result, dict):
            output_text = result.get("output", "")
        else:
            output_text = getattr(result, "output", "") or ""

        return TransformationExecuteResponse(
            output=output_text,
            transformation_id=execute_request.transformation_id,
            model_id=execute_request.model_id,
        )

    except HTTPException:
        raise
    except DeeperNotebookError:
        raise  # Let global exception handlers return proper status codes
    except Exception as e:
        logger.error(f"Error executing transformation: {str(e)}")
        raise HTTPException(status_code=500, detail="Error executing transformation")


@router.get("/transformations/default-prompt", response_model=DefaultPromptResponse)
async def get_default_prompt():
    """Get the default transformation prompt."""
    try:
        default_prompts: DefaultPrompts = await DefaultPrompts.get_instance()  # type: ignore[assignment]

        return DefaultPromptResponse(
            transformation_instructions=default_prompts.transformation_instructions
            or ""
        )
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error fetching default prompt: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching default prompt")


@router.put("/transformations/default-prompt", response_model=DefaultPromptResponse)
async def update_default_prompt(prompt_update: DefaultPromptUpdate):
    """Update the default transformation prompt."""
    try:
        default_prompts: DefaultPrompts = await DefaultPrompts.get_instance()  # type: ignore[assignment]

        default_prompts.transformation_instructions = (
            prompt_update.transformation_instructions
        )
        await default_prompts.update()

        return DefaultPromptResponse(
            transformation_instructions=default_prompts.transformation_instructions
        )
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except (NotFoundError, InvalidInputError):
        # v0.7.181 — bubble typed exceptions to the global handlers
        # in api/main.py (NotFoundError → 404, InvalidInputError → 400).
        raise
    except Exception as e:
        logger.error(f"Error updating default prompt: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating default prompt")


@router.get(
    "/transformations/{transformation_id}", response_model=TransformationResponse
)
async def get_transformation(transformation_id: str):
    """Get a specific transformation by ID."""
    try:
        transformation = await Transformation.get(transformation_id)
        if not transformation:
            raise HTTPException(status_code=404, detail="Transformation not found")

        return TransformationResponse(
            id=transformation.id or "",
            name=transformation.name,
            title=transformation.title,
            description=transformation.description,
            prompt=transformation.prompt,
            apply_default=transformation.apply_default,
            created=iso(transformation.created),
            updated=iso(transformation.updated),
        )
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — let the global handler at api/main.py:567 map to
        # HTTP 404; previously the generic except below clobbered to 500.
        raise
    except Exception as e:
        logger.error(f"Error fetching transformation {transformation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching transformation")


@router.put(
    "/transformations/{transformation_id}", response_model=TransformationResponse
)
async def update_transformation(
    transformation_id: str, transformation_update: TransformationUpdate
):
    """Update a transformation."""
    try:
        transformation = await Transformation.get(transformation_id)
        if not transformation:
            raise HTTPException(status_code=404, detail="Transformation not found")

        # Update only provided fields
        if transformation_update.name is not None:
            transformation.name = transformation_update.name
        if transformation_update.title is not None:
            transformation.title = transformation_update.title
        if transformation_update.description is not None:
            transformation.description = transformation_update.description
        if transformation_update.prompt is not None:
            transformation.prompt = transformation_update.prompt
        if transformation_update.apply_default is not None:
            transformation.apply_default = transformation_update.apply_default

        await transformation.save()

        return TransformationResponse(
            id=transformation.id or "",
            name=transformation.name,
            title=transformation.title,
            description=transformation.description,
            prompt=transformation.prompt,
            apply_default=transformation.apply_default,
            created=iso(transformation.created),
            updated=iso(transformation.updated),
        )
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — see get_transformation above.
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating transformation {transformation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error updating transformation")


@router.delete("/transformations/{transformation_id}")
async def delete_transformation(transformation_id: str):
    """Delete a transformation."""
    try:
        transformation = await Transformation.get(transformation_id)
        if not transformation:
            raise HTTPException(status_code=404, detail="Transformation not found")

        await transformation.delete()

        return {"message": "Transformation deleted successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — see get_transformation above.
        raise
    except Exception as e:
        logger.error(f"Error deleting transformation {transformation_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting transformation")
