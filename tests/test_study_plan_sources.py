"""RED-to-GREEN coverage for Study Workbench source readiness and linking."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routers import study_plans
from api.schemas.study_plans import SourceLinkRequest
from deeper_notebook.study import source_service
from deeper_notebook.study.plans import StudyPlan, StudyPlanSourceLink

LINK = StudyPlanSourceLink(source_id="source:one")


def _projection(
    *,
    source_id: str = "source:one",
    title: str = "Lecture",
    kind: str = "upload",
    command: str | None = "command:one",
    has_text: bool = True,
    text_length: int = 256,
    fingerprint: str | None = None,
) -> dict[str, object]:
    return {
        "id": source_id,
        "title": title,
        "source_type": kind,
        "command": command,
        "has_text": has_text,
        "text_length": text_length,
        "fingerprint": fingerprint,
        "content_fingerprint": None,
        "source_fingerprint": None,
    }


@pytest.mark.asyncio
async def test_readiness_marks_missing_text_without_reading_or_copying_source(
    monkeypatch,
):
    """A source without extracted text is bounded as processing, not exposed."""

    get_source = AsyncMock(
        return_value=[
            _projection(
                title="Lecture",
                kind="upload",
                command="command:one",
                has_text=False,
                text_length=0,
            )
        ]
    )
    monkeypatch.setattr(source_service, "repo_query", get_source)

    receipt = await source_service.StudySourceService().readiness([LINK])

    assert receipt.ready is False
    assert receipt.items[0].source_id == "source:one"
    assert receipt.items[0].title == "Lecture"
    assert receipt.items[0].kind == "upload"
    assert receipt.items[0].reason == "processing"
    assert receipt.items[0].command_id == "command:one"
    assert receipt.items[0].fingerprint_status == "unknown"
    assert "full_text" not in receipt.items[0].model_dump()
    assert "file_path" not in receipt.items[0].model_dump()
    get_source.assert_awaited_once()


@pytest.mark.asyncio
async def test_readiness_deduplicates_links_and_exposes_only_bounded_projection(
    monkeypatch,
):
    get_source = AsyncMock(
        return_value=[
            _projection(
                kind="text",
                command=None,
                has_text=True,
                text_length=256,
                fingerprint="a" * 64,
            )
        ]
    )
    monkeypatch.setattr(source_service, "repo_query", get_source)

    receipt = await source_service.StudySourceService().readiness([LINK, LINK])

    assert receipt.ready is True
    assert len(receipt.items) == 1
    assert receipt.items[0].fingerprint_status == "available"
    assert set(receipt.items[0].model_dump()) == {
        "source_id",
        "title",
        "kind",
        "ready",
        "command_id",
        "fingerprint_status",
        "reason",
    }
    get_source.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_source_rejects_missing_source_before_linking(monkeypatch):
    monkeypatch.setattr(source_service, "repo_query", AsyncMock(return_value=[]))

    with pytest.raises(source_service.StudySourceNotFoundError):
        await source_service.StudySourceService().validate_source("source:missing")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_source_id",
    [
        "note:private",
        "notebook:private",
        "source:",
        "source:one:two",
        "not-a-record-id",
    ],
)
async def test_validate_source_rejects_non_source_ids_before_projection(
    monkeypatch, invalid_source_id
):
    query = AsyncMock(return_value=[_projection()])
    monkeypatch.setattr(source_service, "repo_query", query)

    with pytest.raises(source_service.StudySourceNotFoundError):
        await source_service.StudySourceService().validate_source(invalid_source_id)

    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_source_binds_a_canonical_source_record_id(monkeypatch):
    query = AsyncMock(return_value=[_projection()])
    monkeypatch.setattr(source_service, "repo_query", query)

    await source_service.StudySourceService().validate_source("source:lecture notes")

    bound_id = query.await_args.args[1]["source_id"]
    assert getattr(bound_id, "table_name", None) == "source"
    assert getattr(bound_id, "id", None) == "lecture notes"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requested_id", "expected_id"),
    [
        ("source:lecture notes", "source:⟨lecture notes⟩"),
        ("source:⟨lecture notes⟩", "source:⟨lecture notes⟩"),
    ],
)
async def test_validate_source_round_trips_driver_encoded_ids_without_double_encoding(
    monkeypatch, requested_id, expected_id
):
    query = AsyncMock(return_value=[_projection()])
    monkeypatch.setattr(source_service, "repo_query", query)

    await source_service.StudySourceService().validate_source(requested_id)

    bound_id = query.await_args.args[1]["source_id"]
    assert str(bound_id) == expected_id
    assert getattr(bound_id, "id", None) == "lecture notes"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_source_id",
    [
        "note:private",
        "notebook:private",
        "source:",
        "source:one:two",
        "not-a-record-id",
    ],
)
async def test_link_invalid_source_id_is_safe_source_404_without_projection_or_mutation(
    monkeypatch, invalid_source_id
):
    plan = _plan()
    query = AsyncMock(return_value=[_projection()])
    add_source = AsyncMock()

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(self, *args: object, **kwargs: object) -> object:
            return await add_source(*args, **kwargs)

    monkeypatch.setattr(study_plans, "_repository", Repository)
    monkeypatch.setattr(source_service, "repo_query", query)

    with pytest.raises(HTTPException) as raised:
        await study_plans.add_study_plan_source(
            "study_plan:one",
            SourceLinkRequest(source_id=invalid_source_id, expected_revision=1),
        )

    assert raised.value.status_code == 404
    query.assert_not_awaited()
    add_source.assert_not_awaited()


def _plan(*links: StudyPlanSourceLink) -> StudyPlan:
    from datetime import UTC, datetime

    now = datetime(2026, 8, 12, tzinfo=UTC)
    return StudyPlan(
        plan_id="study_plan:one",
        goal="Learn mechanics",
        starting_level="Beginner",
        source_links=links,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_link_validates_source_before_repository_mutation(monkeypatch):
    plan = _plan()
    add_source = AsyncMock()

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(self, *args: object, **kwargs: object) -> object:
            return await add_source(*args, **kwargs)

    monkeypatch.setattr(study_plans, "_repository", Repository)
    monkeypatch.setattr(source_service, "repo_query", AsyncMock(return_value=[]))

    with pytest.raises(HTTPException) as raised:
        await study_plans.add_study_plan_source(
            "study_plan:one",
            SourceLinkRequest(source_id="source:missing", expected_revision=1),
        )

    assert raised.value.status_code == 404
    add_source.assert_not_awaited()


@pytest.mark.asyncio
async def test_link_deduplicates_existing_source_without_revision_bump(monkeypatch):
    plan = _plan(LINK)
    add_source = AsyncMock()

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(self, *args: object, **kwargs: object) -> object:
            return await add_source(*args, **kwargs)

    monkeypatch.setattr(study_plans, "_repository", Repository)
    query = AsyncMock(return_value=[_projection(has_text=True, text_length=16)])
    monkeypatch.setattr(source_service, "repo_query", query)

    result = await study_plans.add_study_plan_source(
        "study_plan:one",
        SourceLinkRequest(source_id="source:one", expected_revision=1),
    )

    assert result.source_id == "source:one"
    add_source.assert_not_awaited()
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_link_rejects_invalid_source_before_repository_construction_even_for_stale_legacy_plan(
    monkeypatch,
):
    repository_calls = 0
    source_validation = AsyncMock()

    def forbidden_repository():
        nonlocal repository_calls
        repository_calls += 1
        raise AssertionError("invalid source must be rejected before repository access")

    monkeypatch.setattr(study_plans, "_repository", forbidden_repository)
    monkeypatch.setattr(
        study_plans.StudySourceService, "validate_source", source_validation
    )

    with pytest.raises(HTTPException) as raised:
        await study_plans.add_study_plan_source(
            "study_plan:one",
            SourceLinkRequest(source_id="note:private", expected_revision=99),
        )

    assert raised.value.status_code == 404
    assert repository_calls == 0
    source_validation.assert_not_awaited()


@pytest.mark.asyncio
async def test_link_persists_and_returns_one_canonical_encoded_source_id(monkeypatch):
    plan = _plan()
    captured: list[str] = []

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(
            self, plan_id: str, source_id: str, *, expected_revision: int
        ) -> StudyPlanSourceLink:
            captured.append(source_id)
            return StudyPlanSourceLink(source_id=source_id)

    monkeypatch.setattr(study_plans, "_repository", Repository)
    monkeypatch.setattr(study_plans.StudySourceService, "validate_source", AsyncMock())

    result = await study_plans.add_study_plan_source(
        "study_plan:one",
        SourceLinkRequest(source_id="source:lecture notes", expected_revision=1),
    )

    assert captured == ["source:⟨lecture notes⟩"]
    assert result.source_id == "source:⟨lecture notes⟩"


@pytest.mark.asyncio
async def test_encoded_duplicate_retry_is_idempotent_before_stale_revision_conflict(
    monkeypatch,
):
    plan = _plan(StudyPlanSourceLink(source_id="source:⟨lecture notes⟩"))
    repository_calls = AsyncMock()
    validate_source = AsyncMock(
        side_effect=AssertionError("duplicate retry should not read source")
    )

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(self, *args: object, **kwargs: object) -> object:
            return await repository_calls(*args, **kwargs)

    monkeypatch.setattr(study_plans, "_repository", Repository)
    monkeypatch.setattr(
        study_plans.StudySourceService, "validate_source", validate_source
    )

    result = await study_plans.add_study_plan_source(
        "study_plan:one",
        SourceLinkRequest(source_id="source:lecture notes", expected_revision=99),
    )

    assert result.source_id == "source:⟨lecture notes⟩"
    repository_calls.assert_not_awaited()
    validate_source.assert_not_awaited()


@pytest.mark.asyncio
async def test_source_readiness_uses_fixed_projection_without_materializing_source(
    monkeypatch,
):
    query = AsyncMock(return_value=[_projection(command=None, fingerprint="a" * 64)])
    monkeypatch.setattr(source_service, "repo_query", query)

    receipt = await source_service.StudySourceService().readiness([LINK])

    assert receipt.ready is True
    assert receipt.items[0].fingerprint_status == "available"
    statement = query.await_args.args[0]
    assert "SELECT *" not in statement.upper()
    assert " ASSET" not in statement.upper()
    assert "PROVENANCE.FINGERPRINT" in statement.upper()
    assert "PROVENANCE.CONTENT_FINGERPRINT" in statement.upper()
    assert "PROVENANCE.SOURCE_FINGERPRINT" in statement.upper()
    assert "full_text" in statement
    assert "has_text" in statement
    query.assert_awaited_once()


def test_source_projection_guards_optional_full_text_before_string_functions():
    """The Surreal 2.x projection must not call string functions on NONE."""

    statement = source_service.SOURCE_PROJECTION

    assert "type::is::string(full_text)" in statement
    assert (
        "IF type::is::string(full_text) THEN string::len(full_text) ELSE 0 END"
        in statement
    )
    assert (
        "IF type::is::string(full_text) THEN string::len(string::trim(full_text)) > 0 ELSE false END"
        in statement
    )


@pytest.mark.asyncio
async def test_readiness_keeps_valid_items_when_legacy_links_use_wrong_tables(
    monkeypatch,
):
    """Malformed legacy links become bounded missing items without a wrong-table query."""

    query = AsyncMock(
        return_value=[
            _projection(
                source_id="source:one",
                title="Valid source",
                kind="text",
                command=None,
                has_text=True,
                text_length=12,
            )
        ]
    )
    monkeypatch.setattr(source_service, "repo_query", query)
    links = (
        StudyPlanSourceLink(source_id="note:legacy"),
        LINK,
        StudyPlanSourceLink(source_id="not-a-record-id"),
        LINK,
    )

    receipt = await source_service.StudySourceService().readiness(links)

    assert receipt.ready is False
    assert [item.source_id for item in receipt.items] == [
        "note:legacy",
        "source:one",
        "not-a-record-id",
    ]
    assert [item.reason for item in receipt.items] == ["missing", "ready", "missing"]
    assert query.await_count == 1
    bound_id = query.await_args.args[1]["source_id"]
    assert getattr(bound_id, "table_name", None) == "source"
    assert getattr(bound_id, "id", None) == "one"


@pytest.mark.asyncio
async def test_readiness_treats_unescaped_bracketed_ids_as_missing_without_alias_query(
    monkeypatch,
):
    """Malformed bracket syntax must not alias to a different Source row."""

    query = AsyncMock(
        return_value=[
            _projection(
                source_id="source:one",
                title="Valid source",
                kind="text",
                command=None,
                has_text=True,
                text_length=12,
            )
        ]
    )
    monkeypatch.setattr(source_service, "repo_query", query)
    links = (
        StudyPlanSourceLink(source_id="source:⟨target⟩suffix⟩"),
        LINK,
    )

    receipt = await source_service.StudySourceService().readiness(links)

    assert [item.source_id for item in receipt.items] == [
        "source:⟨target⟩suffix⟩",
        "source:one",
    ]
    assert [item.reason for item in receipt.items] == ["missing", "ready"]
    query.assert_awaited_once()
    bound_id = query.await_args.args[1]["source_id"]
    assert str(bound_id) == "source:one"


def test_normalize_source_id_preserves_correctly_encoded_closing_bracket():
    normalized = source_service.normalize_source_id("source:⟨target\\⟩suffix⟩")

    assert normalized.canonical == "source:⟨target\\⟩suffix⟩"
    assert normalized.record.id == "target⟩suffix"


@pytest.mark.asyncio
async def test_source_projection_query_error_is_unavailable_without_exception_inspection(
    monkeypatch,
):
    query = AsyncMock(side_effect=RuntimeError("opaque driver failure"))
    monkeypatch.setattr(source_service, "repo_query", query)

    with pytest.raises(source_service.StudySourceUnavailableError):
        await source_service.StudySourceService().validate_source("source:one")


@pytest.mark.asyncio
async def test_source_projection_empty_result_is_not_found(monkeypatch):
    query = AsyncMock(return_value=[])
    monkeypatch.setattr(source_service, "repo_query", query)

    with pytest.raises(source_service.StudySourceNotFoundError):
        await source_service.StudySourceService().validate_source("source:missing")


@pytest.mark.asyncio
async def test_readiness_rejects_more_than_100_links_before_any_source_projection(
    monkeypatch,
):
    query = AsyncMock(return_value=[_projection()])
    monkeypatch.setattr(source_service, "repo_query", query)
    links = (StudyPlanSourceLink(source_id=f"source:{index}") for index in range(101))

    with pytest.raises(source_service.StudySourceInputLimitError):
        await source_service.StudySourceService().readiness(links)

    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_readiness_consumes_infinite_links_only_until_bounded_limit(monkeypatch):
    query = AsyncMock(return_value=[_projection()])
    monkeypatch.setattr(source_service, "repo_query", query)
    consumed = 0

    def infinite_links():
        nonlocal consumed
        index = 0
        while True:
            consumed += 1
            yield StudyPlanSourceLink(source_id=f"source:{index}")
            index += 1

    with pytest.raises(source_service.StudySourceInputLimitError):
        await source_service.StudySourceService().readiness(infinite_links())

    assert consumed == 101
    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_retry_is_idempotent_before_stale_revision_conflict(
    monkeypatch,
):
    plan = _plan(LINK)
    repository_calls = AsyncMock()

    class Repository:
        async def get(self, plan_id: str) -> StudyPlan:
            return plan

        async def add_source(self, *args: object, **kwargs: object) -> object:
            return await repository_calls(*args, **kwargs)

    validate_source = AsyncMock(
        side_effect=AssertionError("duplicate retry should not read source")
    )
    monkeypatch.setattr(study_plans, "_repository", Repository)
    monkeypatch.setattr(
        study_plans.StudySourceService, "validate_source", validate_source
    )

    result = await study_plans.add_study_plan_source(
        "study_plan:one",
        SourceLinkRequest(source_id="source:one", expected_revision=99),
    )

    assert result.source_id == "source:one"
    repository_calls.assert_not_awaited()
    validate_source.assert_not_awaited()
