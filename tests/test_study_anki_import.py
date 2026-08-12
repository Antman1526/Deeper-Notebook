from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path

import pytest

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
from tests.fixtures.anki.build_fixtures import build_apkg


def test_inspects_basic_reverse_and_cloze_without_publishing(tmp_path: Path) -> None:
    basic = inspect_anki_package(build_apkg(tmp_path / "basic.apkg"))
    reverse = inspect_anki_package(build_apkg(tmp_path / "reverse.apkg", kind="reverse"))
    cloze = inspect_anki_package(build_apkg(tmp_path / "cloze.apkg", kind="cloze"))

    assert [(card.kind, card.front) for card in basic.cards] == [
        ("basic", "What is inertia?")
    ]
    assert [card.kind for card in reverse.cards] == ["basic", "reverse"]
    assert cloze.cards[0].kind == "cloze"
    assert "[…]" in cloze.cards[0].front
    assert cloze.cards[0].back.startswith("What is inertia?")
    assert all(card.deck_name == "Mechanics" for card in (*basic.cards, *reverse.cards, *cloze.cards))
    assert basic.cards[0].tags == ("mechanics", "physics")


@pytest.mark.parametrize("collection_member", ["collection.anki2", "collection.anki21"])
def test_supported_collection_variants_are_inspected(
    tmp_path: Path, collection_member: str
) -> None:
    inspection = inspect_anki_package(
        build_apkg(
            tmp_path / f"{collection_member}.apkg",
            collection_member=collection_member,
        )
    )

    assert inspection.collection_member == collection_member
    assert len(inspection.cards) == 1


def test_media_is_mapped_to_bounded_placeholders(tmp_path: Path) -> None:
    package = build_apkg(
        tmp_path / "media.apkg",
        front='<img src="diagram.png"> Name the diagram',
        back='Listen [sound:answer.mp3]',
        media={"diagram.png": b"png", "answer.mp3": b"mp3"},
    )
    inspection = inspect_anki_package(package)

    assert inspection.media_names == ("answer.mp3", "diagram.png")
    assert inspection.cards[0].media_names == ("answer.mp3", "diagram.png")
    assert "[media:diagram.png]" in inspection.cards[0].front
    assert "[media:answer.mp3]" in inspection.cards[0].back


def test_cloze_allows_an_empty_optional_extra_field(tmp_path: Path) -> None:
    inspection = inspect_anki_package(
        build_apkg(tmp_path / "cloze-empty-extra.apkg", kind="cloze", back="")
    )

    assert inspection.cards[0].kind == "cloze"
    assert inspection.cards[0].back == "What is inertia?"


