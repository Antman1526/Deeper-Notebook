from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import study_anki
from deeper_notebook.study.anki_package import AnkiImportOptions, inspect_anki_package
from deeper_notebook.study.anki_repository import (
    AnkiImportRepository,
    import_anki_package,
)
from tests.fixtures.anki.build_fixtures import build_apkg


def test_inspection_retains_original_note_identity_and_clean_fields(tmp_path: Path) -> None:
    inspection = inspect_anki_package(
        build_apkg(tmp_path / "reverse.apkg", kind="reverse")
    )

    assert len(inspection.cards) == 2
    assert {card.source_note_id for card in inspection.cards} == {inspection.cards[0].note_id}
    assert inspection.cards[0].source_fields == (
        "What is inertia?",
        "Resistance to a change in motion.",
    )
    assert inspection.cards[1].source_fields == inspection.cards[0].source_fields


def test_cloze_export_round_trip_preserves_raw_tokens_and_extra(tmp_path: Path) -> None:
    from api.routers.study_anki import export_anki_package

    package = build_apkg(tmp_path / "cloze.apkg", kind="cloze", back="Mnemonic")
    inspection = inspect_anki_package(package)
    raw = inspection.cards[0]
    exported = export_anki_package(
        {
            "plan_id": "study_plan:repair",
            "state": "approved",
            "approved_syllabus_version": 1,
            "cards": [
                {
                    "card_id": "study_card:cloze",
                    "version": 1,
                    "front": raw.front,
                    "back": raw.back,
                    "kind": "cloze",
                    "source_note_id": raw.source_note_id,
                    "source_model_kind": raw.source_model_kind,
                    "template_ord": raw.template_ord,
                    "source_fields": raw.source_fields,
                }
            ],
        },
        tmp_path / "exported.apkg",
    )

    round_trip = inspect_anki_package(exported.path)
    assert round_trip.cards[0].kind == "cloze"
    assert "{{c1::" in round_trip.cards[0].source_fields[0]
    assert round_trip.cards[0].source_fields[1] == "Mnemonic"


def test_multicloze_export_receipt_counts_native_cards(tmp_path: Path) -> None:
    from api.routers.study_anki import export_anki_package, inspect_export

    result = export_anki_package(
        {
            "plan_id": "study_plan:multi-cloze",
            "state": "approved",
            "approved_syllabus_version": 1,
            "cards": [
                {
                    "card_id": "study_card:multi-cloze",
                    "version": 1,
                    "front": "The first and second",
                    "back": "Mnemonic",
                    "kind": "cloze",
                    "source_note_id": "note-multi",
                    "source_model_kind": "cloze",
                    "template_ord": 0,
                    "source_fields": ("The {{c1::first}} and {{c2::second}}", "Mnemonic"),
                }
            ],
        },
        tmp_path / "multi-cloze.apkg",
    )
    inspection = inspect_export(result.path)
    assert inspection.card_count == 2
    assert result.receipt.card_count == inspection.card_count == 2


def test_export_semantic_identity_is_stable_when_cards_arrive_out_of_order(tmp_path: Path) -> None:
    from api.routers.study_anki import export_anki_package
    from tests.test_study_anki_export import PLAN_EXPORT

    first = export_anki_package(PLAN_EXPORT, tmp_path / "ordered.apkg")
    reversed_plan = {**PLAN_EXPORT, "cards": tuple(reversed(PLAN_EXPORT["cards"]))}
    second = export_anki_package(reversed_plan, tmp_path / "reversed.apkg")
    assert first.receipt.receipt_id == second.receipt.receipt_id
    assert first.receipt.card_count == second.receipt.card_count == 4
    assert first.receipt.stable_note_guids == second.receipt.stable_note_guids


def test_import_persists_bounded_compatibility_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = build_apkg(tmp_path / "compat.apkg", kind="cloze", back="Mnemonic")
    mutations: list[tuple[str, dict[str, object]]] = []

    async def fake_query(query: str, params: dict[str, object]):
        if query.startswith("SELECT"):
            return []
        mutations.append((query, params))
        return [{"result": params["receipt"]}]

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", fake_query)
    asyncio.run(
        import_anki_package(
            "study_plan:compat", package, AnkiImportOptions(), "repair-request"
        )
    )

    query, params = mutations[0]
    assert "study_anki_card_compat" in query
    compat = params["compat_0"]
    assert isinstance(compat, dict)
    assert compat["source_note_id"]
    assert "{{c1::" in compat["source_fields"][0]
    assert compat["source_fields"][1] == "Mnemonic"


