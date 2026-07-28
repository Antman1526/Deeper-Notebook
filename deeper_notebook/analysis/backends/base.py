"""Small interface for platform-enforced analysis sandboxes."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from deeper_notebook.analysis.contracts import (
    AnalysisFailure,
    AnalysisRunState,
    OutputManifest,
    ResourceLimits,
    ScrubbedExecutionRequest,
)


class SandboxAvailability(BaseModel):
    """Self-test result used by routing before any execution is approved."""

    model_config = ConfigDict(extra="forbid")

    backend_id: str = Field(min_length=1, max_length=128)
    available: bool
    reason_code: str = Field(min_length=1, max_length=128)


class AnalysisExecutionResult(BaseModel):
    """Typed backend outcome; raw process errors are never part of this API."""

    model_config = ConfigDict(extra="forbid")

    state: AnalysisRunState
    output_manifest: OutputManifest | None = None
    failure: AnalysisFailure | None = None


class AnalysisBackend(ABC):
    """A backend must prove availability before it can ever execute code."""

    backend_id: str

    @abstractmethod
    async def availability(self) -> SandboxAvailability:
        """Run a platform-specific non-execution availability self-test."""

    @abstractmethod
    async def run(
        self,
        request: ScrubbedExecutionRequest,
        limits: ResourceLimits,
    ) -> AnalysisExecutionResult:
        """Execute only inside the future platform-enforced sandbox."""
