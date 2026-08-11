"""Persistence for versioned evidence-evaluation runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger

from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_create,
    repo_query,
)
from deeper_notebook.evaluation.schemas import (
    ClaimVerdict,
    hash_source_text,
    resolve_source_states,
    validate_verdict_against_snapshots,
)

_SAFE_EVALUATION_ERROR = "Evaluation failed. Review local logs for details."
_RUN_PROJECTION = (
    "id, notebook_id, artifact_id, message_id, evaluator_version, model_id, "
    "metrics, error, created"
)


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

    async def latest_run(
        self,
        *,
        notebook_id: str,
        selector_field: str,
        selector_value: object,
    ) -> dict[str, Any] | None:
        """Read one newest run for a validated notebook-owned selector."""
        if selector_field not in {"artifact_id", "message_id"}:
            raise ValueError("unsupported evaluation selector")
        try:
            rows = await repo_query(
                f"SELECT {_RUN_PROJECTION} FROM evaluation_run "
                f"WHERE notebook_id = $notebook_id AND {selector_field} = ${selector_field} "
                "ORDER BY created DESC LIMIT 1",
                {"notebook_id": ensure_record_id(notebook_id), selector_field: selector_value},
            )
            return dict(rows[0]) if rows else None
        except Exception as exc:
            logger.exception("Failed to load latest evaluation run")
            raise EvaluationRepositoryError(
                "Failed to load latest evaluation run"
            ) from exc

    async def latest_runs_for_messages(
        self,
        *,
        notebook_id: str,
        message_ids: Sequence[str],
    ) -> list[dict[str, Any]]:
        """Read one newest run per message in one bounded DB request.

        A nested, parameterized subquery is used for each deduplicated message
        ID. Every branch has ``LIMIT 1`` so a message with a long evaluation
        history cannot materialize unbounded rows or starve another requested
        message. The request itself is capped by the router at 100 IDs.
        """
        if not message_ids:
            return []
        branches = ",\n".join(
            "  (SELECT "
            f"{_RUN_PROJECTION} FROM evaluation_run "
            "WHERE notebook_id = $notebook_id "
            f"AND message_id = $message_id_{index} "
            "ORDER BY created DESC LIMIT 1)"
            for index, _message_id in enumerate(message_ids)
        )
        variables: dict[str, object] = {
            "notebook_id": ensure_record_id(notebook_id),
            **{
                f"message_id_{index}": message_id
                for index, message_id in enumerate(message_ids)
            },
        }
        try:
            rows = await repo_query(
                "SELECT VALUE array::flatten([\n"
                f"{branches}\n"
                "]) ",
                variables,
            )
            # Depending on SurrealDB client/version, SELECT VALUE may return
            # either the flattened array directly or one wrapper row.
            if len(rows) == 1 and isinstance(rows[0], list):
                rows = rows[0]
            return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception as exc:
            logger.exception("Failed to load latest evaluation runs")
            raise EvaluationRepositoryError(
                "Failed to load latest evaluation runs"
            ) from exc

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

    async def list_verdicts_for_runs(
        self,
        evaluation_run_ids: Sequence[str],
    ) -> dict[str, list[ClaimVerdict]]:
        """Load verdicts for several runs in one parameterized query.

        Notebook chat uses a bounded latest-run batch endpoint. Keeping the
        verdict read batched prevents the endpoint from reintroducing one
        database round trip per visible message.
        """
        if not evaluation_run_ids:
            return {}
        try:
            rows = await repo_query(
                "SELECT evaluation_run_id, created, schema_version, claim, status, "
                "confidence, citation_markers, evidence, explanation "
                "FROM claim_verdict WHERE evaluation_run_id IN $run_ids "
                "ORDER BY created ASC",
                {"run_ids": [ensure_record_id(run_id) for run_id in evaluation_run_ids]},
            )
            result: dict[str, list[ClaimVerdict]] = {
                str(run_id): [] for run_id in evaluation_run_ids
            }
            for row in rows:
                run_id = row.get("evaluation_run_id")
                if run_id is None:
                    continue
                key = str(run_id)
                if key not in result:
                    continue
                verdict = ClaimVerdict.model_validate(
                    {
                        field: value
                        for field, value in row.items()
                        if field not in {"created", "evaluation_run_id"}
                    }
                )
                result[key].append(verdict)
            return result
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