def test_migration_45_is_additive_and_reversible() -> None:
    up = Path("deeper_notebook/database/migrations/45.surrealql").read_text()
    down = Path("deeper_notebook/database/migrations/45_down.surrealql").read_text()
    assert "study_anki_card_compat" in up
    assert "study_anki_job" in up
    assert "study_anki_export" in up
    assert "REMOVE TABLE IF EXISTS study_anki_card_compat" in down
    assert "REMOVE TABLE IF EXISTS study_anki_job" in down
    assert "REMOVE TABLE IF EXISTS study_anki_export" in down


def test_job_and_download_authority_rehydrates_without_process_caches() -> None:
    from deeper_notebook.study.anki_jobs import AnkiJobRepository

    assert AnkiJobRepository is not None
    study_anki._IMPORT_JOBS.clear()
    study_anki._DOWNLOADS.clear()


def test_metadata_create_contains_active_capacity_guard() -> None:
    source = Path("deeper_notebook/study/anki_jobs.py").read_text()
    assert "study_anki_job_capacity" in source
    assert "study_anki_export_capacity" in source
    assert "MAX_METADATA_ROWS" in source


def test_task_owned_roots_are_under_canonical_data_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(study_anki, "DATA_FOLDER", tmp_path / "canonical-data")
    import_root = study_anki._import_root()
    export_root = study_anki._export_root()
    assert import_root.is_relative_to((tmp_path / "canonical-data").resolve())
    assert export_root.is_relative_to((tmp_path / "canonical-data").resolve())
    assert not import_root.is_relative_to(Path.cwd() / "data")


@pytest.mark.asyncio
async def test_durable_job_claim_rejects_different_request_or_options(monkeypatch: pytest.MonkeyPatch) -> None:
    from deeper_notebook.study.anki_jobs import AnkiJobRepository

    calls: list[str] = []

    async def fake_query(query: str, params: dict[str, object]):
        calls.append(query)
        if query.startswith("UPDATE"):
            return []
        return [{
            "job_id": "anki_job:" + "a" * 64,
            "plan_id": "study_plan:one",
            "file_token": "upload-" + "d" * 64 + ".apkg",
            "package_sha256": "b" * 64,
            "collection_sha256": "e" * 64,
            "collection_member": "collection.anki2",
            "card_count": 1,
            "transformed_count": 0,
            "skipped_count": 0,
            "rejected_count": 0,
            "claim_request_id": "request-one",
            "claim_options_sha256": "c" * 64,
            "status": "publishing",
            "created_at": "2026-08-12T00:00:00+00:00",
            "updated_at": "2026-08-12T00:00:00+00:00",
            "expires_at": "2026-08-13T00:00:00+00:00",
        }]

    monkeypatch.setattr("deeper_notebook.study.anki_jobs.repo_query", fake_query)
    decision = await AnkiJobRepository().claim(
        "anki_job:" + "a" * 64,
        "study_plan:one",
        "b" * 64,
        "request-two",
        "d" * 64,
    )
    assert decision == "conflict"
    assert any("claim_request_id" in query for query in calls)


def test_status_rehydrates_from_durable_metadata_after_cache_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from deeper_notebook.study.anki_jobs import AnkiJobMetadata

    package = build_apkg(tmp_path / "rehydrate.apkg")
    inspection = inspect_anki_package(package)
    import_root = tmp_path / "imports"
    import_root.mkdir()
    token_path = import_root / ("upload-" + "f" * 64 + ".apkg")
    token_path.write_bytes(package.read_bytes())
    now = datetime.now(UTC)
    metadata = AnkiJobMetadata(
        job_id="anki_job:" + "a" * 64,
        plan_id="study_plan:one",
        file_token=token_path.name,
        package_sha256=inspection.package_sha256,
        collection_sha256=inspection.collection_sha256,
        collection_member="collection.anki2",
        card_count=1,
        transformed_count=0,
        skipped_count=0,
        rejected_count=0,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
    )

    class FakeJobs:
        async def get(self, job_id: str, plan_id: str):
            return metadata if job_id == metadata.job_id and plan_id == metadata.plan_id else None

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "study_workbench_enabled", lambda: True)
    monkeypatch.setattr(study_anki, "_import_root", lambda: import_root)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    app = FastAPI()
    app.include_router(study_anki.router, prefix="/api")
    study_anki._IMPORT_JOBS.clear()
    with TestClient(app) as client:
        response = client.get(
            "/api/study/plans/study_plan%3Aone/anki/import/anki_job:" + "a" * 64
        )
    assert response.status_code == 200
    assert response.json()["job_id"] == metadata.job_id
    assert response.json()["card_count"] == 1


