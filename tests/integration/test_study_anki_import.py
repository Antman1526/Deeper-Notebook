"""Disposable real-SurrealDB contracts for native Anki publication."""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.study.anki_package import (
    AnkiImportOptions,
    AnkiPackageRejected,
    inspect_anki_package,
)
from deeper_notebook.study.anki_repository import (
    AnkiImportConflict,
    AnkiImportRepository,
    AnkiImportRepositoryError,
    import_anki_package,
)
from deeper_notebook.study.plan_repository import StudyPlanRepository
from deeper_notebook.study.plans import StudyPlan, StudyPlanPreferences
from tests.fixtures.anki.build_fixtures import build_apkg

pytestmark = pytest.mark.integration_surreal


def _approved_plan(plan_id: str) -> StudyPlan:
    return StudyPlan(
        plan_id=plan_id,
        goal="Import bounded private study cards",
        starting_level="beginner",
        preferences=StudyPlanPreferences(weekly_minutes=120, session_minutes=30),
        source_manifest_sha256="a" * 64,
        approved_syllabus_version=1,
        state="approved",
    )


async def _published_state(plan_id: str) -> tuple[list[dict[str, object]], ...]:
    canonical_plan_id = str(ensure_record_id(plan_id))
    cards = await repo_query(
        "SELECT id, artifact_id, artifact_card_id, current, due, fsrs_state FROM study_card "
        "ORDER BY artifact_card_id ASC;"
    )
    links = await repo_query(
        "SELECT plan_id, card_id, syllabus_unit_id FROM study_plan_card "
        "WHERE plan_id = $plan_id ORDER BY card_id ASC;",
        {"plan_id": canonical_plan_id},
    )
    receipts = await repo_query(
        "SELECT receipt_id, plan_id, request_id, package_sha256, collection_sha256, "
        "collection_member, card_count, transformed_count, skipped_count, card_ids, "
        "deck_names, tags, media_names, syllabus_unit_id FROM study_anki_import "
        "WHERE plan_id = $plan_id ORDER BY request_id ASC;",
        {"plan_id": canonical_plan_id},
    )
    return cards, links, receipts


async def _seed_unit(
    plan_id: str, unit_id: str, *, syllabus_version: int = 1
) -> None:
    await repo_query(
        "CREATE study_unit CONTENT $unit;",
        {
            "unit": {
                "schema_version": 1,
                "plan_id": str(ensure_record_id(plan_id)),
                "syllabus_version": syllabus_version,
                "unit_id": unit_id,
                "position": 0,
                "title": "Imported recall",
                "objectives": ["Recall imported facts"],
                "prerequisite_unit_ids": [],
                "estimated_minutes": 30,
                "source_ids": [],
                "activities": [],
            }
        },
    )


async def test_anki_import_publishes_native_cards_and_reuses_exact_payload(
    clean_namespace, tmp_path
) -> None:
    plan_id = "study_plan:anki-publish"
    await StudyPlanRepository().create(_approved_plan(plan_id))
    await _seed_unit(plan_id, "native-import")
    package = build_apkg(tmp_path / "reverse.apkg", kind="reverse")
    options = AnkiImportOptions(syllabus_unit_id="native-import")

    first = await import_anki_package(plan_id, package, options, "anki-request-one")
    same_request = await import_anki_package(plan_id, package, options, "anki-request-one")
    same_payload = await import_anki_package(plan_id, package, options, "anki-request-two")

    assert first == same_request == same_payload
    assert first.card_count == 2
    assert first.transformed_count == 1
    assert first.skipped_count == 0
    assert first.collection_member == "collection.anki2"
    assert first.deck_names == ("Mechanics",)
    assert first.tags == ("mechanics", "physics")
    assert len(first.card_ids) == 2

    cards, links, receipts = await _published_state(plan_id)
    assert len(cards) == len(links) == first.card_count
    assert len(receipts) == 1
    assert {str(card["id"]) for card in cards} == set(first.card_ids)
    assert {str(link["card_id"]) for link in links} == set(first.card_ids)
    assert all(card["artifact_id"] == f"anki_import:{first.package_sha256}" for card in cards)
    assert all(card["current"] is True and card["due"] is not None for card in cards)
    assert all(link["syllabus_unit_id"] == "native-import" for link in links)
    assert receipts[0] == {
        "receipt_id": first.receipt_id,
        "plan_id": str(ensure_record_id(plan_id)),
        "request_id": "anki-request-one",
        "package_sha256": first.package_sha256,
        "collection_sha256": first.collection_sha256,
        "collection_member": "collection.anki2",
        "card_count": 2,
        "transformed_count": 1,
        "skipped_count": 0,
        "card_ids": list(first.card_ids),
        "deck_names": ["Mechanics"],
        "tags": ["mechanics", "physics"],
        "media_names": [],
        "syllabus_unit_id": "native-import",
    }

    with pytest.raises(AnkiImportConflict, match="request ID was already used"):
        await import_anki_package(
            plan_id,
            package,
            AnkiImportOptions(syllabus_unit_id="different-unit"),
            "anki-request-one",
        )
    assert await _published_state(plan_id) == (cards, links, receipts)