@pytest.mark.parametrize(
    ("member", "code"),
    [
        ("../outside", "unsafe_member_path"),
        ("/absolute", "unsafe_member_path"),
        ("C:/drive", "unsafe_member_path"),
        ("folder\\file", "unsafe_member_path"),
        ("unknown.bin", "unexpected_member"),
    ],
)
def test_archive_members_are_rejected_before_sqlite_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, member: str, code: str
) -> None:
    package = build_apkg(tmp_path / "unsafe.apkg", extra_members=[(member, b"x")])
    opened = False

    def forbidden_connect(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("SQLite must not open")

    monkeypatch.setattr(sqlite3, "connect", forbidden_connect)
    with pytest.raises(AnkiPackageRejected, match=code):
        inspect_anki_package(package)
    assert opened is False


def test_duplicate_and_symlink_members_are_rejected(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.apkg"
    with zipfile.ZipFile(duplicate, "w") as archive:
        archive.writestr("collection.anki2", b"one")
        with pytest.warns(UserWarning):
            archive.writestr("collection.anki2", b"two")
        archive.writestr("media", b"{}")
    with pytest.raises(AnkiPackageRejected, match="duplicate_member"):
        inspect_anki_package(duplicate)

    symlink = zipfile.ZipInfo("0")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    package = build_apkg(
        tmp_path / "symlink.apkg",
        media_manifest={"0": "asset.png"},
        extra_members=[(symlink, b"/etc/passwd")],
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_member_type"):
        inspect_anki_package(package)


def test_archive_budgets_reject_ratio_and_member_count(tmp_path: Path) -> None:
    bomb = build_apkg(
        tmp_path / "bomb.apkg",
        extra_members=[("0", b"0" * (3 * 1024 * 1024))],
        media_manifest={"0": "asset.bin"},
    )
    with pytest.raises(AnkiPackageRejected, match="compression_ratio_exceeded"):
        inspect_anki_package(bomb)

    crowded = build_apkg(
        tmp_path / "crowded.apkg",
        extra_members=[(str(index), b"x") for index in range(513)],
        media_manifest={str(index): f"asset-{index}.bin" for index in range(513)},
    )
    with pytest.raises(AnkiPackageRejected, match="member_count_exceeded"):
        inspect_anki_package(crowded)


def test_archive_rejects_overlong_and_control_character_names(tmp_path: Path) -> None:
    overlong = build_apkg(
        tmp_path / "overlong.apkg",
        extra_members=[("x" * 4097, b"x")],
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_member_path"):
        inspect_anki_package(overlong)

    control = build_apkg(
        tmp_path / "control.apkg",
        extra_members=[("bad\x1fname", b"x")],
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_member_path"):
        inspect_anki_package(control)


@pytest.mark.parametrize("variant", ["collection.anki21b", "collection.anki99"])
def test_unknown_or_ambiguous_collection_variant_is_rejected(tmp_path: Path, variant: str) -> None:
    package = build_apkg(tmp_path / "unknown.apkg", collection_member=variant)
    with pytest.raises(AnkiPackageRejected, match="unsupported_collection"):
        inspect_anki_package(package)

    ambiguous = build_apkg(
        tmp_path / "ambiguous.apkg", extra_members=[("collection.anki21", b"also")]
    )
    with pytest.raises(AnkiPackageRejected, match="ambiguous_collection"):
        inspect_anki_package(ambiguous)


@pytest.mark.parametrize(
    "manifest",
    [None, [], {"../outside": "asset.png"}, {"0": "../outside"}, {"0": "/etc/passwd"}],
)
def test_invalid_media_manifest_and_external_paths_are_rejected(
    tmp_path: Path, manifest: object
) -> None:
    package = build_apkg(
        tmp_path / "media-invalid.apkg",
        media={"asset.png": b"x"},
        media_manifest=manifest if manifest is not None else "not-json-object",
    )
    with pytest.raises(AnkiPackageRejected, match="invalid_media"):
        inspect_anki_package(package)


def test_published_local_file_class_cannot_read_external_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = tmp_path / "private.txt"
    sentinel.write_text("must never be read")
    package = build_apkg(
        tmp_path / "external.apkg",
        media={str(sentinel): b"archive bytes"},
    )
    original = Path.read_bytes

    def guarded_read(path: Path) -> bytes:
        if path == sentinel:
            raise AssertionError("external file was read")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    with pytest.raises(AnkiPackageRejected, match="invalid_media_filename"):
        inspect_anki_package(package)


def test_inspection_uses_one_task_owned_archive_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "snapshot.apkg")
    real_zip_file = zipfile.ZipFile
    opened_paths: list[Path] = []

    def recording_zip_file(file, *args, **kwargs):
        opened_paths.append(Path(file))
        return real_zip_file(file, *args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", recording_zip_file)
    inspect_anki_package(package)

    assert len(opened_paths) == 1
    assert opened_paths[0] != package
    assert opened_paths[0].name == "package.apkg"


def test_sqlite_header_schema_and_active_templates_are_rejected(tmp_path: Path) -> None:
    invalid = build_apkg(tmp_path / "not-sqlite.apkg", raw_collection=b"not sqlite")
    with pytest.raises(AnkiPackageRejected, match="invalid_sqlite_header"):
        inspect_anki_package(invalid)

    hostile = build_apkg(
        tmp_path / "hostile.apkg", hostile_template='<script src="file:///etc/passwd"></script>{{Front}}'
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_template"):
        inspect_anki_package(hostile)

    unsupported_markup = build_apkg(
        tmp_path / "template-form.apkg",
        hostile_template="<form>{{Front}}</form>",
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_template"):
        inspect_anki_package(unsupported_markup)

    trigger = build_apkg(
        tmp_path / "trigger.apkg",
        extra_sql="CREATE TRIGGER hostile AFTER INSERT ON notes BEGIN DELETE FROM cards; END;",
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_sqlite_schema"):
        inspect_anki_package(trigger)

    extra_table = build_apkg(
        tmp_path / "extra-table.apkg",
        extra_sql="CREATE TABLE addon_payload (code blob);",
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_sqlite_schema"):
        inspect_anki_package(extra_table)

    extra_column = build_apkg(
        tmp_path / "extra-column.apkg",
        extra_sql="ALTER TABLE notes ADD COLUMN addon_payload blob;",
    )
    with pytest.raises(AnkiPackageRejected, match="unsupported_sqlite_schema"):
        inspect_anki_package(extra_column)

    overflow = build_apkg(
        tmp_path / "overflow-schema.apkg",
        note_unique_constraints=101,
        extra_sql="CREATE TRIGGER zzz_hostile AFTER INSERT ON notes BEGIN DELETE FROM cards; END;",
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_sqlite_schema"):
        inspect_anki_package(overflow)


def test_fields_and_imported_scheduling_are_bounded_and_inert(tmp_path: Path) -> None:
    remote_reference = build_apkg(
        tmp_path / "remote.apkg",
        front='<img src="https://example.invalid/tracker.png">',
    )
    with pytest.raises(AnkiPackageRejected, match="unsafe_field"):
        inspect_anki_package(remote_reference)

    oversized = build_apkg(
        tmp_path / "oversized.apkg",
        front="x" * (64 * 1024 + 1),
    )
    with pytest.raises(AnkiPackageRejected, match="field_size_exceeded"):
        inspect_anki_package(oversized)

    invalid_schedule = build_apkg(
        tmp_path / "invalid-schedule.apkg",
        extra_sql="UPDATE cards SET due = 'not-an-integer', ivl = -999999999;",
    )
    with pytest.raises(AnkiPackageRejected, match="invalid_scheduling"):
        inspect_anki_package(invalid_schedule)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"models_override": {"not-an-id": {"id": "not-an-id"}}}, "invalid_models"),
        ({"decks_override": {"1e3": {"id": "1e3", "name": "Deck"}}}, "invalid_decks"),
        (
            {
                "models_override": {
                    "1": {
                        "id": 1,
                        "name": "Basic",
                        "type": 0,
                        "flds": [
                            {"name": "Front", "ord": 0},
                            {"name": "Back", "ord": 0},
                        ],
                        "tmpls": [
                            {
                                "ord": 0,
                                "qfmt": "{{Front}}",
                                "afmt": "{{Back}}",
                            }
                        ],
                        "css": "",
                    }
                }
            },
            "unsupported_model",
        ),
    ],
)
def test_malformed_model_and_deck_metadata_use_safe_rejections(
    tmp_path: Path, overrides: dict[str, object], code: str
) -> None:
    package = build_apkg(tmp_path / f"{code}.apkg", **overrides)

    with pytest.raises(AnkiPackageRejected, match=code):
        inspect_anki_package(package)


def test_sqlite_is_opened_immutable_query_only_and_trusted_schema_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "readonly.apkg")
    real_connect = sqlite3.connect
    seen_uri = ""
    pragmas: list[str] = []

    class CursorProxy:
        def __init__(self, cursor):
            self.cursor = cursor

        def execute(self, sql, parameters=()):
            pragmas.append(sql)
            return self.cursor.execute(sql, parameters)

        def __iter__(self):
            return iter(self.cursor)

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    class ConnectionProxy:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, parameters=()):
            pragmas.append(sql)
            return self.connection.execute(sql, parameters)

        def cursor(self):
            return CursorProxy(self.connection.cursor())

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.connection.close()

    def recording_connect(database, *args, **kwargs):
        nonlocal seen_uri
        seen_uri = str(database)
        return ConnectionProxy(real_connect(database, *args, **kwargs))

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    inspect_anki_package(package)
    assert "mode=ro" in seen_uri and "immutable=1" in seen_uri
    assert any("query_only=ON" in sql for sql in pragmas)
    assert any("trusted_schema=OFF" in sql for sql in pragmas)


def test_import_is_explicit_atomic_and_replay_compares_full_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "publish.apkg", kind="reverse")
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_query(query: str, params: dict[str, object]):
        calls.append((query, params))
        if query.startswith("SELECT"):
            return []
        return [{"result": params["receipt"]}]

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", fake_query)
    receipt = asyncio.run(
        import_anki_package(
            "study_plan:one", package, AnkiImportOptions(), "anki-request-one"
        )
    )
    assert receipt.card_count == 2
    mutation, mutation_params = next(
        (query, params) for query, params in calls if "BEGIN TRANSACTION" in query
    )
    assert "CREATE $card_record_0" in mutation and "study_plan_card" in mutation
    assert str(mutation_params["card_record_0"]).startswith("study_card:")
    assert "CREATE $receipt_record" in mutation
    assert str(mutation_params["receipt_record"]).startswith("study_anki_import:")
    assert "state IN ['approved', 'generating', 'active', 'completed']" in mutation
    assert "active_syllabus_version != NONE" in mutation
    assert "COMMIT TRANSACTION" in mutation
    assert "extract" not in mutation.lower()

    repository = AnkiImportRepository()
    existing = receipt

    async def replay_query(query: str, params: dict[str, object]):
        if query.startswith("SELECT"):
            return [existing.model_dump(mode="python") | {"id": "study_anki_import:one"}]
        raise AssertionError("replay must not mutate")

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", replay_query)
    assert asyncio.run(
        repository.publish("study_plan:one", inspect_anki_package(package), AnkiImportOptions(), "anki-request-one")
    ).payload_sha256 == receipt.payload_sha256

    changed = AnkiImportOptions(syllabus_unit_id="unit-two")
    with pytest.raises(AnkiImportConflict):
        asyncio.run(repository.publish("study_plan:one", inspect_anki_package(package), changed, "anki-request-one"))

    changed_inspection = inspect_anki_package(package).model_copy(
        update={"skipped_count": 1}
    )
    with pytest.raises(AnkiImportConflict):
        asyncio.run(
            repository.publish(
                "study_plan:one",
                changed_inspection,
                AnkiImportOptions(),
                "anki-request-one",
            )
        )


def test_import_rejects_one_invalid_card_before_repository_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "invalid-card.apkg", back="<iframe src='x'></iframe>")
    called = False

    async def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("repository mutation must not run")

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", forbidden)
    with pytest.raises(AnkiPackageRejected, match="unsafe_field"):
        asyncio.run(import_anki_package("study_plan:one", package, AnkiImportOptions(), "bad"))
    assert called is False


def test_syllabus_unit_authority_is_bound_inside_the_import_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "unit-bound.apkg")
    mutations: list[tuple[str, dict[str, object]]] = []

    async def fake_query(query: str, params: dict[str, object]):
        if query.startswith("SELECT"):
            return []
        mutations.append((query, params))
        return [{"result": params["receipt"]}]

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", fake_query)
    asyncio.run(
        import_anki_package(
            "study_plan:one",
            package,
            AnkiImportOptions(syllabus_unit_id="unit-one"),
            "unit-bound",
        )
    )

    query, params = mutations[0]
    assert "syllabus_version = $plan_guard" in query
    assert "unit_id = $syllabus_unit_id" in query
    assert "IF array::len($unit_guard) != 1" in query
    assert params["syllabus_unit_id"] == "unit-one"


def test_import_rejects_wrong_table_plan_id_before_any_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = build_apkg(tmp_path / "wrong-plan.apkg")
    called = False

    async def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", forbidden)
    with pytest.raises(AnkiImportRepositoryError, match="Invalid Study Plan ID"):
        asyncio.run(
            import_anki_package(
                "source:not-a-plan", package, AnkiImportOptions(), "wrong-plan"
            )
        )
    assert called is False


@pytest.mark.parametrize(
    ("plan_id", "request_id", "message"),
    [
        (" study_plan:one", "request", "Invalid Study Plan ID"),
        ("study_plan:one", " request", "Invalid Anki import request ID"),
        ("study_plan:one", "request\x1f", "Invalid Anki import request ID"),
    ],
)
def test_import_rejects_ambiguous_authority_tokens_before_any_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plan_id: str,
    request_id: str,
    message: str,
) -> None:
    package = build_apkg(tmp_path / "ambiguous-authority.apkg")
    called = False

    async def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", forbidden)
    with pytest.raises(AnkiImportRepositoryError, match=message):
        asyncio.run(
            import_anki_package(
                plan_id, package, AnkiImportOptions(), request_id
            )
        )
    assert called is False


