from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers import study_anki
from deeper_notebook.database.repository import ensure_record_id
from deeper_notebook.study.anki_jobs import AnkiClaimResult, AnkiJobMetadata
from deeper_notebook.study.anki_package import AnkiImportOptions, inspect_anki_package
from deeper_notebook.study.anki_repository import (
    AnkiCompatibilityReceipt,
    canonical_anki_import_payload,
)
from tests.fixtures.anki.build_fixtures import build_apkg
from tests.test_study_anki_export import PLAN_EXPORT


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: True)
    study_anki._IMPORT_JOBS.clear()
    study_anki._DOWNLOADS.clear()
    monkeypatch.setattr(study_anki, "study_workbench_enabled", lambda: True)
    monkeypatch.setattr(study_anki, "_export_root", lambda: tmp_path / "exports")
    monkeypatch.setattr(study_anki, "_import_root", lambda: tmp_path / "imports")
    monkeypatch.setattr(study_anki, "_load_export_plan", lambda plan_id: PLAN_EXPORT)
    app = FastAPI()
    app.include_router(study_anki.router, prefix="/api")
    return TestClient(app)


def _receipt(
    package: Path,
    request_id: str,
    *,
    plan_id: str = "study_plan:one",
    options: AnkiImportOptions | None = None,
) -> AnkiCompatibilityReceipt:
    inspection = inspect_anki_package(package)
    canonical_plan_id = str(ensure_record_id(plan_id))
    payload_sha256, _ = canonical_anki_import_payload(
        plan_id, inspection, options or AnkiImportOptions()
    )
    return AnkiCompatibilityReceipt(
        receipt_id="study_anki_import:" + "a" * 64,
        plan_id=canonical_plan_id,
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


def test_feature_off_is_uniform_404_before_body_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(study_anki, "study_workbench_enabled", lambda: False)
    app = FastAPI()
    app.include_router(study_anki.router, prefix="/api")
    with TestClient(app) as client:
        responses = [
            client.post("/api/study/plans/not-a-plan/anki/import", data={"options": "{"}),
            client.post("/api/study/plans/not-a-plan/anki/export", json={"unexpected": True}),
            client.get("/api/study/plans/not-a-plan/anki/import/../../etc/passwd"),
        ]
    assert {response.status_code for response in responses} == {404}


def test_upload_preview_does_not_publish_and_returns_bounded_summary(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "deck.apkg"
    package.write_bytes(b"not-a-package")
    publish_called = False

    async def forbidden_publish(*args: object, **kwargs: object) -> object:
        nonlocal publish_called
        publish_called = True
        raise AssertionError("preview must not publish")

    monkeypatch.setattr(study_anki, "_publish_import", forbidden_publish)
    response = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("deck.apkg", io.BytesIO(package.read_bytes()), "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert response.status_code == 422
    assert publish_called is False


def test_valid_preview_requires_explicit_publish_and_replay_is_bound(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = build_apkg(tmp_path / "valid.apkg")
    request_id = "anki-request-one"
    receipt = _receipt(package, request_id)
    published: list[str] = []

    async def fake_publish(plan_id: str, job: object, options: object, caller_request_id: str):
        published.append(caller_request_id)
        return receipt

    monkeypatch.setattr(study_anki, "_publish_import", fake_publish)
    preview = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("valid.apkg", package.read_bytes(), "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert preview.status_code == 200
    job_id = preview.json()["job_id"]
    assert preview.json()["status"] == "preview_ready"
    assert client.get(f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}").json()["receipt_id"] is None

    missing_confirmation = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert missing_confirmation.status_code == 200
    assert missing_confirmation.json()["status"] == "published"
    assert published == [request_id]
    assert not study_anki._IMPORT_JOBS[job_id].path.exists()

    replay = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert replay.status_code == 200 and replay.json()["status"] == "replayed"
    mismatch = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": "different-request", "options": {"schema_version": 1}},
    )
    assert mismatch.status_code == 409


def test_publish_retry_reconciles_receipt_after_durable_complete_crash(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = build_apkg(tmp_path / "crash-window.apkg")
    request_id = "crash-window-request"
    receipt = _receipt(package, request_id)
    state: dict[str, object] = {"metadata": None, "complete_calls": 0, "native_committed": False}
    owner_token = "a" * 64

    class FakeJobs:
        async def create(self, metadata: AnkiJobMetadata) -> AnkiJobMetadata:
            state["metadata"] = metadata
            return metadata

        async def get(self, job_id: str, plan_id: str) -> AnkiJobMetadata | None:
            metadata = state["metadata"]
            if isinstance(metadata, AnkiJobMetadata) and metadata.job_id == job_id and metadata.plan_id == plan_id:
                return metadata
            return None

        async def claim(
            self,
            job_id: str,
            plan_id: str,
            package_sha256: str,
            request_id: str,
            options_sha256: str,
            payload_sha256: str,
        ) -> AnkiClaimResult:
            metadata = state["metadata"]
            assert isinstance(metadata, AnkiJobMetadata)
            if metadata.status == "preview_ready":
                state["metadata"] = metadata.model_copy(
                    update={
                        "status": "publishing",
                        "claim_request_id": request_id,
                            "claim_options_sha256": options_sha256,
                            "claim_package_sha256": package_sha256,
                            "claim_payload_sha256": payload_sha256,
                        "claim_owner_token": owner_token,
                        "claim_expires_at": datetime.now(UTC) + timedelta(minutes=5),
                    }
                )
                return AnkiClaimResult("owner", owner_token)
            return AnkiClaimResult("replay")

        async def complete(
            self,
            job_id: str,
            plan_id: str,
            request_id: str,
            options_sha256: str,
            receipt_id: str,
            owner: str,
            *,
            package_sha256: str,
            payload_sha256: str,
        ) -> AnkiJobMetadata | None:
            state["complete_calls"] = int(state["complete_calls"]) + 1
            if int(state["complete_calls"]) == 1:
                state["native_committed"] = True
                raise RuntimeError("simulated crash after native publication")
            metadata = state["metadata"]
            assert isinstance(metadata, AnkiJobMetadata)
            repaired = metadata.model_copy(update={"status": "published", "receipt_id": receipt_id})
            state["metadata"] = repaired
            return repaired

    class FakeReceipts:
        async def _find_by_request(self, plan_id: str, caller_request_id: str):
            if state["native_committed"] and caller_request_id == request_id:
                return receipt
            return None

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiImportRepository", FakeReceipts)
    monkeypatch.setattr(
        study_anki,
        "_publish_import",
        lambda *args, **kwargs: _async_return(receipt),
    )

    preview = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("crash-window.apkg", package.read_bytes(), "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert preview.status_code == 200
    job_id = preview.json()["job_id"]
    first = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert first.status_code == 503

    retry = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "replayed"
    repaired = state["metadata"]
    assert isinstance(repaired, AnkiJobMetadata)
    assert repaired.status == "published"
    assert repaired.receipt_id == receipt.receipt_id
    assert state["complete_calls"] == 2


def test_durable_claim_uses_repository_canonical_plan_payload(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = build_apkg(tmp_path / "canonical-plan.apkg")
    plan_id = "study_plan:canonical-plan"
    request_id = "canonical-plan-request"
    receipt = _receipt(package, request_id, plan_id=plan_id)
    claims: list[str] = []
    state: dict[str, AnkiJobMetadata] = {}

    class FakeJobs:
        async def create(self, metadata: AnkiJobMetadata) -> AnkiJobMetadata:
            state["metadata"] = metadata
            return metadata

        async def get(self, _job_id: str, _plan_id: str) -> AnkiJobMetadata:
            return state["metadata"]

        async def claim(
            self,
            _job_id: str,
            _plan_id: str,
            _package_sha256: str,
            _request_id: str,
            _options_sha256: str,
            payload_sha256: str,
        ) -> AnkiClaimResult:
            claims.append(payload_sha256)
            return AnkiClaimResult("owner", "c" * 64)

        async def complete(self, *args: object, **kwargs: object) -> AnkiJobMetadata:
            return state["metadata"].model_copy(
                update={"status": "published", "receipt_id": receipt.receipt_id}
            )

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(
        study_anki, "_publish_import", lambda *args, **kwargs: _async_return(receipt)
    )
    encoded_plan_id = plan_id.replace(":", "%3A")
    preview = client.post(
        f"/api/study/plans/{encoded_plan_id}/anki/import",
        files={"file": ("canonical-plan.apkg", package.read_bytes(), "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert preview.status_code == 200
    job_id = preview.json()["job_id"]
    response = client.post(
        f"/api/study/plans/{encoded_plan_id}/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert response.status_code == 200
    assert claims == [receipt.payload_sha256]


def test_publish_rejects_divergent_receipt_payload_before_durable_complete(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = build_apkg(tmp_path / "divergent-receipt.apkg")
    request_id = "divergent-receipt-request"
    receipt = _receipt(package, request_id).model_copy(update={"payload_sha256": "f" * 64})
    complete_calls: list[tuple[object, ...]] = []
    state: dict[str, AnkiJobMetadata] = {}

    class FakeJobs:
        async def create(self, metadata: AnkiJobMetadata) -> AnkiJobMetadata:
            state["metadata"] = metadata
            return metadata

        async def get(self, _job_id: str, _plan_id: str) -> AnkiJobMetadata:
            return state["metadata"]

        async def claim(self, *args: object, **kwargs: object) -> AnkiClaimResult:
            return AnkiClaimResult("owner", "c" * 64)

        async def complete(self, *args: object, **kwargs: object) -> AnkiJobMetadata:
            complete_calls.append(args)
            return state["metadata"].model_copy(
                update={"status": "published", "receipt_id": receipt.receipt_id}
            )

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(
        study_anki, "_publish_import", lambda *args, **kwargs: _async_return(receipt)
    )
    preview = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("divergent-receipt.apkg", package.read_bytes(), "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert preview.status_code == 200
    job_id = preview.json()["job_id"]
    response = client.post(
        f"/api/study/plans/study_plan%3Aone/anki/import/{job_id}:publish",
        json={"upload_id": job_id, "request_id": request_id, "options": {"schema_version": 1}},
    )
    assert response.status_code == 409
    assert complete_calls == []


@pytest.mark.asyncio
async def test_replay_rejects_receipt_from_same_request_different_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_a = build_apkg(tmp_path / "package-a.apkg", kind="basic")
    package_b = build_apkg(tmp_path / "package-b.apkg", kind="reverse")
    inspection_a = inspect_anki_package(package_a)
    inspection_b = inspect_anki_package(package_b)
    plan_id = "study_plan:authority"
    job_id = "anki_job:" + "b" * 64
    request_id = "same-request-different-package"
    options = study_anki.AnkiImportOptions()
    options_hash = study_anki._options_sha256(options)
    now = datetime.now(UTC)
    receipt_a = _receipt(package_a, request_id)
    metadata = AnkiJobMetadata(
        job_id=job_id,
        plan_id=plan_id,
        file_token="upload-" + "b" * 64 + ".apkg",
        package_sha256=inspection_b.package_sha256,
        collection_sha256=inspection_b.collection_sha256,
        collection_member=inspection_b.collection_member,
        card_count=len(inspection_b.cards),
        transformed_count=inspection_b.transformed_count,
        skipped_count=inspection_b.skipped_count,
        rejected_count=inspection_b.skipped_count,
        status="publishing",
        claim_request_id=request_id,
        claim_options_sha256=options_hash,
        claim_package_sha256=inspection_b.package_sha256,
        claim_owner_token="c" * 64,
        claim_expires_at=now + timedelta(minutes=5),
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )
    job = study_anki._ImportJob(
        job_id,
        plan_id,
        package_b,
        inspection_b,
        status="publishing",
        metadata=metadata,
    )
    complete_calls: list[tuple[object, ...]] = []

    class FakeJobs:
        async def claim(self, *args: object, **kwargs: object) -> AnkiClaimResult:
            return AnkiClaimResult("replay")

        async def get(self, job_id: str, plan_id: str) -> AnkiJobMetadata:
            return metadata

        async def complete(self, *args: object, **kwargs: object) -> AnkiJobMetadata:
            complete_calls.append(args)
            return metadata.model_copy(update={"status": "published", "receipt_id": receipt_a.receipt_id})

    class FakeReceipts:
        async def _find_by_request(self, plan_id: str, request_id: str) -> AnkiCompatibilityReceipt:
            return receipt_a

    monkeypatch.setattr(study_anki, "_durable_metadata_enabled", lambda: True)
    monkeypatch.setattr(study_anki, "_load_job", lambda *_args, **_kwargs: _async_return(job))
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiImportRepository", FakeReceipts)

    with pytest.raises(HTTPException) as exc_info:
        await study_anki.publish_anki_import(
            plan_id,
            job_id,
            study_anki.AnkiImportPublishRequest(
                upload_id=job_id,
                request_id=request_id,
                options=study_anki.AnkiHttpOptions(schema_version=1),
            ),
        )

    assert exc_info.value.status_code == 409
    assert complete_calls == []
    assert metadata.status == "publishing"
    assert metadata.receipt_id is None


@pytest.mark.asyncio
async def test_published_replay_rejects_receipt_from_different_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_a = build_apkg(tmp_path / "published-a.apkg", kind="basic")
    package_b = build_apkg(tmp_path / "published-b.apkg", kind="reverse")
    inspection_b = inspect_anki_package(package_b)
    plan_id = "study_plan:published-authority"
    job_id = "anki_job:" + "d" * 64
    request_id = "published-replay-different-package"
    options = study_anki.AnkiImportOptions()
    options_hash = study_anki._options_sha256(options)
    now = datetime.now(UTC)
    receipt_a = _receipt(package_a, request_id)
    metadata = AnkiJobMetadata(
        job_id=job_id,
        plan_id=plan_id,
        file_token="upload-" + "d" * 64 + ".apkg",
        package_sha256=inspection_b.package_sha256,
        collection_sha256=inspection_b.collection_sha256,
        collection_member=inspection_b.collection_member,
        card_count=len(inspection_b.cards),
        transformed_count=inspection_b.transformed_count,
        skipped_count=inspection_b.skipped_count,
        rejected_count=inspection_b.skipped_count,
        status="published",
        claim_request_id=request_id,
        claim_options_sha256=options_hash,
        claim_package_sha256=inspection_b.package_sha256,
        claim_owner_token="e" * 64,
        claim_expires_at=now + timedelta(minutes=5),
        receipt_id=receipt_a.receipt_id,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )
    job = study_anki._ImportJob(
        job_id,
        plan_id,
        package_b,
        inspection_b,
        status="published",
        metadata=metadata,
    )

    class FakeJobs:
        async def get(self, job_id: str, plan_id: str) -> AnkiJobMetadata:
            return metadata

    class FakeReceipts:
        async def find_by_receipt(self, plan_id: str, receipt_id: str) -> AnkiCompatibilityReceipt:
            return receipt_a

    monkeypatch.setattr(study_anki, "_durable_metadata_enabled", lambda: True)
    monkeypatch.setattr(study_anki, "_load_job", lambda *_args, **_kwargs: _async_return(job))
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiImportRepository", FakeReceipts)

    with pytest.raises(HTTPException) as exc_info:
        await study_anki.publish_anki_import(
            plan_id,
            job_id,
            study_anki.AnkiImportPublishRequest(
                upload_id=job_id,
                request_id=request_id,
                options=study_anki.AnkiHttpOptions(schema_version=1),
            ),
        )

    assert exc_info.value.status_code == 409
    assert metadata.status == "published"
    assert metadata.receipt_id == receipt_a.receipt_id


async def _async_return(value: object) -> object:
    return value


def test_upload_bound_and_download_symlink_are_rejected(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(study_anki, "MAX_UPLOAD_BYTES", 4)
    oversized = client.post(
        "/api/study/plans/study_plan%3Aone/anki/import",
        files={"file": ("oversized.apkg", b"12345", "application/octet-stream")},
        data={"options": json.dumps({"schema_version": 1})},
    )
    assert oversized.status_code == 413

    root = study_anki._export_root()
    root.mkdir(parents=True)
    outside = tmp_path / "outside.apkg"
    outside.write_bytes(b"private")
    link = root / "link.apkg"
    link.symlink_to(outside)
    download_id = "anki_download:" + "c" * 64
    study_anki._DOWNLOADS[download_id] = link
    assert client.get(f"/api/study/plans/anki/download/{download_id}").status_code == 404


def test_export_returns_opaque_download_id_and_download_has_safe_headers(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/study/plans/study_plan%3Aexport/anki/export",
        json={"schema_version": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["download_id"].startswith("anki_download:")
    assert "/" not in body["download_id"]
    downloaded = client.get(f"/api/study/plans/anki/download/{body['download_id']}")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/zip")
    assert "path" not in downloaded.text.lower()
