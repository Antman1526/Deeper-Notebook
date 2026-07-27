"""Idempotent stage runner for persisted research work."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol

from loguru import logger
from surreal_commands import get_command_status, submit_command

from deeper_notebook.research.repository import ResearchRunRepository
from deeper_notebook.research.state import (
    ResearchRun,
    ResearchStage,
    ResearchStageResult,
)

ResearchStageHandler = Callable[[ResearchRun], Awaitable[ResearchStageResult]]


class ResearchRunStore(Protocol):
    async def get(self, run_id: str) -> ResearchRun | None: ...

    async def save_stage_result(
        self,
        run: ResearchRun,
        stage: ResearchStage,
        result: ResearchStageResult,
    ) -> ResearchRun: ...

    async def request_cancellation(self, run_id: str) -> ResearchRun | None: ...

    async def set_command_id(self, run_id: str, command_id: str) -> ResearchRun: ...


class ResearchWorkflow:
    """Run checkpointed research stages without duplicating accepted sources."""

    def __init__(
        self,
        repository: ResearchRunStore | None = None,
        handlers: Mapping[ResearchStage, ResearchStageHandler] | None = None,
        *,
        command_submitter: Callable[..., object] = submit_command,
        command_status_getter: Callable[
            [str], Awaitable[object | None]
        ] = get_command_status,
    ) -> None:
        self.repository = repository or ResearchRunRepository()
        self.handlers = dict(handlers or {})
        self._command_submitter = command_submitter
        self._command_status_getter = command_status_getter

    async def submit(self, run_id: str) -> ResearchRun:
        """Submit the registered background command only after persistence exists."""
        run = await self._require_run(run_id)
        if run.cancelled or run.stage == "complete":
            return run
        command_id = await asyncio.to_thread(
            self._command_submitter,
            "open_notebook",
            "run_research",
            {"research_run_id": run_id},
        )
        if not command_id:
            raise RuntimeError("Research command submission did not return an id")
        return await self.repository.set_command_id(run_id, str(command_id))

    async def resume(self, run_id: str) -> ResearchRun:
        """Advance until approval, cancellation, completion, or a missing handler."""
        run = await self._require_run(run_id)
        while True:
            run = await self._refresh_cancellation(run)
            if run.cancelled or run.stage == "complete":
                return run

            if run.stage == "await_source_approval":
                if run.pending_candidate_ids():
                    return run
                run = await self.repository.save_stage_result(
                    run,
                    "await_source_approval",
                    ResearchStageResult(
                        checkpoint={
                            "approved_candidate_ids": sorted(
                                run.approved_candidate_ids()
                            )
                        },
                        approval_decisions=run.approval_decisions,
                    ),
                )
                continue

            handler = self.handlers.get(run.stage)
            if handler is None:
                # A future feature can install a new handler without changing
                # existing checkpoints. Treat absent work as a clean pause.
                return run
            stage = run.stage
            result = await handler(run)
            if stage == "validate":
                # Completion is only reachable with a deterministic receipt
                # produced after every compared claim passed citation checks.
                from deeper_notebook.research.comparison import (
                    require_strict_comparison,
                )

                require_strict_comparison(result.checkpoint)
            run = await self.repository.save_stage_result(run, stage, result)

    async def _refresh_cancellation(self, run: ResearchRun) -> ResearchRun:
        if run.cancelled or not run.command_id:
            return run
        try:
            status = await self._command_status_getter(run.command_id)
        except Exception as exc:
            # Status lookup is advisory. The durable run flag remains the
            # source of truth, so a transient command-store error must not
            # turn a resumable research run into a failed one.
            logger.warning("Unable to read research command status: {}", exc)
            return run
        state = str(getattr(status, "status", "")).lower()
        if state not in {"canceled", "cancelled"}:
            return run
        cancelled = await self.repository.request_cancellation(run.id or "")
        return cancelled or run

    async def _require_run(self, run_id: str) -> ResearchRun:
        run = await self.repository.get(run_id)
        if run is None:
            raise ValueError("Research run not found")
        return run
