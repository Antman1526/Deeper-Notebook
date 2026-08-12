"""Task 14 repository adapter over native Study and Task 10 receipts.

``StudyAssistantRepository`` remains the only writer for ``study_progress``.
This adapter owns bounded aggregation and a read-only projection of native
reviews; it never updates cards or invokes the FSRS scheduler.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from surrealdb import RecordID  # type: ignore[import-untyped]

from deeper_notebook.database.repository import ensure_record_id, repo_query

from .assistant_repository import (
    StudyAssistantRepository,
    StudyAssistantRepositoryError,
    StudyAssistantUnavailableError,
)
from .contracts import StudyReview
from .progress import (
    MAX_PROJECTION_RECEIPTS,
    StudyMasteryProjection,
    StudyProgressReceipt,
    project_mastery,
)

MAX_PROGRESS_PAGE = 50
MAX_PAGE_OFFSET = 100_000

ReviewLoader = Callable[[str, int, int], Awaitable[tuple[StudyReview, ...]]]


class StudyProgressRepositoryError(RuntimeError):
    """Safe persistence failure suitable for a Study API boundary."""


def _page(value: int, offset: int) -> tuple[int, int]:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StudyProgressRepositoryError("invalid progress page")
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise StudyProgressRepositoryError("invalid progress offset")
    if value < 1 or offset < 0 or offset > MAX_PAGE_OFFSET:
        raise StudyProgressRepositoryError("invalid progress page")
    return min(value, MAX_PROGRESS_PAGE), offset


def _safe_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("invalid review timestamp")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("review timestamp must be timezone-aware")
    return result


def _record_text(value: object) -> str:
    return str(value) if isinstance(value, RecordID) else str(value)


def _review_from_row(row: object) -> StudyReview:
    if not isinstance(row, dict):
        raise StudyProgressRepositoryError("invalid persisted Study review")
    values: dict[str, Any] = {
        "id": _record_text(row["id"]) if row.get("id") is not None else None,
        "card_id": _record_text(row.get("card_id", "")),
        "card_version": row.get("card_version"),
        "request_id": row.get("request_id"),
        "rating": row.get("rating"),
        "reviewed_at": _safe_datetime(row.get("reviewed_at")),
        "fsrs_state_before": row.get("fsrs_state_before"),
        "fsrs_state_after": row.get("fsrs_state_after"),
        "lapse_count_after": row.get("lapse_count_after"),
        "created": row.get("created"),
    }
    try:
        return StudyReview.model_validate(
            {key: value for key, value in values.items() if value is not None}
        )
    except Exception as exc:
        raise StudyProgressRepositoryError("invalid persisted Study review") from exc


class StudyProgressRepository:
    """Read/write adapter preserving Task 10's append-only authority."""

    def __init__(
        self,
        *,
        assistant: StudyAssistantRepository | None = None,
        review_loader: ReviewLoader | None = None,
    ) -> None:
        self.assistant = assistant or StudyAssistantRepository()
        self._review_loader = review_loader

    async def append_progress(
        self, receipt: StudyProgressReceipt
    ) -> StudyProgressReceipt:
        try:
            return await self.assistant.append_progress(receipt)
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            raise StudyProgressRepositoryError("Study progress is unavailable") from exc

    async def append(self, receipt: StudyProgressReceipt) -> StudyProgressReceipt:
        return await self.append_progress(receipt)

    async def list_progress(
        self,
        plan_id: str,
        *,
        limit: int = MAX_PROGRESS_PAGE,
        offset: int = 0,
    ) -> tuple[StudyProgressReceipt, ...]:
        page_limit, page_offset = _page(limit, offset)
        try:
            return await self.assistant.list_progress(
                plan_id,
                limit=page_limit,
                offset=page_offset,
            )
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            raise StudyProgressRepositoryError("Study progress is unavailable") from exc

    async def get_progress_by_request(
        self,
        plan_id: str,
        request_id: str,
    ) -> StudyProgressReceipt | None:
        try:
            return await self.assistant.get_progress_by_request(plan_id, request_id)
        except StudyAssistantRepositoryError:
            raise
        except Exception as exc:
            raise StudyProgressRepositoryError("Study progress is unavailable") from exc

    async def list_reviews(
        self,
        plan_id: str,
        *,
        limit: int = MAX_PROGRESS_PAGE,
        offset: int = 0,
    ) -> tuple[StudyReview, ...]:
        page_limit, page_offset = _page(limit, offset)
        if self._review_loader is not None:
            try:
                return tuple(
                    (await self._review_loader(plan_id, page_limit, page_offset))[
                        :MAX_PROJECTION_RECEIPTS
                    ]
                )
            except StudyProgressRepositoryError:
                raise
            except Exception as exc:
                raise StudyProgressRepositoryError(
                    "Study reviews are unavailable"
                ) from exc
        try:
            # The plan-card link stores public card-id text while native
            # ``study_review.card_id`` is a record<study_card>. Resolve the
            # links first, then bind those RecordIDs; this keeps the query
            # native, parameterized, and compatible with Surreal's typed
            # record comparison. No FSRS state is copied or rewritten.
            link_rows = await repo_query(
                "SELECT card_id FROM study_plan_card WHERE plan_id = $plan_id "
                "ORDER BY card_id LIMIT $limit START $offset;",
                {"plan_id": plan_id, "limit": page_limit, "offset": page_offset},
            )
            if not isinstance(link_rows, (list, tuple)) or not link_rows:
                return ()
            card_ids: list[RecordID] = []
            for link in link_rows:
                if not isinstance(link, dict) or not isinstance(link.get("card_id"), str):
                    raise StudyProgressRepositoryError("invalid linked Study card")
                card_id = ensure_record_id(link["card_id"])
                if str(card_id).split(":", 1)[0] != "study_card":
                    raise StudyProgressRepositoryError("invalid linked Study card")
                card_ids.append(card_id)
            rows = await repo_query(
                "SELECT id, card_id, card_version, request_id, rating, reviewed_at, "
                "fsrs_state_before, fsrs_state_after, lapse_count_after, created "
                "FROM study_review WHERE card_id IN $card_ids "
                "ORDER BY reviewed_at DESC LIMIT $limit;",
                {"card_ids": card_ids, "limit": page_limit},
            )
            if not isinstance(rows, (list, tuple)):
                return ()
            return tuple(_review_from_row(row) for row in rows[:page_limit])
        except StudyProgressRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to load native Study reviews for progress")
            raise StudyProgressRepositoryError("Study reviews are unavailable") from exc

    async def project(
        self,
        plan_id: str,
        *,
        now: datetime,
        limit: int = MAX_PROGRESS_PAGE,
    ) -> StudyMasteryProjection:
        if now.tzinfo is None or now.utcoffset() is None:
            raise StudyProgressRepositoryError(
                "progress projection requires an aware timestamp"
            )
        try:
            receipts, reviews = await self._load_inputs(plan_id, limit=limit)
            return project_mastery(receipts, reviews, now=now)
        except StudyProgressRepositoryError:
            raise
        except StudyAssistantRepositoryError as exc:
            raise StudyProgressRepositoryError("Study progress is unavailable") from exc
        except Exception as exc:
            logger.exception("Failed to project Study mastery")
            raise StudyProgressRepositoryError("Study progress is unavailable") from exc

    async def get_projection(
        self,
        plan_id: str,
        *,
        now: datetime,
        limit: int = MAX_PROGRESS_PAGE,
    ) -> StudyMasteryProjection:
        return await self.project(plan_id, now=now, limit=limit)

    async def _load_inputs(
        self,
        plan_id: str,
        *,
        limit: int,
    ) -> tuple[tuple[StudyProgressReceipt, ...], tuple[StudyReview, ...]]:
        page_limit, _offset = _page(limit, 0)
        # Keep each query bounded to one page; no unbounded materialization.
        receipts, reviews = await __import__("asyncio").gather(
            self.list_progress(plan_id, limit=page_limit),
            self.list_reviews(plan_id, limit=page_limit),
        )
        return receipts, reviews


__all__ = [
    "MAX_PROGRESS_PAGE",
    "StudyProgressRepository",
    "StudyProgressRepositoryError",
]
