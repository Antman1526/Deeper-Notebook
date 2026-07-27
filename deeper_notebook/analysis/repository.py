"""SurrealDB persistence for metadata-only analysis contracts."""

from __future__ import annotations

from typing import Any

from loguru import logger

from deeper_notebook.analysis.contracts import AnalysisRun
from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_create,
    repo_query,
)


class AnalysisRunRepositoryError(RuntimeError):
    """A safe analysis persistence error suitable for API callers."""


def _one_record(result: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(result, list):
        if len(result) != 1:
            raise AnalysisRunRepositoryError(
                "Analysis persistence returned an invalid record"
            )
        result = result[0]
    if not isinstance(result, dict) or "id" not in result:
        raise AnalysisRunRepositoryError(
            "Analysis persistence returned an invalid record"
        )
    return result


def _assert_metadata_only(value: object) -> None:
    """Prevent a future caller from slipping source bodies into a run record."""
    forbidden_keys = {"content", "source_content", "source_text", "full_text"}
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden_keys:
                raise AnalysisRunRepositoryError(
                    "Analysis records cannot persist source content"
                )
            _assert_metadata_only(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_metadata_only(nested)


class AnalysisRunRepository:
    """Persist analysis state and validated output metadata, never source text."""

    async def create(self, run: AnalysisRun) -> AnalysisRun:
        try:
            data = self._storage_data(run)
            created = _one_record(await repo_create("analysis_run", data))
            return AnalysisRun.model_validate(created)
        except AnalysisRunRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to create analysis run")
            raise AnalysisRunRepositoryError("Failed to create analysis run") from exc

    async def get(self, run_id: str) -> AnalysisRun | None:
        try:
            rows = await repo_query(
                "SELECT * FROM $run", {"run": ensure_record_id(run_id)}
            )
            return AnalysisRun.model_validate(rows[0]) if rows else None
        except Exception as exc:
            logger.exception("Failed to load analysis run")
            raise AnalysisRunRepositoryError("Failed to load analysis run") from exc

    async def save_result(self, run: AnalysisRun) -> AnalysisRun:
        """Persist a terminal result and replace its metadata-only output index."""
        if run.id is None:
            raise AnalysisRunRepositoryError("Analysis run has no persisted id")
        canonical = AnalysisRun.model_validate(run.model_dump(mode="json"))
        if canonical.state not in {
            "succeeded",
            "failed",
            "sandbox_unavailable",
            "cancelled",
        }:
            raise AnalysisRunRepositoryError(
                "Only terminal analysis results can be saved"
            )
        try:
            rows = await repo_query(
                "UPDATE $run MERGE $data RETURN AFTER;",
                {
                    "run": ensure_record_id(run.id),
                    "data": self._storage_data(canonical),
                },
            )
            saved = AnalysisRun.model_validate(_one_record(rows))
            await repo_query(
                "DELETE analysis_output WHERE analysis_run_id = $run;",
                {"run": ensure_record_id(run.id)},
            )
            if canonical.output_manifest is not None:
                for output in canonical.output_manifest.outputs:
                    await repo_create(
                        "analysis_output",
                        {
                            "analysis_run_id": ensure_record_id(run.id),
                            **output.model_dump(mode="json"),
                        },
                    )
            return saved
        except AnalysisRunRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to persist analysis result")
            raise AnalysisRunRepositoryError(
                "Failed to persist analysis result"
            ) from exc

    @staticmethod
    def _storage_data(run: AnalysisRun) -> dict[str, Any]:
        data = run.model_dump(exclude={"id", "created", "updated"}, mode="json")
        if run.notebook_id:
            data["notebook_id"] = ensure_record_id(run.notebook_id)
        _assert_metadata_only(data)
        return data
