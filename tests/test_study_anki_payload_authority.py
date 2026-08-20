from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routers import study_anki
from deeper_notebook.study.anki_jobs import (
    AnkiClaimResult,
    AnkiJobMetadata,
    AnkiJobRepository,
)
from deeper_notebook.study.anki_package import AnkiImportOptions, inspect_anki_package
from deeper_notebook.study.anki_repository import (
    AnkiCompatibilityReceipt,
    _canonical_payload,
)
from tests.fixtures.anki.build_fixtures import build_apkg


def _receipt_for_options(
    package: Path, *, plan_id: str, request_id: str, options: AnkiImportOptions
) -> AnkiCompatibilityReceipt:
    inspection = inspect_anki_package(package)
    payload_sha256, _selected = _canonical_payload(plan_id, inspection, options)
    return AnkiCompatibilityReceipt(
        receipt_id="study_anki_import:" + "a" * 64,
        plan_id=plan_id,
        request_id=request_id,
        payload_sha256=payload_sha256,
        package_sha256=inspection.package_sha256,
        collection_sha256=inspection.collection_sha256,
        collection_member=inspection.collection_member,
        card_count=len(inspection.cards),
        transformed_count=inspection.transformed_count,
        skipped_count=inspection.skipped_count,
        card_ids=tuple(card.card_id for card in inspection.cards),
        deck_names=inspection.deck_names,
        tags=inspection.tags,
        media_names=inspection.media_names,
        created_at=datetime.now(UTC),
    )


def _metadata_for_options(
    package: Path,
    *,
    plan_id: str,
    job_id: str,
    request_id: str,
    options: AnkiImportOptions,
    status: str,
) -> AnkiJobMetadata:
    inspection = inspect_anki_package(package)
    options_sha256 = study_anki._options_sha256(options)
    payload_sha256, _selected = _canonical_payload(plan_id, inspection, options)
    now = datetime.now(UTC)
    # model_construct intentionally makes this RED test runnable against the
    # pre-repair model: the baseline silently drops the unknown authority
    # field, so the endpoint accepts a receipt for different options.
    return AnkiJobMetadata.model_construct(
        job_id=job_id,
        plan_id=plan_id,
        file_token="upload-" + "b" * 64 + ".apkg",
        package_sha256=inspection.package_sha256,
        collection_sha256=inspection.collection_sha256,
        collection_member=inspection.collection_member,
        card_count=len(inspection.cards),
        transformed_count=inspection.transformed_count,
        skipped_count=inspection.skipped_count,
        rejected_count=inspection.skipped_count,
        status=status,
        claim_request_id=request_id,
        claim_options_sha256=options_sha256,
        claim_package_sha256=inspection.package_sha256,
        claim_payload_sha256=payload_sha256,
        claim_owner_token="c" * 64,
        claim_expires_at=now + timedelta(minutes=5),
        receipt_id=None,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )


@pytest.mark.asyncio
async def test_crash_replay_rejects_same_package_request_with_different_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "same-package.apkg", kind="basic")
    plan_id = "study_plan:payload-crash"
    job_id = "anki_job:" + "b" * 64
    request_id = "same-request-different-options"
    original_options = AnkiImportOptions()
    current_options = AnkiImportOptions(deck_names=("Mechanics",))
    receipt = _receipt_for_options(
        package, plan_id=plan_id, request_id=request_id, options=original_options
    )
    metadata = _metadata_for_options(
        package,
        plan_id=plan_id,
        job_id=job_id,
        request_id=request_id,
        options=current_options,
        status="publishing",
    )
    inspection = inspect_anki_package(package)
    job = study_anki._ImportJob(
        job_id, plan_id, package, inspection, status="publishing", metadata=metadata
    )
    complete_calls: list[tuple[object, ...]] = []

    class FakeJobs:
        async def claim(self, *args: object, **kwargs: object) -> AnkiClaimResult:
            return AnkiClaimResult("replay")

        async def get(self, _job_id: str, _plan_id: str) -> AnkiJobMetadata:
            return metadata

        async def complete(self, *args: object, **kwargs: object) -> AnkiJobMetadata:
            complete_calls.append(args)
            return metadata.model_copy(
                update={"status": "published", "receipt_id": receipt.receipt_id}
            )

    class FakeReceipts:
        async def _find_by_request(
            self, _plan_id: str, _request_id: str
        ) -> AnkiCompatibilityReceipt:
            return receipt

    monkeypatch.setattr(study_anki, "_durable_metadata_enabled", lambda: True)
    monkeypatch.setattr(
        study_anki, "_load_job", lambda *_args, **_kwargs: _async_return(job)
    )
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiImportRepository", FakeReceipts)

    with pytest.raises(HTTPException) as exc_info:
        await study_anki.publish_anki_import(
            plan_id,
            job_id,
            study_anki.AnkiImportPublishRequest(
                upload_id=job_id,
                request_id=request_id,
                options=study_anki.AnkiHttpOptions(
                    schema_version=1, deck_names=("Mechanics",)
                ),
            ),
        )

    assert exc_info.value.status_code == 409
    assert complete_calls == []


