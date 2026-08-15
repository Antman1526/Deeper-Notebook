from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.source_visuals.repository import (
    SourceVisualConflictError,
    SourceVisualRepository,
    SourceVisualRepositoryError,
    operation_identity,
)

UTC = timezone.utc
SOURCE_UPDATED = datetime(2026, 8, 14, 12, tzinfo=UTC)
OWNER_A = "a" * 64
OWNER_B = "b" * 64
READY_ROW = {
    "schema_version": 1,
    "id": "source_visual:one",
    "source_id": "source:one",
    "source_updated_at": SOURCE_UPDATED,
    "source_file_sha256": None,
    "content_sha256": "a" * 64,
    "asset_sha256": "b" * 64,
    "asset_relpath": "aa/" + "a" * 64 + "/" + "b" * 64 + ".webp",
    "origin": "embedded",
    "source_locator": {"page": 1},
    "extractor_version": "source-visual-v1",
    "alt_text": "Source one visual",
    "width": 640,
    "height": 360,
    "mime_type": "image/webp",
    "created_at": SOURCE_UPDATED,
    "updated_at": SOURCE_UPDATED,
}


def _repository() -> SourceVisualRepository:
    return SourceVisualRepository()


@pytest.mark.asyncio
async def test_list_current_uses_source_revision_without_hashing(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(return_value=[READY_ROW])
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    result = await repository.list_current({"source:one": SOURCE_UPDATED})
    assert result["source:one"].source_updated_at == SOURCE_UPDATED
    assert query.await_count == 1


@pytest.mark.asyncio
async def test_list_current_omits_malformed_and_stale_rows(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(
        return_value=[
            READY_ROW,
            {**READY_ROW, "source_id": "source:bad", "asset_relpath": ""},
            {**READY_ROW, "source_id": "source:stale", "source_updated_at": SOURCE_UPDATED - timedelta(days=1)},
        ]
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    result = await repository.list_current(
        {"source:one": SOURCE_UPDATED, "source:stale": SOURCE_UPDATED}
    )
    assert list(result) == ["source:one"]


@pytest.mark.asyncio
async def test_claim_lease_supports_first_acquire_renewal_and_expired_takeover(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(side_effect=[None, {"owner_token": OWNER_A, "lease_until": SOURCE_UPDATED}])
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    first = await repository.acquire_claim(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        now=SOURCE_UPDATED,
        lease_until=SOURCE_UPDATED + timedelta(minutes=5),
    )
    assert first.owner_token == OWNER_A
    renewed = await repository.renew_claim(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        now=SOURCE_UPDATED,
        lease_until=SOURCE_UPDATED + timedelta(minutes=10),
    )
    assert renewed.owner_token == OWNER_A
    assert query.await_count == 2


@pytest.mark.asyncio
async def test_live_owner_contention_and_old_owner_fencing(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(return_value={"owner_token": OWNER_A, "lease_until": SOURCE_UPDATED + timedelta(minutes=5)})
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    with pytest.raises(SourceVisualConflictError) as error:
        await repository.acquire_claim(
            source_id="source:one",
            content_sha256="a" * 64,
            extractor_version="source-visual-v1",
            owner_token=OWNER_B,
            now=SOURCE_UPDATED,
            lease_until=SOURCE_UPDATED + timedelta(minutes=5),
        )
    assert error.value.code == "CLAIM_HELD"
    with pytest.raises(SourceVisualConflictError):
        await repository.renew_claim(
            source_id="source:one",
            content_sha256="a" * 64,
            extractor_version="source-visual-v1",
            owner_token=OWNER_B,
            now=SOURCE_UPDATED,
            lease_until=SOURCE_UPDATED + timedelta(minutes=5),
        )


@pytest.mark.asyncio
async def test_expired_claim_is_taken_over_by_the_new_owner(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(
        return_value={
            "owner_token": OWNER_A,
            "lease_until": SOURCE_UPDATED - timedelta(minutes=1),
        }
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    claim = await repository.acquire_claim(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_B,
        now=SOURCE_UPDATED,
        lease_until=SOURCE_UPDATED + timedelta(minutes=5),
    )
    assert claim.owner_token == OWNER_B
    assert claim.lease_until == SOURCE_UPDATED + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_command_binding_is_compare_and_set(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(return_value={"command_id": None, "owner_token": OWNER_A})
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    bound = await repository.bind_command(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        command_id="command:one",
    )
    assert bound.command_id == "command:one"
    query.return_value = {"command_id": "command:other", "owner_token": OWNER_A}
    with pytest.raises(SourceVisualConflictError):
        await repository.bind_command(
            source_id="source:one",
            content_sha256="a" * 64,
            extractor_version="source-visual-v1",
            owner_token=OWNER_A,
            command_id="command:one",
        )


@pytest.mark.asyncio
async def test_operation_replay_requires_an_exact_payload(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    payload = {
        "source_id": "source:one",
        "request_id": "request:one",
        "source_updated_at": SOURCE_UPDATED,
        "content_sha256": "a" * 64,
        "operation": "delete",
        "outcome": "deleted",
        "command_id": None,
        "error_code": None,
    }
    operation_id = operation_identity("source:one", "request:one", "delete")
    query = AsyncMock(side_effect=[None, {"id": operation_id, **payload}])
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    first = await repository.record_operation(**payload)
    replay = await repository.record_operation(**payload)
    assert first == replay
    query.side_effect = None
    query.return_value = {"id": operation_id, **payload, "result": {"ok": False}}
    with pytest.raises(SourceVisualConflictError) as error:
        await repository.record_operation(**payload)
    assert error.value.code == "REQUEST_CONFLICT"


@pytest.mark.asyncio
async def test_publish_and_delete_require_owner_and_current_source(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(return_value={"owner_token": OWNER_A, "source_updated_at": SOURCE_UPDATED})
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    published = await repository.publish_ready(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        source_updated_at=SOURCE_UPDATED,
    )
    deleted = await repository.delete_ready(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        source_updated_at=SOURCE_UPDATED,
    )
    assert published.source_id == deleted.source_id == "source:one"


@pytest.mark.asyncio
async def test_complete_and_release_reject_wrong_owner(monkeypatch: pytest.MonkeyPatch):
    repository = _repository()
    query = AsyncMock(return_value={"owner_token": OWNER_A})
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    for method in (repository.complete_claim, repository.release_claim):
        with pytest.raises(SourceVisualConflictError):
            await method(
                source_id="source:one",
                content_sha256="a" * 64,
                extractor_version="source-visual-v1",
                owner_token=OWNER_B,
            )


def test_repository_error_codes_are_bounded_and_do_not_expose_payload():
    assert issubclass(SourceVisualRepositoryError, Exception)
    assert issubclass(SourceVisualConflictError, SourceVisualRepositoryError)