async def test_concurrent_same_payload_imports_converge_on_one_native_publication(
    clean_namespace, tmp_path
) -> None:
    plan_id = "study_plan:anki-race"
    await StudyPlanRepository().create(_approved_plan(plan_id))
    await _seed_unit(plan_id, "race-unit")
    inspection = inspect_anki_package(build_apkg(tmp_path / "race.apkg", kind="reverse"))
    options = AnkiImportOptions(syllabus_unit_id="race-unit")
    first_repository = AnkiImportRepository()
    second_repository = AnkiImportRepository()

    first, second = await asyncio.gather(
        first_repository.publish(plan_id, inspection, options, "anki-race-one"),
        second_repository.publish(plan_id, inspection, options, "anki-race-two"),
        return_exceptions=True,
    )

    failures = [result for result in (first, second) if isinstance(result, BaseException)]
    successes = [result for result in (first, second) if not isinstance(result, BaseException)]
    assert len(successes) >= 1
    assert all(isinstance(error, AnkiImportConflict) for error in failures)
    winner = successes[0]
    assert all(result == winner for result in successes)

    replay = await AnkiImportRepository().publish(
        plan_id,
        inspection,
        options,
        "anki-race-two" if isinstance(second, BaseException) else "anki-race-one",
    )
    assert replay == winner

    cards, links, receipts = await _published_state(plan_id)
    assert len(cards) == len(links) == winner.card_count == 2
    assert len(receipts) == 1
    assert receipts[0]["receipt_id"] == winner.receipt_id
    assert {str(link["card_id"]) for link in links} == set(winner.card_ids)


async def test_anki_import_rejections_never_publish_partial_native_state(
    clean_namespace, tmp_path
) -> None:
    plan_id = "study_plan:anki-rejections"
    archived_plan_id = "study_plan:anki-archived"
    draft_plan_id = "study_plan:anki-draft"
    foreign_plan_id = "study_plan:anki-foreign"
    await StudyPlanRepository().create(_approved_plan(plan_id))
    await StudyPlanRepository().create(
        _approved_plan(archived_plan_id).model_copy(update={"goal": "Archived import"})
    )
    await StudyPlanRepository().create(
        _approved_plan(draft_plan_id).model_copy(update={"goal": "Draft import"})
    )
    await StudyPlanRepository().create(
        _approved_plan(foreign_plan_id).model_copy(update={"goal": "Foreign unit"})
    )
    await repo_query(
        'UPDATE $plan SET state = "archived" RETURN AFTER;',
        {"plan": ensure_record_id(archived_plan_id)},
    )
    await repo_query(
        'UPDATE $plan SET state = "draft" RETURN AFTER;',
        {"plan": ensure_record_id(draft_plan_id)},
    )
    await _seed_unit(foreign_plan_id, "foreign-unit")
    await _seed_unit(plan_id, "stale-unit", syllabus_version=2)
    package = build_apkg(tmp_path / "valid.apkg")
    invalid_package = build_apkg(
        tmp_path / "invalid.apkg", back="<iframe src='file:///sentinel'></iframe>"
    )
    before = await _published_state(plan_id)

    with pytest.raises(AnkiPackageRejected, match="unsafe_field"):
        await import_anki_package(plan_id, invalid_package, AnkiImportOptions(), "invalid-package")
    with pytest.raises(AnkiImportRepositoryError, match="unavailable"):
        await import_anki_package(
            "study_plan:missing", package, AnkiImportOptions(), "missing-plan"
        )
    with pytest.raises(AnkiImportRepositoryError, match="Invalid Study Plan ID"):
        await import_anki_package("source:not-a-plan", package, AnkiImportOptions(), "wrong-plan")
    with pytest.raises(AnkiImportRepositoryError, match="unavailable"):
        await import_anki_package(
            archived_plan_id, package, AnkiImportOptions(), "archived-plan"
        )
    with pytest.raises(AnkiImportRepositoryError, match="unavailable"):
        await import_anki_package(
            draft_plan_id, package, AnkiImportOptions(), "draft-plan"
        )
    with pytest.raises(AnkiImportRepositoryError, match="unavailable"):
        await import_anki_package(
            plan_id,
            package,
            AnkiImportOptions(syllabus_unit_id="foreign-unit"),
            "foreign-unit",
        )
    with pytest.raises(AnkiImportRepositoryError, match="unavailable"):
        await import_anki_package(
            plan_id,
            package,
            AnkiImportOptions(syllabus_unit_id="stale-unit"),
            "stale-unit",
        )

    assert await _published_state(plan_id) == before
    archived_cards, archived_links, archived_receipts = await _published_state(archived_plan_id)
    assert archived_cards == []
    assert archived_links == []
    assert archived_receipts == []
