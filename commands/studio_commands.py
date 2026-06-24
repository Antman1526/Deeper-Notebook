"""Background commands for Evidence Studio artifact generation."""

from typing import Optional

from pydantic import BaseModel
from surreal_commands import CommandInput, CommandOutput, command


class StudioArtifactGenerationInput(CommandInput):
    artifact_id: str
    workflow_run_id: Optional[str] = None


class StudioArtifactGenerationOutput(CommandOutput):
    success: bool
    artifact_id: str
    workflow_run_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None


def _dump_response(value) -> dict:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {}


@command(
    "generate_studio_artifact",
    app="open_notebook",
    retry={"max_attempts": 1},
)
async def generate_studio_artifact_command(
    input_data: StudioArtifactGenerationInput,
) -> StudioArtifactGenerationOutput:
    try:
        from api.routers.studio import generate_studio_artifact

        response = await generate_studio_artifact(input_data.artifact_id)
        payload = _dump_response(response)
        return StudioArtifactGenerationOutput(
            success=True,
            artifact_id=input_data.artifact_id,
            workflow_run_id=input_data.workflow_run_id,
            status=str(payload.get("status") or "completed"),
        )
    except Exception as exc:
        return StudioArtifactGenerationOutput(
            success=False,
            artifact_id=input_data.artifact_id,
            workflow_run_id=input_data.workflow_run_id,
            status="failed",
            error_message=str(exc),
        )
