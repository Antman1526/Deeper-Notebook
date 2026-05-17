from typing import List

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.models import (
    DefaultPromptResponse,
    DefaultPromptUpdate,
    TransformationCreate,
    TransformationExecuteRequest,
    TransformationExecuteResponse,
    TransformationResponse,
    TransformationUpdate,
)
from open_notebook.ai.models import Model
from open_notebook.domain.transformation import DefaultPrompts, Transformation
from open_notebook.exceptions import InvalidInputError, OpenNotebookError
from open_notebook.graphs.transformation import graph as transformation_graph

router = APIRouter()


@router.get("/transformations", response_model=List[TransformationResponse])
async def get_transformations():
    """Get all transformations."""
    try:
        transformations = await Transformation.get_all(order_by="name asc")

        return [
            TransformationResponse(
                id=transformation.id or "",
                name=transformation.name,
                title=transformation.title,
                description=transformation.description,
                prompt=transformation.prompt,
                apply_default=transformation.apply_default,
                created=str(transformation.created),
                updated=str(transformation.updated),
            )
            for transformation in transformations
        ]
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error fetching transformations: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching transformations: {str(e)}"
        )


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
            created=str(new_transformation.created),
            updated=str(new_transformation.updated),
        )
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        # v0.7.108 — re-raise typed HTTPExceptions so the next
        # `except Exception` doesn't clobber them to 500.
        raise
    except Exception as e:
        logger.error(f"Error creating transformation: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error creating transformation: {str(e)}"
        )


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
            os.environ.get("ONP_TRANSFORMATION_TIMEOUT_SEC", "180").strip() or 180
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
                    "or raise ONP_TRANSFORMATION_TIMEOUT_SEC."
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
    except OpenNotebookError:
        raise  # Let global exception handlers return proper status codes
    except Exception as e:
        logger.error(f"Error executing transformation: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error executing transformation: {str(e)}"
        )


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
    except Exception as e:
        logger.error(f"Error fetching default prompt: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching default prompt: {str(e)}"
        )


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
    except Exception as e:
        logger.error(f"Error updating default prompt: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating default prompt: {str(e)}"
        )


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
            created=str(transformation.created),
            updated=str(transformation.updated),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching transformation {transformation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error fetching transformation: {str(e)}"
        )


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
            created=str(transformation.created),
            updated=str(transformation.updated),
        )
    except HTTPException:
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating transformation {transformation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error updating transformation: {str(e)}"
        )


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
    except Exception as e:
        logger.error(f"Error deleting transformation {transformation_id}: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error deleting transformation: {str(e)}"
        )
