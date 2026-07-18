"""Persistence for versioned evidence-evaluation runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from open_notebook.database.repository import ensure_record_id, repo_create, repo_query
from open_notebook.evaluation.schemas import (
    ClaimVerdict,
    hash_source_text,
    resolve_source_states,
    validate_verdict_against_snapshots,
)

_SAFE_EVALUATION_ERROR = "Evaluation failed. Review local logs for details."


class EvaluationRepositoryError(RuntimeError):
    """A safe persistence failure suitable for callers to surface."""


@dataclass(frozen=True)
class StoredEvaluationRun:
    id: str


def _record_from_create(
    result: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, Any]:
    if isinstance(result, list):
        if len(result) != 1:
            raise EvaluationRepositoryError(
                "Evaluation persistence returned an invalid record"
            )
        result = result[0]
    if not isinstance(result, dict) or "id" not in result:
        raise EvaluationRepositoryError(
            "Evaluation persistence returned an invalid record"
        )
    return result


class EvaluationRepository:
    """Write verified snapshots and read them with honest source-drift state."""

    async def create_run(
        self,
        *,
        notebook_id: str,
        evaluator_version: str,
        model_id: str | None,
        source_snapshots: Mapping[str, str],
        verdicts: Sequence[ClaimVerdict],
        artifact_id: str | None = None,
        message_id: str | None = None,
        metrics: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> StoredEvaluationRun:
        """Persist a run only after quotes have matched their input snapshots."""
        for verdict in verdicts:
            validate_verdict_against_snapshots(verdict, source_snapshots)

        source_content_hashes = [
            {"source_id": source_id, "sha256": hash_source_text(source_text)}
            for source_id, source_text in sorted(source_snapshots.items())
        ]
        try:
            run_data: dict[str, Any] = {
                "notebook_id": ensure_record_id(notebook_id),
                "artifact_id": ensure_record_id(artifact_id) if artifact_id else None,
                "message_id": message_id,
                "evaluator_version": evaluator_version,
                "model_id": model_id,
                "source_content_hashes": source_content_hashes,
                "metrics": dict(metrics or {}),
                "error": _SAFE_EVALUATION_ERROR if error else None,
            }
            run = _record_from_create(await repo_create("evaluation_run", run_data))
            run_id = str(run["id"])

            for verdict in verdicts:
                verdict_data = verdict.model_dump(mode="json")
                verdict_data["evaluation_run_id"] = ensure_record_id(run_id)
                verdict_data["source_state"] = self._aggregate_source_state(verdict)
                _record_from_create(await repo_create("claim_verdict", verdict_data))
            return StoredEvaluationRun(id=run_id)
        except EvaluationRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to persist evaluation run")
            raise EvaluationRepositoryError("Failed to persist evaluation run") from exc

    async def list_verdicts(
        self,
        evaluation_run_id: str,
        *,
        current_source_texts: Mapping[str, str] | None = None,
    ) -> list[ClaimVerdict]:
        """Return saved verdicts, flagging changed sources without relocation."""
        try:
            rows = await repo_query(
                "SELECT created, schema_version, claim, status, confidence, citation_markers, evidence, "
                "explanation FROM claim_verdict WHERE evaluation_run_id = $run "
                "ORDER BY created ASC",
                {"run": ensure_record_id(evaluation_run_id)},
            )
            # SurrealDB requires the ordering idiom in the selected fields.
            # Audit metadata is not part of the public verdict contract.
            verdicts = [
                ClaimVerdict.model_validate(
                    {key: value for key, value in row.items() if key != "created"}
                )
                for row in rows
            ]
            if current_source_texts is None:
                return verdicts
            return [
                resolve_source_states(verdict, current_source_texts)
                for verdict in verdicts
            ]
        except Exception as exc:
            logger.exception("Failed to load evaluation verdicts")
            raise EvaluationRepositoryError(
                "Failed to load evaluation verdicts"
            ) from exc

    @staticmethod
    def _aggregate_source_state(verdict: ClaimVerdict) -> str:
        if any(span.source_state == "source_changed" for span in verdict.evidence):
            return "source_changed"
        return "current"
