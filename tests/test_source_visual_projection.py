from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.source_visuals.contracts import SourceVisualRecord

UTC = timezone.utc
NOW = datetime(2026, 8, 15, 12, tzinfo=UTC)
SOURCE_SHA = "a" * 64
ASSET_SHA = "b" * 64
FILE_SHA = "c" * 64


def _record(
    source_id: str = "source:one",
    *,
    updated: datetime = NOW,
    source_file_sha256: str | None = FILE_SHA,
) -> SourceVisualRecord:
    return SourceVisualRecord(
        source_id=source_id,
        source_updated_at=updated,
        source_file_sha256=source_file_sha256,
        content_sha256=SOURCE_SHA,
        asset_sha256=ASSET_SHA,
        asset_relpath="aa/" + SOURCE_SHA + "/" + ASSET_SHA + ".webp",
        origin="embedded",
        source_locator={"page": 1},
        extractor_version="source-visual-v1",
        alt_text="Embedded image from Source one",
        width=640,
        height=360,
        mime_type="image/webp",
        created_at=NOW,
        updated_at=NOW,
    )


class _CurrentRows(dict[str, SourceVisualRecord]):
    def __init__(self, *args, statuses=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.statuses = statuses or {}


class _Repository:
    def __init__(self, current: dict[str, SourceVisualRecord], statuses=None):
        self.current = _CurrentRows(current, statuses=statuses)
        self.calls: list[dict[str, datetime]] = []

    async def list_current(self, revisions: dict[str, datetime]):
        self.calls.append(dict(revisions))
        return self.current


class _CaptureRepository:
    def __init__(self, records: list[SourceVisualRecord]):
        self.records = records
        self.calls: list[tuple[str, ...]] = []

    async def list_current_by_source_file_sha256(self, values: tuple[str, ...]):
        self.calls.append(values)
        return self.records


def _source_row(source_id: str = "source:one", *, updated: datetime = NOW) -> dict[str, object]:
    return {
        "id": source_id,
        "updated": updated,
        "title": "Source one",
        "full_text": "this must never reach visual projection",
        "asset": {"file_path": "/private/source.pdf", "url": None},
    }


@pytest.mark.asyncio
async def test_projects_thirty_rows_through_one_bounded_batch_without_private_fields():
    from api.source_visual_projection import project_source_visuals

    rows = [_source_row(f"source:{index}") for index in range(30)]
    records = {
        f"source:{index}": _record(f"source:{index}")
        for index in range(30)
    }
    repository = _Repository(records)

    projected = await project_source_visuals(rows, repository=repository)

    assert len(repository.calls) == 1
    assert set(repository.calls[0]) == {f"source:{index}" for index in range(30)}
    receipt = projected["source:0"].visual.model_dump(mode="json")
    assert receipt["asset_url"].startswith("/api/sources/source%3A0/visual?v=")
    assert receipt["asset_url"] != "/private/source.pdf"
    assert "asset_relpath" not in receipt
    assert "source_file_sha256" not in receipt
    assert "full_text" not in receipt
    assert projected["source:0"].visual_status is None


@pytest.mark.asyncio
async def test_projection_bounds_to_two_hundred_and_omits_stale_or_malformed_rows():
    from api.source_visual_projection import project_source_visuals

    rows = [_source_row(f"source:{index}") for index in range(201)]
    stale = _record("source:stale", updated=NOW.replace(hour=13))
    malformed = SimpleNamespace(source_id="source:malformed")
    repository = _Repository(
        {
            "source:0": _record("source:0"),
            "source:stale": stale,
            "source:malformed": malformed,  # type: ignore[dict-item]
        }
    )

    projected = await project_source_visuals(rows, repository=repository)

    assert len(repository.calls) == 1
    assert len(repository.calls[0]) == 200
    assert projected["source:0"].visual is not None
    assert "source:stale" not in projected
    assert "source:malformed" not in projected
    assert "source:200" not in projected


@pytest.mark.asyncio
async def test_projection_keeps_detail_list_and_source_bearing_search_receipts_in_parity():
    from api.source_visual_projection import (
        project_search_source_visuals,
        project_source_visuals,
    )

    record = _record()
    detail = await project_source_visuals([_source_row()], repository=_Repository({"source:one": record}))
    listed = await project_source_visuals([_source_row()], repository=_Repository({"source:one": record}))
    results = [
        {"id": "source:one", "title": "Source one"},
        {"id": "note:one", "title": "Note one"},
        {"id": "note:child", "parent_id": "source:one", "title": "Note child"},
    ]
    searched = await project_search_source_visuals(
        results,
        source_rows=[_source_row()],
        repository=_Repository({"source:one": record}),
    )

    assert detail["source:one"].visual == listed["source:one"].visual
    assert searched[0]["visual"] == detail["source:one"].visual.model_dump(mode="json")
    assert searched[0]["visual_status"] is None
    assert "visual" not in searched[1]
    assert "visual_status" not in searched[1]
    assert "visual" not in searched[2]
    assert "visual_status" not in searched[2]


@pytest.mark.asyncio
async def test_search_projection_recognizes_direct_and_parent_source_ids_without_private_leakage(monkeypatch):
    """Production search rows omit revisions and source insights point at parent_id."""

    from api.models import SearchRequest
    from api.routers import search

    results = [
        {"id": "source:one", "title": "Source one", "full_text": "do not project this"},
        {"id": "source_insight:one", "parent_id": "source:two", "title": "Insight"},
        {"id": "note:one", "parent_id": "source:three", "title": "Note"},
    ]
    source_rows = [
        {"id": "source:one", "updated": NOW},
        {"id": "source:two", "updated": NOW},
    ]
    query = AsyncMock(return_value=source_rows)

    async def project(values, *, source_rows):
        assert len(values) == 3
        assert source_rows == [
            {"id": "source:one", "updated": NOW},
            {"id": "source:two", "updated": NOW},
        ]
        copied = [dict(value) for value in values]
        copied[0]["visual"] = {"asset_url": "/api/sources/source%3Aone/visual?v=opaque"}
        copied[1]["visual"] = {"asset_url": "/api/sources/source%3Atwo/visual?v=opaque"}
        return copied

    monkeypatch.setattr(search, "source_visuals_enabled", lambda: True)
    monkeypatch.setattr(search, "text_search", AsyncMock(return_value=results))
    monkeypatch.setattr(search, "repo_query", query)
    projector = AsyncMock(side_effect=project)
    monkeypatch.setattr(search, "project_search_source_visuals", projector)

    response = await search.search_knowledge_base(SearchRequest(query="needle", limit=3))

    assert response.results[0]["visual"]["asset_url"].endswith("opaque")
    assert response.results[1]["visual"]["asset_url"].endswith("opaque")
    assert "visual" not in response.results[2]
    assert query.await_count == 1
    assert projector.await_count == 1
    query_text, variables = query.await_args.args
    assert "SELECT id, updated FROM source" in query_text
    assert "LIMIT $limit" in query_text
    assert variables["limit"] == 200
    assert {str(value) for value in variables["source_ids"]} == {"source:one", "source:two"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"state": "queued", "command_id": "command:one", "updated_at": NOW}, "queued"),
        ({"state": "processing", "command_id": "command:one", "updated_at": NOW}, "processing"),
        ({"state": "unavailable", "updated_at": NOW}, "unavailable"),
        ({"state": "failed", "error_code": "decode_failed", "updated_at": NOW}, "failed"),
    ],
)
async def test_projection_exposes_only_safe_nonready_statuses(status, expected):
    from api.source_visual_projection import project_source_visuals

    repository = _Repository({}, statuses={"source:one": {**status, "worker_error": "/private/secret"}})
    projected = await project_source_visuals([_source_row()], repository=repository)

    response = projected["source:one"].visual_status.model_dump(mode="json")
    assert response["state"] == expected
    assert "worker_error" not in response
    assert "/private" not in str(response)
    assert projected["source:one"].visual is None


