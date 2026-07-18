"""Selection for analysis backends, defaulting to a typed refusal."""

from __future__ import annotations

from collections.abc import Iterable

from open_notebook.analysis.backends.base import AnalysisBackend
from open_notebook.analysis.backends.disabled import DisabledBackend


async def select_analysis_backend(
    candidates: Iterable[AnalysisBackend] = (),
) -> AnalysisBackend:
    """Return only a backend that passed its own availability self-test.

    No candidate means no execution. This intentionally has no shell,
    environment, or existing-tool fallback path.
    """
    for backend in candidates:
        availability = await backend.availability()
        if availability.available:
            return backend
    return DisabledBackend()


__all__ = ["AnalysisBackend", "DisabledBackend", "select_analysis_backend"]
