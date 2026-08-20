"""SurrealDB persistence for resumable research runs."""

from __future__ import annotations

from typing import Any

from loguru import logger

from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_create,
    repo_query,
)
from deeper_notebook.research.state import (
    ResearchRun,
    ResearchStage,
    ResearchStageResult,
)


class ResearchRunRepositoryError(RuntimeError):
    """A safe research-run persistence error suitable for API callers."""


_DATABASE_METADATA_FIELDS = frozenset({"created", "updated"})


def _one_record(result: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(result, list):
        if len(result) != 1:
            raise ResearchRunRepositoryError(
                "Research persistence returned an invalid record"
            )
        result = result[0]
    if not isinstance(result, dict) or "id" not in result:
        raise ResearchRunRepositoryError(
            "Research persistence returned an invalid record"
        )
    return result


def _run_from_record(record: dict[str, Any] | list[dict[str, Any]]) -> ResearchRun:
    """Deserialize persistence records without leaking database audit fields."""
    data = _one_record(record)
    return ResearchRun.model_validate(
        {
            key: value
            for key, value in data.items()
            if key not in _DATABASE_METADATA_FIELDS
        }
    )


class ResearchRunRepository:
    """Persist state transitions atomically enough for cooperative restarts."""

    async def create(self, run: ResearchRun) -> ResearchRun:
        """Store a new run before its first background command is submitted."""
        try:
            data = run.model_dump(exclude={"id"}, mode="json")
            if run.notebook_id:
                data["notebook_id"] = ensure_record_id(run.notebook_id)
            return _run_from_record(await repo_create("research_run", data))
        except ResearchRunRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to create research run")
            raise ResearchRunRepositoryError("Failed to create research run") from exc

    async def get(self, run_id: str) -> ResearchRun | None:
        try:
            rows = await repo_query(
                "SELECT * FROM $run", {"run": ensure_record_id(run_id)}
            )
            if not rows:
                return None
            return _run_from_record(rows[0])
        except Exception as exc:
            logger.exception("Failed to load research run")
            raise ResearchRunRepositoryError("Failed to load research run") from exc

    async def save_stage_result(
        self,
        run: ResearchRun,
        stage: ResearchStage,
        result: ResearchStageResult,
    ) -> ResearchRun:
        """Save one stage once; a replay returns the checkpointed run unchanged."""
        if run.id is None:
            raise ResearchRunRepositoryError("Research run has no persisted id")
        if run.cancelled or run.has_completed(stage):
            return run
        updated_run = run.with_stage_result(stage, result)
        try:
            rows = await repo_query(
                "UPDATE $run MERGE $data WHERE stage = $stage AND cancelled = false RETURN AFTER;",
                {
                    "run": ensure_record_id(run.id),
                    "stage": stage,
                    "data": self._storage_data(updated_run),
                },
            )
            if rows:
                return _run_from_record(rows[0])
            # Another worker either checkpointed this stage or cancelled. Never
            # replay side effects; read the canonical durable state instead.
            current = await self.get(run.id)
            if current is None:
                raise ResearchRunRepositoryError(
                    "Research run disappeared during update"
                )
            return current
        except ResearchRunRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to checkpoint research stage")
            raise ResearchRunRepositoryError(
                "Failed to checkpoint research stage"
            ) from exc

    async def request_cancellation(self, run_id: str) -> ResearchRun | None:
        """Make cancellation durable; active workers observe it between stages."""
        try:
            rows = await repo_query(
                "UPDATE $run SET cancelled = true RETURN AFTER;",
                {"run": ensure_record_id(run_id)},
            )
            return _run_from_record(rows[0]) if rows else None
        except Exception as exc:
            logger.exception("Failed to cancel research run")
            raise ResearchRunRepositoryError("Failed to cancel research run") from exc

    async def save_approval_decisions(
        self,
        run: ResearchRun,
        decisions: dict[str, bool],
    ) -> ResearchRun:
        """Save explicit source choices without reopening completed work."""
        if run.id is None:
            raise ResearchRunRepositoryError("Research run has no persisted id")
        if run.cancelled:
            return run
        updated_run = run.with_approval_decisions(decisions)
        try:
            rows = await repo_query(
                "UPDATE $run SET approval_decisions = $decisions "
                "WHERE cancelled = false RETURN AFTER;",
                {
                    "run": ensure_record_id(run.id),
                    "decisions": updated_run.approval_decisions,
                },
            )
            if rows:
                return _run_from_record(rows[0])
            current = await self.get(run.id)
            if current is None:
                raise ResearchRunRepositoryError(
                    "Research run disappeared during approval"
                )
            return current
        except ResearchRunRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to save research approvals")
            raise ResearchRunRepositoryError(
                "Failed to save research approvals"
            ) from exc

    async def set_command_id(self, run_id: str, command_id: str) -> ResearchRun:
        try:
            rows = await repo_query(
                "UPDATE $run SET command_id = $command_id RETURN AFTER;",
                {"run": ensure_record_id(run_id), "command_id": command_id},
            )
            return _run_from_record(rows)
        except ResearchRunRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to attach research command")
            raise ResearchRunRepositoryError(
                "Failed to attach research command"
            ) from exc

    @staticmethod
    def _storage_data(run: ResearchRun) -> dict[str, Any]:
        data = run.model_dump(exclude={"id", "created", "updated"}, mode="json")
        if run.notebook_id:
            data["notebook_id"] = ensure_record_id(run.notebook_id)
        return data