@pytest.mark.asyncio
async def test_ready_projection_clears_nonready_status_even_when_a_status_hint_exists():
    from api.source_visual_projection import project_source_visuals

    projected = await project_source_visuals(
        [_source_row()],
        repository=_Repository(
            {"source:one": _record()},
            statuses={"source:one": {"state": "failed", "error_code": "decode_failed", "updated_at": NOW}},
        ),
    )

    assert projected["source:one"].visual is not None
    assert projected["source:one"].visual_status is None


@pytest.mark.asyncio
async def test_repository_uses_only_the_latest_current_visual_status_hint(monkeypatch):
    from deeper_notebook.source_visuals.repository import SourceVisualRepository

    newer = NOW.replace(hour=13)
    monkeypatch.setattr(
        "deeper_notebook.source_visuals.repository.repo_query",
        AsyncMock(
            return_value=[
                {
                    "ready": [],
                    "statuses": [
                        {
                            "source_id": "source:one",
                            "source_updated_at": NOW,
                            "outcome": "queued",
                            "command_id": "command:new",
                            "command_status": "running",
                            "updated_at": newer,
                        },
                        {
                            "source_id": "source:one",
                            "source_updated_at": NOW,
                            "outcome": "queued",
                            "command_id": "command:old",
                            "command_status": "queued",
                            "updated_at": NOW,
                        },
                    ],
                }
            ]
        ),
    )

    current = await SourceVisualRepository().list_current({"source:one": NOW})

    assert current.statuses["source:one"]["state"] == "processing"
    assert current.statuses["source:one"]["command_id"] == "command:new"


@pytest.mark.asyncio
async def test_capture_links_only_exact_full_file_sha_to_current_visual_in_one_bounded_batch():
    from api.source_visual_projection import project_capture_linked_sources

    items = [
        {"id": "capture:one", "sha256": FILE_SHA, "filename": "same.pdf"},
        {"id": "capture:two", "sha256": "d" * 64, "filename": "different.pdf"},
        {"id": "capture:bad", "sha256": "not-a-hash", "filename": "bad.pdf"},
    ]
    repository = _CaptureRepository([_record()])

    projected = await project_capture_linked_sources(items, repository=repository)

    assert repository.calls == [(FILE_SHA, "d" * 64)]
    assert projected[0]["linked_source"]["id"] == "source:one"
    assert "source_file_sha256" not in projected[0]["linked_source"]
    assert "asset_relpath" not in projected[0]["linked_source"]
    assert "linked_source" not in projected[1]
    assert "linked_source" not in projected[2]
    assert items[0].get("linked_source") is None