@pytest.mark.asyncio
async def test_expiry_cleanup_unlinks_only_expired_owned_files_and_keeps_live_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_root = tmp_path / "imports"
    export_root = tmp_path / "exports"
    import_root.mkdir()
    export_root.mkdir()
    expired_upload = import_root / ("upload-" + "a" * 64 + ".apkg")
    live_upload = import_root / ("upload-" + "b" * 64 + ".apkg")
    expired_export = export_root / ("export-" + "c" * 64 + ".apkg")
    expired_upload.write_bytes(b"expired")
    live_upload.write_bytes(b"live")
    expired_export.write_bytes(b"expired")

    class FakeJobs:
        async def list_expired(self, *, limit: int):
            return (("anki_job:" + "1" * 64, expired_upload.name),)

        async def delete_expired(self, job_id: str):
            return True

        async def has_file_token(self, file_token: str):
            return False

    class FakeExports:
        async def list_expired(self, *, limit: int):
            return (("anki_download:" + "3" * 64, expired_export.name),)

        async def delete_expired(self, download_id: str):
            return True

        async def has_file_token(self, file_token: str):
            return False

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiExportRepository", FakeExports)
    monkeypatch.setattr(study_anki, "_import_root", lambda: import_root)
    monkeypatch.setattr(study_anki, "_export_root", lambda: export_root)
    await study_anki._cleanup_expired_metadata()
    assert not expired_upload.exists()
    assert live_upload.exists()
    assert not expired_export.exists()


@pytest.mark.asyncio
async def test_expiry_cleanup_keeps_metadata_for_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = "upload-" + "d" * 64 + ".apkg"
    calls: list[str] = []

    class FakeJobs:
        async def list_expired(self, *, limit: int):
            calls.append("listed")
            return (("anki_job:" + "4" * 64, token),)

        async def delete_expired(self, job_id: str):
            calls.append("deleted")
            return True

        async def has_file_token(self, file_token: str):
            return False

    class FakeExports:
        async def list_expired(self, *, limit: int):
            raise RuntimeError("second purge unavailable")

        async def has_file_token(self, file_token: str):
            return False

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiExportRepository", FakeExports)
    monkeypatch.setattr(study_anki, "_import_root", lambda: tmp_path / "missing-root")
    monkeypatch.setattr(study_anki, "_export_root", lambda: tmp_path / "exports")
    await study_anki._cleanup_expired_metadata()
    assert calls == ["listed"]


@pytest.mark.asyncio
async def test_expiry_cleanup_retries_tombstone_after_unlink_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_root = tmp_path / "imports"
    export_root = tmp_path / "exports"
    import_root.mkdir()
    export_root.mkdir()
    token = "upload-" + "e" * 64 + ".apkg"
    source = import_root / token
    source.write_bytes(b"expired")
    tombstone = import_root / (".expired-upload-" + "e" * 64 + ".apkg")
    state = {"listed": True}

    class FakeJobs:
        async def list_expired(self, *, limit: int):
            return (("anki_job:" + "5" * 64, token),) if state["listed"] else ()

        async def delete_expired(self, job_id: str):
            state["listed"] = False
            return True

        async def has_file_token(self, file_token: str):
            return state["listed"]

    class FakeExports:
        async def list_expired(self, *, limit: int):
            return ()

        async def has_file_token(self, file_token: str):
            return False

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiExportRepository", FakeExports)
    monkeypatch.setattr(study_anki, "_import_root", lambda: import_root)
    monkeypatch.setattr(study_anki, "_export_root", lambda: export_root)
    original_remove = study_anki._remove_tombstone
    monkeypatch.setattr(study_anki, "_remove_tombstone", lambda path: None)
    await study_anki._cleanup_expired_metadata()
    assert tombstone.exists() and not source.exists()
    monkeypatch.setattr(study_anki, "_remove_tombstone", original_remove)
    await study_anki._cleanup_expired_metadata()
    assert not tombstone.exists()


@pytest.mark.asyncio
async def test_expiry_cleanup_restores_original_when_metadata_delete_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import_root = tmp_path / "imports"
    export_root = tmp_path / "exports"
    import_root.mkdir()
    export_root.mkdir()
    token = "upload-" + "f" * 64 + ".apkg"
    source = import_root / token
    source.write_bytes(b"expired")

    class FakeJobs:
        async def list_expired(self, *, limit: int):
            return (("anki_job:" + "6" * 64, token),)

        async def delete_expired(self, job_id: str):
            return False

        async def has_file_token(self, file_token: str):
            return True

    class FakeExports:
        async def list_expired(self, *, limit: int):
            return ()

        async def has_file_token(self, file_token: str):
            return False

    monkeypatch.setattr(study_anki, "_test_in_memory_metadata", lambda: False)
    monkeypatch.setattr(study_anki, "AnkiJobRepository", FakeJobs)
    monkeypatch.setattr(study_anki, "AnkiExportRepository", FakeExports)
    monkeypatch.setattr(study_anki, "_import_root", lambda: import_root)
    monkeypatch.setattr(study_anki, "_export_root", lambda: export_root)
    await study_anki._cleanup_expired_metadata()
    assert source.exists()
    assert not (import_root / (".expired-upload-" + "f" * 64 + ".apkg")).exists()
