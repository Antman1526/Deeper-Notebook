"""Contracts for locally bounded, explicitly approved analysis runs.

This package intentionally ships with no executable backend. Platform-specific
sandboxes are added separately, after their enforcement self-tests exist.
"""

from open_notebook.analysis.contracts import AnalysisRun

__all__ = ["AnalysisRun"]
