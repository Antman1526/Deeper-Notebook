"""The only initial analysis backend: a typed, non-executing refusal."""

from __future__ import annotations

from open_notebook.analysis.backends.base import (
    AnalysisBackend,
    AnalysisExecutionResult,
    SandboxAvailability,
)
from open_notebook.analysis.contracts import (
    AnalysisFailure,
    ResourceLimits,
    ScrubbedExecutionRequest,
)


class DisabledBackend(AnalysisBackend):
    """Fail closed until a platform sandbox has passed its enforcement tests.

    This module intentionally does not import subprocess, shell helpers,
    environment access, or the legacy ``opencode_run`` tool.
    """

    backend_id = "disabled"

    async def availability(self) -> SandboxAvailability:
        return SandboxAvailability(
            backend_id=self.backend_id,
            available=False,
            reason_code="sandbox_unavailable",
        )

    async def run(
        self,
        request: ScrubbedExecutionRequest,
        limits: ResourceLimits,
    ) -> AnalysisExecutionResult:
        del request, limits
        return AnalysisExecutionResult(
            state="sandbox_unavailable",
            failure=AnalysisFailure.for_code("sandbox_unavailable"),
        )
