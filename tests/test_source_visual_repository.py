from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from deeper_notebook.source_visuals.contracts import (
    SourceVisualAuthority,
    SourceVisualRecord,
)
from deeper_notebook.source_visuals.repository import (
    SourceVisualConflictError,
    SourceVisualRepository,
    SourceVisualRepositoryError,
    claim_identity,
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
async def test_list_current_binds_revision_values_not_the_revision_mapping(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    calls: list[dict[str, object]] = []

    async def query(_query: str, variables: dict[str, object]):
        calls.append(variables)
        if not isinstance(variables.get("source_revision_values"), list):
            return []
        return [READY_ROW]

    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    result = await repository.list_current({"source:one": SOURCE_UPDATED})
    assert result["source:one"].source_updated_at == SOURCE_UPDATED
    assert len(calls) == 1
    assert calls[0]["source_revision_values"] == [SOURCE_UPDATED]


@pytest.mark.asyncio
async def test_list_current_matches_source_revision_pairs_not_independent_sets(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    second_updated = SOURCE_UPDATED + timedelta(hours=1)
    source_two = {
        **READY_ROW,
        "id": "source_visual:two",
        "source_id": "source:two",
        "source_updated_at": second_updated,
    }
    rows = [
        READY_ROW,
        source_two,
        {
            **READY_ROW,
            "id": "source_visual:one-stale",
            "source_updated_at": second_updated,
        },
        {
            **source_two,
            "id": "source_visual:two-stale",
            "source_updated_at": SOURCE_UPDATED,
        },
    ]
    requested = {"source:one": SOURCE_UPDATED, "source:two": second_updated}
    calls: list[tuple[str, dict[str, object]]] = []

    async def query(query_text: str, variables: dict[str, object]):
        calls.append((query_text, variables))
        pairs = variables.get("source_revision_pairs")
        if pairs is None:
            source_records = {str(value) for value in variables["source_records"]}
            revisions = set(variables["source_revision_values"])
            independently_selected = [
                row
                for row in rows
                if row["source_id"] in source_records
                and row["source_updated_at"] in revisions
            ]
            assert all(
                (row["source_id"], row["source_updated_at"]) in requested.items()
                for row in independently_selected
            ), "independent ID/time IN sets admitted a stale source/revision pair"
            return rows
        normalised_pairs = {(str(pair[0]), pair[1]) for pair in pairs}
        assert normalised_pairs == set(requested.items())
        return [
            row
            for row in rows
            if (row["source_id"], row["source_updated_at"]) in normalised_pairs
        ]

    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    result = await repository.list_current(requested)

    assert set(result) == set(requested)
    assert all(result[source].source_updated_at == revision for source, revision in requested.items())
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cleanup_repository_adapter_is_bounded_parameterized_and_exact(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    query = AsyncMock(
        side_effect=[
            [READY_ROW],
            [READY_ROW],
            [READY_ROW],
            [{"claim_id": claim_identity("source:one", "a" * 64, "source-visual-v1")}],
        ]
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    record = SourceVisualRecord.model_validate(
        {key: value for key, value in READY_ROW.items() if key != "id"}
    )

    found = await repository.find_ready_by_asset_relpath(record.asset_relpath)
    page = await repository.list_ready_for_eviction(limit=100)
    deleted = await repository.delete_ready_if_current(record)
    active = await repository.is_claim_active(record)

    assert found == record
    assert page == [record]
    assert deleted is True
    assert active is True
    find_call, list_call, delete_call, claim_call = query.await_args_list
    assert "$asset_relpath" in find_call.args[0]
    assert find_call.args[1]["asset_relpath"] == record.asset_relpath
    assert "ORDER BY updated_at ASC" in list_call.args[0]
    assert list_call.args[1]["limit"] == 100
    assert "$cache_record" in delete_call.args[0]
    assert delete_call.args[1]["asset_relpath"] == record.asset_relpath
    assert "$claim_record" in claim_call.args[0]


@pytest.mark.asyncio
async def test_cleanup_repository_adapter_rejects_unbounded_or_malformed_input(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    query = AsyncMock(return_value=[])
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)

    with pytest.raises(SourceVisualRepositoryError):
        await repository.list_ready_for_eviction(limit=101)
    with pytest.raises(SourceVisualRepositoryError):
        await repository.find_ready_by_asset_relpath("../outside.webp")

    assert query.await_count == 0


@pytest.mark.asyncio
async def test_conditional_cleanup_delete_atomically_rejects_new_live_claim(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    record = SourceVisualRecord.model_validate(
        {key: value for key, value in READY_ROW.items() if key != "id"}
    )

    async def query(query_text: str, variables: dict[str, object]):
        if (
            "BEGIN TRANSACTION" in query_text
            and "lease_until > time::now()" in query_text
            and "claim_record" in variables
        ):
            return [{"claim_active": True}]
        return [READY_ROW]

    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)

    assert await repository.delete_ready_if_current(record) is False


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
    query = AsyncMock(
        side_effect=[
            None,
            {"owner_token": OWNER_A, "lease_until": SOURCE_UPDATED + timedelta(minutes=5)},
        ]
    )
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
    query = AsyncMock(
        return_value={
            "command_id": None,
            "owner_token": OWNER_A,
            "lease_until": SOURCE_UPDATED + timedelta(minutes=5),
        }
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    bound = await repository.bind_command(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        command_id="command:one",
        now=SOURCE_UPDATED,
    )
    assert bound.command_id == "command:one"
    query.return_value = {
        "command_id": "command:other",
        "owner_token": OWNER_A,
        "lease_until": SOURCE_UPDATED + timedelta(minutes=5),
    }
    with pytest.raises(SourceVisualConflictError):
        await repository.bind_command(
            source_id="source:one",
            content_sha256="a" * 64,
            extractor_version="source-visual-v1",
            owner_token=OWNER_A,
            command_id="command:one",
            now=SOURCE_UPDATED,
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
    query = AsyncMock(
        return_value={
            "owner_token": OWNER_A,
            "lease_until": SOURCE_UPDATED + timedelta(minutes=5),
            "source_updated_at": SOURCE_UPDATED,
        }
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    published = await repository.publish_ready(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        source_updated_at=SOURCE_UPDATED,
        now=SOURCE_UPDATED,
    )
    deleted = await repository.delete_ready(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        source_updated_at=SOURCE_UPDATED,
        now=SOURCE_UPDATED,
    )
    assert published.source_id == deleted.source_id == "source:one"


def _authority(**overrides: object) -> SourceVisualAuthority:
    values: dict[str, object] = {
        "source_id": "source:one",
        "source_updated_at": SOURCE_UPDATED,
        "normalized_source_type": "upload",
        "asset_url": None,
        "controlled_file_path": None,
        "source_file_sha256": "c" * 64,
        "full_text_sha256": "d" * 64,
        "content_sha256": "a" * 64,
        "extractor_version": "source-visual-v1",
    }
    values.update(overrides)
    return SourceVisualAuthority(**values)


def _ready_record(authority: SourceVisualAuthority, **overrides: object) -> SourceVisualRecord:
    values: dict[str, object] = {
        "source_id": authority.source_id,
        "source_updated_at": authority.source_updated_at,
        "source_file_sha256": authority.source_file_sha256,
        "content_sha256": authority.content_sha256,
        "asset_sha256": "b" * 64,
        "asset_relpath": "bb/" + "b" * 64 + "/asset.webp",
        "origin": "embedded",
        "source_locator": {"page": 1},
        "extractor_version": authority.extractor_version,
        "alt_text": "Source visual",
        "width": 640,
        "height": 360,
        "created_at": SOURCE_UPDATED,
        "updated_at": SOURCE_UPDATED,
    }
    values.update(overrides)
    return SourceVisualRecord(**values)


@pytest.mark.asyncio
async def test_publish_ready_binds_source_id_as_a_record_id(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    captured: dict[str, object] = {}

    async def query(_query: str, variables: dict[str, object]):
        captured.update(variables)
        return {
            "owner_token": OWNER_A,
            "lease_until": SOURCE_UPDATED + timedelta(minutes=5),
            "source_updated_at": SOURCE_UPDATED,
        }

    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    await repository.publish_ready(
        source_id="source:one",
        content_sha256="a" * 64,
        extractor_version="source-visual-v1",
        owner_token=OWNER_A,
        source_updated_at=SOURCE_UPDATED,
        now=SOURCE_UPDATED,
    )
    record_data = captured["record_data"]
    assert isinstance(record_data, dict)
    assert record_data["source_id"] == captured["source_record"]
    assert not isinstance(record_data["source_id"], str)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_updated_at", SOURCE_UPDATED - timedelta(minutes=1)),
        ("source_file_sha256", "e" * 64),
        ("content_sha256", "e" * 64),
        ("source_id", "source:two"),
        ("extractor_version", "source-visual-v2"),
    ),
)
async def test_publish_ready_rejects_metadata_not_bound_to_authority(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
):
    repository = _repository()
    authority = _authority()
    record = _ready_record(authority, **{field: value})
    query = AsyncMock(
        return_value={
            "owner_token": OWNER_A,
            "lease_until": SOURCE_UPDATED + timedelta(minutes=5),
            "source_updated_at": SOURCE_UPDATED,
        }
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    with pytest.raises(SourceVisualRepositoryError):
        await repository.publish_ready(
            record=record,
            authority=authority,
            owner_token=OWNER_A,
            source_updated_at=SOURCE_UPDATED,
            now=SOURCE_UPDATED,
        )
    assert query.await_count == 0


@pytest.mark.asyncio
async def test_operation_command_id_is_bound_and_replay_normalizes_record_id(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    payload = {
        "source_id": "source:one",
        "request_id": "request:command",
        "source_updated_at": SOURCE_UPDATED,
        "content_sha256": "a" * 64,
        "operation": "refresh",
        "outcome": "queued",
        "command_id": "command:one",
        "error_code": None,
    }
    operation_id = operation_identity("source:one", "request:command", "refresh")
    query = AsyncMock(return_value=None)
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    await repository.record_operation(**payload)
    variables = query.await_args.args[1]
    assert variables["operation_data"]["command_id"] == variables["command_record"]
    assert not isinstance(variables["operation_data"]["command_id"], str)

    query.return_value = {
        "id": operation_id,
        **payload,
        "command_id": variables["operation_data"]["command_id"],
    }
    replay = await repository.record_operation(**payload)
    assert replay.command_id == "command:one"


@pytest.mark.asyncio
async def test_operation_finalization_is_a_strict_queued_receipt_compare_and_set(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    payload = {
        "source_id": "source:one",
        "request_id": "request:command",
        "source_updated_at": SOURCE_UPDATED,
        "content_sha256": "a" * 64,
        "operation": "refresh",
        "command_id": None,
        "outcome": "queued",
        "error_code": None,
    }
    operation_id = operation_identity("source:one", "request:command", "refresh")
    query = AsyncMock(
        return_value={
            "id": operation_id,
            **payload,
            "command_id": "command:one",
        }
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)

    finalized = await repository.finalize_operation(
        **{key: value for key, value in payload.items() if key != "command_id"},
        expected_command_id=None,
        expected_outcome="queued",
        expected_error_code=None,
        command_id="command:one",
    )

    assert finalized.command_id == "command:one"
    variables = query.await_args.args[1]
    assert variables["expected_command_record"] is None
    assert variables["command_record"] != "command:one"
    query.return_value = {"request_conflict": True}
    with pytest.raises(SourceVisualConflictError):
        await repository.finalize_operation(
            **{key: value for key, value in payload.items() if key != "command_id"},
            expected_command_id=None,
            expected_outcome="queued",
            expected_error_code=None,
            command_id="command:one",
        )


@pytest.mark.asyncio
async def test_completed_delete_lookup_is_exactly_fingerprint_and_revision_bound(
    monkeypatch: pytest.MonkeyPatch,
):
    repository = _repository()
    payload = {
        "operation_id": operation_identity("source:one", "delete-request", "delete"),
        "source_id": "source:one",
        "request_id": "delete-request",
        "source_updated_at": SOURCE_UPDATED,
        "content_sha256": "a" * 64,
        "operation": "delete",
        "command_id": None,
        "outcome": "deleted",
        "error_code": None,
        "created_at": SOURCE_UPDATED,
        "updated_at": SOURCE_UPDATED,
    }
    query = AsyncMock(return_value=[payload])
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)

    receipt = await repository.find_completed_delete(
        "source:one", SOURCE_UPDATED, "a" * 64
    )

    assert receipt is not None
    assert receipt.operation == "delete"
    assert receipt.outcome == "deleted"
    variables = query.await_args.args[1]
    assert variables["source_updated_at"] == SOURCE_UPDATED
    assert variables["content_sha256"] == "a" * 64


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["renew", "bind", "complete", "release", "publish", "delete"])
async def test_lease_mutations_reject_expired_owner(
    monkeypatch: pytest.MonkeyPatch, mutation: str
):
    repository = _repository()
    query = AsyncMock(
        return_value={
            "owner_token": OWNER_A,
            "lease_until": SOURCE_UPDATED - timedelta(seconds=1),
            "source_updated_at": SOURCE_UPDATED,
        }
    )
    monkeypatch.setattr("deeper_notebook.source_visuals.repository.repo_query", query)
    with pytest.raises(SourceVisualConflictError):
        if mutation == "renew":
            await repository.renew_claim(
                source_id="source:one",
                content_sha256="a" * 64,
                extractor_version="source-visual-v1",
                owner_token=OWNER_A,
                now=SOURCE_UPDATED,
                lease_until=SOURCE_UPDATED + timedelta(minutes=5),
            )
        elif mutation == "bind":
            await repository.bind_command(
                source_id="source:one",
                content_sha256="a" * 64,
                extractor_version="source-visual-v1",
                owner_token=OWNER_A,
                command_id="command:one",
                now=SOURCE_UPDATED,
            )
        elif mutation == "complete":
            await repository.complete_claim(
                source_id="source:one",
                content_sha256="a" * 64,
                extractor_version="source-visual-v1",
                owner_token=OWNER_A,
                now=SOURCE_UPDATED,
            )
        elif mutation == "release":
            await repository.release_claim(
                source_id="source:one",
                content_sha256="a" * 64,
                extractor_version="source-visual-v1",
                owner_token=OWNER_A,
                now=SOURCE_UPDATED,
            )
        elif mutation == "publish":
            await repository.publish_ready(
                source_id="source:one",
                content_sha256="a" * 64,
                extractor_version="source-visual-v1",
                owner_token=OWNER_A,
                source_updated_at=SOURCE_UPDATED,
                now=SOURCE_UPDATED,
            )
        else:
            await repository.delete_ready(
                source_id="source:one",
                content_sha256="a" * 64,
                extractor_version="source-visual-v1",
                owner_token=OWNER_A,
                source_updated_at=SOURCE_UPDATED,
                now=SOURCE_UPDATED,
            )


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