@pytest.mark.asyncio
async def test_published_replay_rejects_same_package_request_with_different_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "published-same-package.apkg", kind="basic")
    plan_id = "study_plan:payload-published"
    job_id = "anki_job:" + "d" * 64
    request_id = "published-same-request-different-options"
    original_options = AnkiImportOptions()
    current_options = AnkiImportOptions(deck_names=("Mechanics",))
    receipt = _receipt_for_options(
        package, plan_id=plan_id, request_id=request_id, options=original_options
    )
    metadata = _metadata_for_options(
        package,
        plan_id=plan_id,
        job_id=job_id,
        request_id=request_id,
        options=current_options,
        status="published",
    ).model_copy(update={"receipt_id": receipt.receipt_id})
    inspection = inspect_anki_package(package)
    job = study_anki._ImportJob(
        job_id, plan_id, package, inspection, status="published", metadata=metadata
    )

    class FakeJobs:
        async def get(self, _job_id: str, _plan_id: str) -> AnkiJobMetadata:
            return metadata

    class FakeReceipts:
        async def find_by_receipt(
            self, _plan_id: str, _receipt_id: str
        ) -> AnkiCompatibilityReceipt:
            return receipt

    monkeypatch.setattr(study_anki, "_durable_metadata_enabled", lambda: True)
    monkeypatch.setattr(
        study_anki, "_load_job", lambda *_args, **_kwargs: _async_return(job)
    )
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiImportRepository", FakeReceipts)

    with pytest.raises(HTTPException) as exc_info:
        await study_anki.publish_anki_import(
            plan_id,
            job_id,
            study_anki.AnkiImportPublishRequest(
                upload_id=job_id,
                request_id=request_id,
                options=study_anki.AnkiHttpOptions(
                    schema_version=1, deck_names=("Mechanics",)
                ),
            ),
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_claim_query_binds_exact_payload_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_query(query: str, params: dict[str, object]):
        calls.append((query, params))
        return []

    monkeypatch.setattr("deeper_notebook.study.anki_jobs.repo_query", fake_query)
    payload_sha256 = "e" * 64
    result = await AnkiJobRepository().claim(
        "anki_job:" + "a" * 64,
        "study_plan:one",
        "b" * 64,
        "request-one",
        "c" * 64,
        payload_sha256,
    )
    assert result == "missing"
    assert calls
    query, params = calls[0]
    assert "claim_payload_sha256 = $payload_sha256" in query
    assert params["payload_sha256"] == payload_sha256


@pytest.mark.asyncio
async def test_terminal_queries_bind_exact_payload_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_query(query: str, params: dict[str, object]):
        calls.append((query, params))
        return []

    monkeypatch.setattr("deeper_notebook.study.anki_jobs.repo_query", fake_query)
    payload_sha256 = "e" * 64
    repository = AnkiJobRepository()
    assert (
        await repository.complete(
            "anki_job:" + "a" * 64,
            "study_plan:one",
            "request-one",
            "c" * 64,
            "study_anki_import:receipt",
            "d" * 64,
            package_sha256="b" * 64,
            payload_sha256=payload_sha256,
        )
        is None
    )
    assert (
        await repository.fail(
            "anki_job:" + "a" * 64,
            "study_plan:one",
            "request-one",
            "c" * 64,
            "d" * 64,
            package_sha256="b" * 64,
            payload_sha256=payload_sha256,
        )
        is None
    )
    assert len(calls) == 2
    for query, params in calls:
        assert "claim_payload_sha256 = $payload_sha256" in query
        assert params["payload_sha256"] == payload_sha256


async def _async_return(value: object) -> object:
    return value
