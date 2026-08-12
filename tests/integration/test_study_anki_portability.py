"""Real-Surreal durability and native Anki round-trip contracts."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from surrealdb import RecordID  # type: ignore[import-untyped]

import api.routers.study_anki as study_anki
from api.routers.study_anki import (
    _load_export_plan,
    download_study_plan_anki,
    export_anki_package,
    inspect_export,
)
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.study.anki_jobs import (
    AnkiExportMetadata,
    AnkiExportRepository,
    AnkiJobMetadata,
    AnkiJobRepository,
)
from deeper_notebook.study.anki_package import AnkiImportOptions, inspect_anki_package
from deeper_notebook.study.anki_repository import import_anki_package
from deeper_notebook.study.plan_repository import StudyPlanRepository
from deeper_notebook.study.plans import StudyPlan, StudyPlanPreferences
from tests.fixtures.anki.build_fixtures import build_apkg

pytestmark = pytest.mark.integration_surreal


def _approved_plan(plan_id: str) -> StudyPlan:
    return StudyPlan(
        plan_id=plan_id,
        goal="Durable Anki portability",
        starting_level="beginner",
        preferences=StudyPlanPreferences(weekly_minutes=120, session_minutes=30),
        source_manifest_sha256="a" * 64,
        approved_syllabus_version=1,
        state="approved",
    )


async def _seed_unit(plan_id: str, unit_id: str) -> None:
    await repo_query(
        "CREATE study_unit CONTENT $unit;",
        {
            "unit": {
                "schema_version": 1,
                "plan_id": str(ensure_record_id(plan_id)),
                "syllabus_version": 1,
                "unit_id": unit_id,
                "position": 0,
                "title": "Imported portability",
                "objectives": ["Preserve native Anki semantics"],
                "prerequisite_unit_ids": [],
                "estimated_minutes": 30,
                "source_ids": [],
                "activities": [],
            }
        },
    )


def _job(job_id: str, plan_id: str, package_sha256: str) -> AnkiJobMetadata:
    now = datetime.now(UTC)
    return AnkiJobMetadata(
        job_id=job_id,
        plan_id=plan_id,
        file_token="upload-" + "b" * 64 + ".apkg",
        package_sha256=package_sha256,
        collection_sha256="c" * 64,
        collection_member="collection.anki2",
        card_count=2,
        transformed_count=1,
        skipped_count=0,
        rejected_count=0,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )


async def test_job_claim_is_atomic_rehydratable_and_fenced(clean_namespace) -> None:
    plan_id = "study_plan:durable-claim"
    job_id = "anki_job:" + "1" * 64
    package_sha256 = "a" * 64
    first_repository = AnkiJobRepository()
    second_repository = AnkiJobRepository()
    await first_repository.create(_job(job_id, plan_id, package_sha256))

    # A fresh repository instance rehydrates the durable preview projection.
    rehydrated = await second_repository.get(job_id, plan_id)
    assert rehydrated is not None
    assert rehydrated.file_token.startswith("upload-")

    first, second = await asyncio.gather(
        first_repository.claim(job_id, plan_id, package_sha256, "same-request", "d" * 64),
        second_repository.claim(job_id, plan_id, package_sha256, "same-request", "d" * 64),
    )
    assert sorted((str(first), str(second))) == ["owner", "replay"]
    owner = first if first == "owner" else second
    assert owner.owner_token

    # A different request/options tuple cannot replace a live owner.
    conflict = await second_repository.claim(
        job_id, plan_id, package_sha256, "different-request", "e" * 64
    )
    assert conflict == "conflict"

    completed = await first_repository.complete(
        job_id,
        plan_id,
        "same-request",
        "d" * 64,
        "study_anki_import:receipt",
        owner.owner_token,
        package_sha256=package_sha256,
    )
    assert completed is not None and completed.status == "published"
    assert await second_repository.claim(
        job_id, plan_id, package_sha256, "same-request", "d" * 64
    ) == "replay"


async def test_expired_owner_can_be_reclaimed_but_stale_fence_cannot_complete(clean_namespace) -> None:
    plan_id = "study_plan:durable-reclaim"
    job_id = "anki_job:" + "2" * 64
    package_sha256 = "a" * 64
    repository = AnkiJobRepository()
    await repository.create(_job(job_id, plan_id, package_sha256))
    old_owner = "f" * 64
    old_request = "crashed-request"
    old_options = "e" * 64
    await repo_query(
        "UPDATE $job SET status = 'publishing', claim_request_id = $request_id, "
        "claim_options_sha256 = $options_sha256, claim_package_sha256 = $package_sha256, "
        "claim_owner_token = $owner_token, claim_expires_at = $expired, updated_at = time::now() "
        "WHERE job_id = $job_id RETURN AFTER;",
        {
            "job": RecordID("study_anki_job", job_id.split(":", 1)[1]),
            "job_id": job_id,
            "request_id": old_request,
            "options_sha256": old_options,
            "package_sha256": package_sha256,
            "owner_token": old_owner,
            "expired": datetime.now(UTC) - timedelta(seconds=2),
        },
    )
    reclaimed = await repository.claim(job_id, plan_id, package_sha256, old_request, old_options)
    assert reclaimed == "owner" and reclaimed.owner_token != old_owner
    assert await repository.fail(
        job_id,
        plan_id,
        old_request,
        old_options,
        old_owner,
        package_sha256=package_sha256,
    ) is None
    completed = await repository.complete(
        job_id,
        plan_id,
        old_request,
        old_options,
        "study_anki_import:reclaimed",
        reclaimed.owner_token,
        package_sha256=package_sha256,
    )
    assert completed is not None and completed.status == "published"


async def test_terminal_job_writes_cannot_overwrite_published_or_failed(
    clean_namespace,
) -> None:
    plan_id = "study_plan:durable-terminal-cas"
    package_sha256 = "a" * 64
    repository = AnkiJobRepository()

    published_job = "anki_job:" + "3" * 64
    await repository.create(_job(published_job, plan_id, package_sha256))
    published_claim = await repository.claim(
        published_job, plan_id, package_sha256, "published-request", "d" * 64
    )
    assert published_claim == "owner"
    published = await repository.complete(
        published_job,
        plan_id,
        "published-request",
        "d" * 64,
        "study_anki_import:published",
        published_claim.owner_token,
        package_sha256=package_sha256,
    )
    assert published is not None and published.status == "published"
    assert await repository.fail(
        published_job,
        plan_id,
        "published-request",
        "d" * 64,
        published_claim.owner_token,
        package_sha256=package_sha256,
    ) is None
    current_published = await repository.get(published_job, plan_id)
    assert current_published is not None
    assert current_published.status == "published"
    assert current_published.receipt_id == "study_anki_import:published"

    failed_job = "anki_job:" + "4" * 64
    await repository.create(_job(failed_job, plan_id, package_sha256))
    failed_claim = await repository.claim(
        failed_job, plan_id, package_sha256, "failed-request", "e" * 64
    )
    assert failed_claim == "owner"
    failed = await repository.fail(
        failed_job,
        plan_id,
        "failed-request",
        "e" * 64,
        failed_claim.owner_token,
        package_sha256=package_sha256,
    )
    assert failed is not None and failed.status == "failed"
    assert await repository.complete(
        failed_job,
        plan_id,
        "failed-request",
        "e" * 64,
        "study_anki_import:should-not-publish",
        failed_claim.owner_token,
        package_sha256=package_sha256,
    ) is None
    current_failed = await repository.get(failed_job, plan_id)
    assert current_failed is not None
    assert current_failed.status == "failed"
    assert current_failed.receipt_id is None


async def test_export_metadata_rehydrates_and_downloads_only_hashed_owned_file(
    clean_namespace, tmp_path, monkeypatch
) -> None:
    package = build_apkg(tmp_path / "download.apkg", kind="cloze")
    export_root = tmp_path / "exports"
    export_root.mkdir()
    token = "export-" + "3" * 64 + ".apkg"
    owned = export_root / token
    shutil.copyfile(package, owned)
    digest = hashlib.sha256(owned.read_bytes()).hexdigest()
    inspected = inspect_export(owned)
    download_id = "anki_download:" + "4" * 64
    now = datetime.now(UTC)
    metadata = AnkiExportMetadata(
        download_id=download_id,
        plan_id="study_plan:durable-download",
        file_token=token,
        plan_revision=1,
        syllabus_version=1,
        package_sha256=digest,
        receipt_id="anki_export:receipt",
        card_count=len(inspected.stable_note_guids),
        stable_note_guids=inspected.stable_note_guids,
        stable_model_ids=inspected.stable_model_ids,
        stable_deck_ids=inspected.stable_deck_ids,
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    await AnkiExportRepository().create(metadata)
    monkeypatch.setattr("api.routers.study_anki._export_root", lambda: export_root)
    import api.routers.study_anki as study_anki

    study_anki._DOWNLOADS.clear()
    response = await download_study_plan_anki(download_id)
    assert Path(response.path) == owned
    rehydrated = await AnkiExportRepository().get(download_id)
    assert rehydrated is not None and rehydrated.package_sha256 == digest


async def test_expiry_cleanup_removes_expired_owned_bytes_and_preserves_live_rows(
    clean_namespace, tmp_path, monkeypatch
) -> None:
    import_root = tmp_path / "imports"
    export_root = tmp_path / "exports"
    import_root.mkdir()
    export_root.mkdir()
    expired_upload_token = "upload-" + "5" * 64 + ".apkg"
    live_upload_token = "upload-" + "6" * 64 + ".apkg"
    expired_export_token = "export-" + "7" * 64 + ".apkg"
    live_export_token = "export-" + "8" * 64 + ".apkg"
    (import_root / expired_upload_token).write_bytes(b"expired upload")
    (import_root / live_upload_token).write_bytes(b"live upload")
    (export_root / expired_export_token).write_bytes(b"expired export")
    (export_root / live_export_token).write_bytes(b"live export")
    now = datetime.now(UTC)
    jobs = AnkiJobRepository()
    await jobs.create(
        _job("anki_job:" + "5" * 64, "study_plan:expiry", "a" * 64).model_copy(
            update={"file_token": expired_upload_token, "expires_at": now - timedelta(minutes=1)}
        )
    )
    await jobs.create(
        _job("anki_job:" + "6" * 64, "study_plan:expiry", "b" * 64).model_copy(
            update={"file_token": live_upload_token, "expires_at": now + timedelta(hours=1)}
        )
    )
    exports = AnkiExportRepository()
    for suffix, token, expires_at in (
        ("7", expired_export_token, now - timedelta(minutes=1)),
        ("8", live_export_token, now + timedelta(hours=1)),
    ):
        await exports.create(
            AnkiExportMetadata(
                download_id="anki_download:" + suffix * 64,
                plan_id="study_plan:expiry",
                file_token=token,
                plan_revision=1,
                syllabus_version=1,
                package_sha256="a" * 64,
                receipt_id="anki_export:expiry-" + suffix,
                card_count=0,
                stable_note_guids=(),
                stable_model_ids=(),
                stable_deck_ids=(),
                created_at=now,
                expires_at=expires_at,
            )
        )
    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "_import_root", lambda: import_root)
    monkeypatch.setattr(study_anki, "_export_root", lambda: export_root)
    await study_anki._cleanup_expired_metadata()
    assert not (import_root / expired_upload_token).exists()
    assert (import_root / live_upload_token).exists()
    assert not (export_root / expired_export_token).exists()
    assert (export_root / live_export_token).exists()
    assert await jobs.get("anki_job:" + "5" * 64, "study_plan:expiry") is None
    assert await jobs.get("anki_job:" + "6" * 64, "study_plan:expiry") is not None
    assert await exports.get("anki_download:" + "7" * 64) is None
    assert await exports.get("anki_download:" + "8" * 64) is not None


async def test_durable_metadata_active_capacity_is_bounded(clean_namespace) -> None:
    from deeper_notebook.study.anki_jobs import (
        MAX_METADATA_ROWS,
        AnkiMetadataCapacityError,
    )

    repository = AnkiJobRepository()
    for index in range(MAX_METADATA_ROWS):
        suffix = f"{index + 1:064x}"
        await repository.create(_job("anki_job:" + suffix, "study_plan:capacity", "a" * 64))
    with pytest.raises(AnkiMetadataCapacityError):
        await repository.create(_job("anki_job:" + "f" * 64, "study_plan:capacity", "b" * 64))
    rows = await repo_query("SELECT job_id FROM study_anki_job WHERE expires_at > time::now() LIMIT 257;")
    assert len(rows) == MAX_METADATA_ROWS


@pytest.mark.parametrize("kind", ["basic", "reverse", "cloze"])
async def test_import_compatibility_projection_roundtrips_native_semantics(
    clean_namespace, tmp_path, kind: str
) -> None:
    plan_id = f"study_plan:roundtrip-{kind}"
    await StudyPlanRepository().create(_approved_plan(plan_id))
    await _seed_unit(plan_id, "roundtrip-unit")
    source = build_apkg(tmp_path / f"{kind}.apkg", kind=kind, back="Mnemonic")
    original = inspect_anki_package(source)
    receipt = await import_anki_package(
        plan_id,
        source,
        AnkiImportOptions(syllabus_unit_id="roundtrip-unit"),
        f"roundtrip-{kind}",
    )
    assert receipt.card_count == len(original.cards)

    # This load crosses the native Study card links and the durable
    # study_anki_card_compat projection, as a fresh export worker would.
    exported_plan = await _load_export_plan(plan_id)
    assert len(exported_plan["cards"]) == len(original.cards)
    assert all(card.get("source_fields") for card in exported_plan["cards"])
    destination = tmp_path / f"{kind}-roundtrip.apkg"
    result = export_anki_package(exported_plan, destination)
    exported = inspect_anki_package(result.path)
    assert result.receipt.card_count == inspect_export(result.path).card_count
    if kind == "reverse":
        assert len(exported.cards) == 2
        assert {card.kind for card in exported.cards} == {"basic", "reverse"}
        assert all(card.source_fields == original.cards[0].source_fields for card in exported.cards)
        assert result.receipt.card_count == 2
    elif kind == "cloze":
        assert len(exported.cards) == 1
        assert exported.cards[0].kind == "cloze"
        assert "{{c1::" in exported.cards[0].source_fields[0]
        assert exported.cards[0].source_fields[1] == "Mnemonic"
    else:
        assert len(exported.cards) == 1
        assert exported.cards[0].kind == "basic"
        assert exported.cards[0].source_fields == original.cards[0].source_fields
