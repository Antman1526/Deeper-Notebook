from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from surreal_commands import registry

from api.command_service import CommandService

router = APIRouter()


class CommandExecutionRequest(BaseModel):
    command: str = Field(
        ..., description="Command function name (e.g., 'process_text')"
    )
    app: str = Field(..., description="Persisted application identifier")
    input: dict[str, Any] = Field(..., description="Arguments to pass to the command")


class CommandJobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class CommandJobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    progress: Optional[dict[str, Any]] = None


@router.post("/commands/jobs", response_model=CommandJobResponse)
async def execute_command(request: CommandExecutionRequest):
    """
    Submit a command for background processing.
    Returns immediately with job ID for status tracking.

    Example request:
    {
        "command": "process_text",
        "app": "<persisted_app_identifier>",
        "input": {
            "text": "Hello world",
            "operation": "uppercase"
        }
    }
    """
    try:
        # Submit command using app name (not module name)
        job_id = await CommandService.submit_command_job(
            module_name=request.app,  # Preserve the persisted identifier.
            command_name=request.command,
            command_args=request.input,
        )

        return CommandJobResponse(
            job_id=job_id,
            status="submitted",
            message=f"Command '{request.command}' submitted successfully",
        )

    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error submitting command: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to submit command")


@router.get("/commands/jobs/{job_id}", response_model=CommandJobStatusResponse)
async def get_command_job_status(job_id: str):
    """Get the status of a specific command job."""
    try:
        status_data = await CommandService.get_command_status(job_id)
        # v0.7.87 — service now returns None for missing jobs; map that
        # to a real 404 instead of returning 200 with a fake
        # `status="unknown"` payload that callers had to special-case.
        if status_data is None:
            raise HTTPException(status_code=404, detail="Command job not found")
        return CommandJobStatusResponse(**status_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch job status")


@router.get("/commands/jobs", response_model=list[dict[str, Any]])
async def list_command_jobs(
    command_filter: Optional[str] = Query(None, description="Filter by command name"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Maximum number of jobs to return"),
):
    """List command jobs with optional filtering"""
    try:
        jobs = await CommandService.list_command_jobs(
            command_filter=command_filter, status_filter=status_filter, limit=limit
        )
        return jobs

    except HTTPException:
        # v0.7.135 — re-raise typed HTTPExceptions so the generic
        # `except Exception` below doesn't clobber 4xx/5xx to 500.
        # Mechanically enforced by tests/test_v0_7_135_meta.py.
        raise
    except Exception as e:
        logger.error(f"Error listing command jobs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list command jobs")


@router.delete("/commands/jobs/{job_id}")
async def cancel_command_job(job_id: str):
    """Cancel a running command job.

    v0.7.87 — the service implementation now actually writes the
    `canceled` signal back to surreal_commands instead of returning
    True without doing anything. Returns 404 when the job doesn't
    exist; 409 Conflict when the job exists but isn't in a
    cancellable state (already completed, failed, or canceled).
    """
    try:
        # First peek at the job's status so we can return precise codes.
        status_data = await CommandService.get_command_status(job_id)
        if status_data is None:
            raise HTTPException(status_code=404, detail="Command job not found")
        current_status = (status_data.get("status") or "").lower()
        if current_status not in {"new", "queued", "running"}:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Command job is not in a cancellable state "
                    f"(current: {current_status or 'unknown'})"
                ),
            )
        success = await CommandService.cancel_command_job(job_id)
        return {"job_id": job_id, "cancelled": success}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling command job: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to cancel command job")


@router.get("/commands/registry/debug")
async def debug_registry():
    """Debug endpoint to see what commands are registered"""
    try:
        # Get all registered commands
        all_items = registry.get_all_commands()

        # Create JSON-serializable data
        command_items = []
        for item in all_items:
            try:
                command_items.append(
                    {
                        "app_id": item.app_id,
                        "name": item.name,
                        "full_id": f"{item.app_id}.{item.name}",
                    }
                )
            except Exception as item_error:
                logger.error(f"Error processing item: {item_error}")

        # Get the basic command structure
        try:
            commands_dict: dict[str, list[str]] = {}
            for item in all_items:
                if item.app_id not in commands_dict:
                    commands_dict[item.app_id] = []
                commands_dict[item.app_id].append(item.name)
        except Exception:
            commands_dict = {}

        return {
            "total_commands": len(all_items),
            "commands_by_app": commands_dict,
            "command_items": command_items,
        }

    except Exception as e:
        logger.error(f"Error debugging registry: {str(e)}")
        return {
            "error": str(e),
            "total_commands": 0,
            "commands_by_app": {},
            "command_items": [],
        }