def test_import_revalidates_unchecked_contract_copies_before_any_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inspection = inspect_anki_package(build_apkg(tmp_path / "unchecked.apkg"))
    invalid_options = AnkiImportOptions().model_copy(
        update={"deck_names": ("",)}
    )
    invalid_inspection = inspection.model_copy(
        update={"package_sha256": "not-a-sha"}
    )
    called = False

    async def forbidden(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("deeper_notebook.study.anki_repository.repo_query", forbidden)
    repository = AnkiImportRepository()
    with pytest.raises(AnkiImportRepositoryError, match="Invalid Anki import payload"):
        asyncio.run(
            repository.publish(
                "study_plan:one", inspection, invalid_options, "unchecked-options"
            )
        )
    with pytest.raises(AnkiImportRepositoryError, match="Invalid Anki import payload"):
        asyncio.run(
            repository.publish(
                "study_plan:one",
                invalid_inspection,
                AnkiImportOptions(),
                "unchecked-inspection",
            )
        )
    assert called is False


def test_migration_44_is_additive_bounded_and_symmetric() -> None:
    root = Path(__file__).resolve().parents[1]
    up = (root / "deeper_notebook/database/migrations/44.surrealql").read_text()
    down = (root / "deeper_notebook/database/migrations/44_down.surrealql").read_text()
    assert "DEFINE TABLE IF NOT EXISTS study_anki_import SCHEMAFULL" in up
    assert "idx_study_anki_import_request" in up
    assert "idx_study_anki_import_payload" in up
    assert "array::len($value) <= 10000" in up
    assert down.strip() == "REMOVE TABLE IF EXISTS study_anki_import;"
