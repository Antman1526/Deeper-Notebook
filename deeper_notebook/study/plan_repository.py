"""Additive SurrealDB persistence for Study Workbench plans and syllabi.

The repository deliberately stores only plan-owned projections.  Existing source
records are linked by bounded string IDs and are never read, updated, or deleted
by this module; source readiness and authority belong to the established source
store/service.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, Literal

from loguru import logger
from surrealdb import RecordID  # type: ignore[import-untyped]

from deeper_notebook.database.repository import (
    ensure_record_id,
    repo_query,
)

from .plans import (
    StudyActivity,
    StudyPlan,
    StudyPlanPreferences,
    StudyPlanSourceLink,
    StudySyllabus,
    StudySyllabusUnit,
)


class StudyPlanRepositoryError(RuntimeError):
    """Safe persistence/domain error suitable for an API boundary."""


class StudyPlanNotFoundError(StudyPlanRepositoryError):
    """The requested plan identifier has no accessible plan projection."""


class StudyPlanConflictError(StudyPlanRepositoryError):
    """A validated optimistic or lifecycle guard rejected the mutation."""


_TRANSACTION_CONFLICT_MARKERS = (
    "study_plan_guard_failed",
    "study_plan_state_guard_failed",
    "study_plan_update_failed",
    "study_syllabus_guard_failed",
)


def _is_transaction_conflict(exc: BaseException) -> bool:
    """Recognize only repository-owned Surreal THROW markers as conflicts."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        # ``repo_query`` raises RuntimeError with the exact string returned by
        # Surreal THROW. Do not use substring matching: transport errors may
        # echo the submitted SQL, including every dormant THROW marker.
        message = str(current).strip()
        if message in _TRANSACTION_CONFLICT_MARKERS:
            return True
        current = current.__cause__ or current.__context__
    return False


_MAX_PAGE_SIZE = 500
_MAX_PAGE_OFFSET = 100_000
_PLAN_UPDATE_FIELDS = frozenset(
    {"goal", "starting_level", "target_date", "preferences"}
)
_PLAN_FIELDS = (
    "id",
    "schema_version",
    "plan_id",
    "goal",
    "starting_level",
    "target_date",
    "preferences",
    "source_links",
    "source_manifest_sha256",
    "active_syllabus_version",
    "state",
    "revision",
    "created_at",
    "updated_at",
)
_PLAN_PROJECTION = ", ".join(_PLAN_FIELDS)
_SYLLABUS_FIELDS = (
    "id",
    "schema_version",
    "plan_id",
    "version",
    "source_manifest_sha256",
    "approved_at",
)
_SYLLABUS_PROJECTION = ", ".join(_SYLLABUS_FIELDS)
_UNIT_FIELDS = (
    "schema_version",
    "plan_id",
    "syllabus_version",
    "unit_id",
    "position",
    "title",
    "objectives",
    "prerequisite_unit_ids",
    "estimated_minutes",
    "source_ids",
    "activities",
)
_UNIT_PROJECTION = ", ".join(_UNIT_FIELDS)


def _record_id(value: str | RecordID, table: str) -> RecordID:
    """Parse and table-bind a Surreal record ID before query parameter binding."""
    try:
        record = ensure_record_id(value)
    except Exception as exc:  # pragma: no cover - exact driver exception varies
        label = "study plan" if table == "study_plan" else table.replace("_", " ")
        error_type = StudyPlanNotFoundError if table == "study_plan" else StudyPlanRepositoryError
        raise error_type(f"invalid {label} ID") from exc
    rendered = str(record)
    if rendered.split(":", 1)[0] != table:
        label = "study plan" if table == "study_plan" else table.replace("_", " ")
        error_type = StudyPlanNotFoundError if table == "study_plan" else StudyPlanRepositoryError
        raise error_type(f"invalid {label} ID")
    return record


def _bounded_page(limit: int, offset: int) -> tuple[int, int]:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise StudyPlanRepositoryError("invalid pagination")
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise StudyPlanRepositoryError("invalid pagination")
    return min(max(limit, 1), _MAX_PAGE_SIZE), min(max(offset, 0), _MAX_PAGE_OFFSET)


def _expected_revision(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise StudyPlanRepositoryError("invalid expected revision")
    return value


def _flatten_dicts(value: object) -> list[dict[str, Any]]:
    """Collect record dictionaries from all common Surreal result shapes."""
    if isinstance(value, dict):
        # Some client versions return a statement envelope with ``result``.
        if "result" in value and len(value) <= 3:
            return _flatten_dicts(value.get("result"))
        return [value]
    if isinstance(value, (list, tuple)):
        records: list[dict[str, Any]] = []
        for item in value:
            records.extend(_flatten_dicts(item))
        return records
    return []


def _one_record(value: object, *, kind: str) -> dict[str, Any]:
    records = _flatten_dicts(value)
    if kind == "plan":
        candidates = [
            row
            for row in records
            if "revision" in row and ("goal" in row or "plan_id" in row)
        ]
    elif kind == "syllabus":
        candidates = [row for row in records if "version" in row and "plan_id" in row]
    elif kind == "link":
        candidates = [row for row in records if "source_id" in row and "plan_id" in row]
    else:
        candidates = records
    if len(candidates) != 1:
        raise StudyPlanRepositoryError(f"invalid persisted {kind} record")
    row = candidates[0]
    if "id" not in row and "plan_id" not in row:
        raise StudyPlanRepositoryError(f"invalid persisted {kind} record")
    return row


def _record_or_none(value: object, *, kind: str) -> dict[str, Any] | None:
    if not _flatten_dicts(value):
        return None
    return _one_record(value, kind=kind)


def _guard_plan_sql(
    expected_revision: int | None,
    *,
    expected_state: str | tuple[str, ...] | None = None,
) -> str:
    predicate = "id = $plan"
    if expected_revision is not None:
        predicate += " AND revision = $expected_revision"
    state_guard = ""
    if expected_state is not None:
        states = (expected_state,) if isinstance(expected_state, str) else expected_state
        checks = " AND ".join(f'$plan_guard.state != "{state}"' for state in states)
        state_guard = f'IF {checks} {{ THROW "study_plan_state_guard_failed"; }}; '
    return (
        "LET $plan_guard = (SELECT id, revision, state FROM $plan WHERE "
        f"{predicate})[0]; IF $plan_guard = NONE {{ "
        'THROW "study_plan_guard_failed"; }; '
        + state_guard
    )


def _as_datetime(value: object, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise StudyPlanRepositoryError(f"invalid persisted {field_name}") from exc
    else:
        raise StudyPlanRepositoryError(f"invalid persisted {field_name}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _source_ids(value: object) -> tuple[StudyPlanSourceLink, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise StudyPlanRepositoryError("invalid persisted source links")
    links: list[StudyPlanSourceLink] = []
    seen: set[str] = set()
    for item in value:
        source_id = item.get("source_id") if isinstance(item, dict) else item
        if not isinstance(source_id, str) or source_id in seen:
            raise StudyPlanRepositoryError("invalid persisted source links")
        seen.add(source_id)
        try:
            links.append(StudyPlanSourceLink(source_id=source_id))
        except Exception as exc:
            raise StudyPlanRepositoryError("invalid persisted source links") from exc
    return tuple(links)


def _plan_from_record(record: object) -> StudyPlan:
    """Decode only the public StudyPlan projection from a database row."""
    row = _one_record(record, kind="plan")
    raw_id = row.get("plan_id", row.get("id"))
    if isinstance(raw_id, RecordID):
        raw_id = str(raw_id)
    if not isinstance(raw_id, str):
        raise StudyPlanRepositoryError("invalid persisted study plan")
    created = row.get("created_at", row.get("created"))
    updated = row.get("updated_at", row.get("updated"))
    if created is None or updated is None:
        raise StudyPlanRepositoryError("invalid persisted study plan timestamps")
    source_links = _source_ids(row.get("source_links", []))
    target_date = row.get("target_date")
    if isinstance(target_date, str):
        try:
            target_date = date.fromisoformat(target_date)
        except ValueError as exc:
            raise StudyPlanRepositoryError("invalid persisted target_date") from exc
    values: dict[str, Any] = {
        "schema_version": row.get("schema_version", 1),
        "plan_id": raw_id,
        "goal": row.get("goal"),
        "starting_level": row.get("starting_level"),
        "target_date": target_date,
        "preferences": row.get("preferences"),
        "source_links": source_links,
        "source_manifest_sha256": row.get("source_manifest_sha256"),
        "approved_syllabus_version": row.get(
            "approved_syllabus_version", row.get("active_syllabus_version")
        ),
        "state": row.get("state", "draft"),
        "version": row.get("version", row.get("revision", 1)),
        "created_at": _as_datetime(created, "created_at"),
        "updated_at": _as_datetime(updated, "updated_at"),
    }
    try:
        return StudyPlan.model_validate(values)
    except Exception as exc:
        raise StudyPlanRepositoryError("invalid persisted study plan") from exc


def _syllabus_from_records(
    syllabus_record: object,
    unit_records: object,
    *,
    plan_id: str,
    version: int,
) -> StudySyllabus:
    """Decode one plan-bound syllabus and its bounded, ordered unit projection."""
    syllabus = _one_record(syllabus_record, kind="syllabus")
    raw_plan_id = syllabus.get("plan_id")
    if isinstance(raw_plan_id, RecordID):
        raw_plan_id = str(raw_plan_id)
    if raw_plan_id != plan_id or syllabus.get("version") != version:
        raise StudyPlanRepositoryError("invalid persisted study syllabus")

    rows = _flatten_dicts(unit_records)
    if len(rows) > 64:
        raise StudyPlanRepositoryError("invalid persisted study syllabus units")
    units: list[StudySyllabusUnit] = []
    for position, row in enumerate(rows):
        raw_unit_plan_id = row.get("plan_id")
        if isinstance(raw_unit_plan_id, RecordID):
            raw_unit_plan_id = str(raw_unit_plan_id)
        if (
            raw_unit_plan_id != plan_id
            or row.get("syllabus_version") != version
            or isinstance(row.get("position"), bool)
            or row.get("position") != position
        ):
            raise StudyPlanRepositoryError("invalid persisted study syllabus units")
        try:
            units.append(
                StudySyllabusUnit.model_validate(
                    {
                        field: row.get(field)
                        for field in (
                            "unit_id",
                            "title",
                            "objectives",
                            "prerequisite_unit_ids",
                            "estimated_minutes",
                            "source_ids",
                            "activities",
                        )
                    }
                )
            )
        except Exception as exc:
            raise StudyPlanRepositoryError("invalid persisted study syllabus units") from exc

    try:
        return StudySyllabus.model_validate(
            {
                "schema_version": syllabus.get("schema_version", 1),
                "plan_id": plan_id,
                "version": version,
                "source_manifest_sha256": syllabus.get("source_manifest_sha256"),
                "units": units,
                "approved_at": syllabus.get("approved_at"),
            }
        )
    except Exception as exc:
        raise StudyPlanRepositoryError("invalid persisted study syllabus") from exc


def _plan_data(plan: StudyPlan) -> dict[str, Any]:
    data = plan.model_dump(mode="python", exclude={"plan_id", "version", "approved_syllabus_version"})
    data["plan_id"] = plan.plan_id
    data["revision"] = plan.version
    data["active_syllabus_version"] = plan.approved_syllabus_version
    data["source_links"] = [link.source_id for link in plan.source_links]
    if isinstance(data.get("target_date"), date):
        data["target_date"] = data["target_date"].isoformat()
    return data


def _source_link_data(plan_id: str, source_id: str) -> dict[str, Any]:
    return {"plan_id": plan_id, "source_id": source_id, "created_at": datetime.now(UTC)}


def _stable_record_token(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:40]


def _syllabus_data(syllabus: StudySyllabus) -> dict[str, Any]:
    return {
        "schema_version": syllabus.schema_version,
        "plan_id": syllabus.plan_id,
        "version": syllabus.version,
        "source_manifest_sha256": syllabus.source_manifest_sha256,
        "approved_at": syllabus.approved_at,
        "created_at": datetime.now(UTC),
    }


def _unit_data(syllabus: StudySyllabus, unit: StudySyllabusUnit, position: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plan_id": syllabus.plan_id,
        "syllabus_version": syllabus.version,
        "unit_id": unit.unit_id,
        "position": position,
        "title": unit.title,
        "objectives": list(unit.objectives),
        "prerequisite_unit_ids": list(unit.prerequisite_unit_ids),
        "estimated_minutes": unit.estimated_minutes,
        "source_ids": list(unit.source_ids),
        "activities": [activity.model_dump(mode="python") for activity in unit.activities],
    }


class StudyPlanRepository:
    """Persist plan-owned records with bounded, optimistic mutations."""

    async def create(self, plan: StudyPlan) -> StudyPlan:
        try:
            plan_id = _record_id(plan.plan_id, "study_plan")
            rows = await repo_query(
                f"CREATE $plan CONTENT $data RETURN AFTER;",
                {"plan": plan_id, "data": _plan_data(plan)},
            )
            return _plan_from_record(_one_record(rows, kind="plan"))
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to create study plan")
            raise StudyPlanRepositoryError("Failed to create study plan") from exc

    async def get(self, plan_id: str) -> StudyPlan | None:
        try:
            record = _record_id(plan_id, "study_plan")
            rows = await repo_query(
                f"SELECT {_PLAN_PROJECTION} FROM $plan;",
                {"plan": record},
            )
            row = _record_or_none(rows, kind="plan")
            return _plan_from_record(row) if row is not None else None
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to load study plan")
            raise StudyPlanRepositoryError("Failed to load study plan") from exc

    async def get_syllabus(
        self,
        plan_id: str,
        *,
        version: int | None = None,
    ) -> StudySyllabus | None:
        """Read a projection-only exact or latest immutable syllabus snapshot."""
        try:
            plan = _record_id(plan_id, "study_plan")
            canonical_plan_id = str(plan)
            if version is not None:
                if isinstance(version, bool) or not isinstance(version, int) or version < 1:
                    raise StudyPlanRepositoryError("invalid syllabus version")
                syllabus_rows = await repo_query(
                    f"SELECT {_SYLLABUS_PROJECTION} FROM study_syllabus "
                    "WHERE plan_id = $plan_id AND version = $version LIMIT 1;",
                    {"plan_id": canonical_plan_id, "version": version},
                )
            else:
                syllabus_rows = await repo_query(
                    f"SELECT {_SYLLABUS_PROJECTION} FROM study_syllabus "
                    "WHERE plan_id = $plan_id ORDER BY version DESC LIMIT 1;",
                    {"plan_id": canonical_plan_id},
                )
            syllabus_row = _record_or_none(syllabus_rows, kind="syllabus")
            if syllabus_row is None:
                return None
            syllabus_version = syllabus_row.get("version")
            if isinstance(syllabus_version, bool) or not isinstance(syllabus_version, int):
                raise StudyPlanRepositoryError("invalid persisted study syllabus")
            unit_rows = await repo_query(
                f"SELECT {_UNIT_PROJECTION} FROM study_unit "
                "WHERE type::string(plan_id) = $plan_id AND syllabus_version = $version "
                "ORDER BY position ASC LIMIT 64;",
                {"plan_id": canonical_plan_id, "version": syllabus_version},
            )
            return _syllabus_from_records(
                syllabus_row,
                unit_rows,
                plan_id=canonical_plan_id,
                version=syllabus_version,
            )
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to load study syllabus")
            raise StudyPlanRepositoryError("Failed to load study syllabus") from exc

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[StudyPlan]:
        page_limit, page_offset = _bounded_page(limit, offset)
        try:
            rows = await repo_query(
                f"SELECT {_PLAN_PROJECTION} FROM study_plan "
                "ORDER BY updated_at DESC LIMIT $limit START $offset;",
                {"limit": page_limit, "offset": page_offset},
            )
            records = _flatten_dicts(rows)
            return [_plan_from_record(record) for record in records if "revision" in record]
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to list study plans")
            raise StudyPlanRepositoryError("Failed to list study plans") from exc

    async def update(
        self,
        plan_id: str,
        changes: Mapping[str, Any] | StudyPlan,
        *,
        expected_revision: int,
    ) -> StudyPlan:
        expected_revision = _expected_revision(expected_revision)
        if isinstance(changes, StudyPlan):
            raw_patch = _plan_data(changes)
            raw_patch = {key: raw_patch[key] for key in _PLAN_UPDATE_FIELDS if key in raw_patch}
        elif isinstance(changes, Mapping):
            unknown = set(changes) - _PLAN_UPDATE_FIELDS
            if unknown:
                raise StudyPlanRepositoryError("study plan update contains protected fields")
            raw_patch = dict(changes)
        else:
            raise StudyPlanRepositoryError("invalid study plan update")
        try:
            current = await self.get(plan_id)
            if current is None:
                raise StudyPlanNotFoundError("study plan not found")
            patch = dict(raw_patch)
            if "preferences" in patch:
                preferences = patch["preferences"]
                if preferences is not None and not isinstance(preferences, StudyPlanPreferences):
                    try:
                        preferences = StudyPlanPreferences.model_validate(preferences)
                    except Exception as exc:
                        raise StudyPlanRepositoryError("invalid study plan update") from exc
                patch["preferences"] = (
                    preferences.model_dump(mode="python") if preferences is not None else None
                )
            if isinstance(patch.get("target_date"), str):
                try:
                    patch["target_date"] = date.fromisoformat(patch["target_date"])
                except ValueError as exc:
                    raise StudyPlanRepositoryError("invalid study plan update") from exc
            # Construct the complete candidate before issuing any mutation. This
            # applies the same strict/immutable contract as create and prevents
            # malformed mappings from reaching SurrealDB.
            try:
                candidate = current.model_copy(update=patch)
            except Exception as exc:
                raise StudyPlanRepositoryError("invalid study plan update") from exc
            patch = {key: getattr(candidate, key) for key in _PLAN_UPDATE_FIELDS if key in patch}
            if isinstance(patch.get("preferences"), StudyPlanPreferences):
                patch["preferences"] = patch["preferences"].model_dump(mode="python")
            if isinstance(patch.get("target_date"), date):
                patch["target_date"] = patch["target_date"].isoformat()
            rows = await repo_query(
                "UPDATE $plan MERGE $patch SET revision = revision + 1, "
                "updated_at = time::now() WHERE revision = $expected_revision "
                "RETURN AFTER;",
                {
                    "plan": _record_id(plan_id, "study_plan"),
                    "patch": patch,
                    "expected_revision": expected_revision,
                },
            )
            row = _record_or_none(rows, kind="plan")
            if row is None:
                raise StudyPlanConflictError("study plan revision conflict")
            return _plan_from_record(row)
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to update study plan")
            raise StudyPlanRepositoryError("Failed to update study plan") from exc

    async def add_source(
        self,
        plan_id: str,
        source_id: str,
        *,
        expected_revision: int | None = None,
    ) -> StudyPlanSourceLink:
        try:
            plan_record = _record_id(plan_id, "study_plan")
            link = StudyPlanSourceLink(source_id=source_id)
            link_record = ensure_record_id(
                f"study_plan_source:{_stable_record_token(plan_id, link.source_id)}"
            )
            where_revision = " AND revision = $expected_revision" if expected_revision is not None else ""
            params: dict[str, Any] = {
                "plan": plan_record,
                "link": link_record,
                "link_data": _source_link_data(plan_id, link.source_id),
                "source_id": link.source_id,
            }
            if expected_revision is not None:
                params["expected_revision"] = _expected_revision(expected_revision)
            transaction = (
                "BEGIN TRANSACTION; "
                + _guard_plan_sql(expected_revision)
                + "CREATE $link CONTENT $link_data; "
                "LET $updated_plan = (UPDATE $plan SET source_links = "
                "array::distinct(array::append(source_links, $source_id)), "
                'state = IF state = "draft" THEN "analyzing_sources" ELSE state END, '
                "revision = revision + 1, updated_at = time::now() "
                f"WHERE id = $plan{where_revision} RETURN AFTER)[0]; "
                'IF $updated_plan = NONE { THROW "study_plan_update_failed"; }; '
                "COMMIT TRANSACTION; RETURN $updated_plan;"
            )
            await repo_query(transaction, params)
            updated = await self.get(plan_id)
            if updated is None or link.source_id not in {item.source_id for item in updated.source_links}:
                raise StudyPlanConflictError("study plan revision conflict")
            if expected_revision is not None and updated.version != expected_revision + 1:
                raise StudyPlanConflictError("study plan revision conflict")
            return link
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to add study source link")
            if _is_transaction_conflict(exc):
                raise StudyPlanConflictError("study plan revision conflict") from exc
            raise StudyPlanRepositoryError("Study source link already exists or plan is unavailable") from exc

    async def remove_source(
        self,
        plan_id: str,
        source_id: str,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        try:
            plan_record = _record_id(plan_id, "study_plan")
            link = StudyPlanSourceLink(source_id=source_id)
            params: dict[str, Any] = {
                "plan_id": plan_id,
                "plan": plan_record,
                "source_id": link.source_id,
            }
            if expected_revision is not None:
                expected_revision = _expected_revision(expected_revision)
                params["expected_revision"] = expected_revision
            where_revision = " AND revision = $expected_revision" if expected_revision is not None else ""
            before = await self.get(plan_id)
            if before is None:
                raise StudyPlanNotFoundError("study plan not found")
            await repo_query(
                "BEGIN TRANSACTION; "
                + _guard_plan_sql(expected_revision)
                + "LET $link_guard = (SELECT id FROM study_plan_source "
                "WHERE plan_id = $plan_id AND source_id = $source_id)[0]; "
                "IF $link_guard != NONE { "
                "DELETE study_plan_source WHERE plan_id = $plan_id AND source_id = $source_id; "
                "LET $updated_plan = (UPDATE $plan SET source_links = "
                "array::filter(source_links, |$value| $value != $source_id), "
                "revision = revision + 1, updated_at = time::now() "
                f"WHERE id = $plan{where_revision} RETURN AFTER)[0]; "
                'IF $updated_plan = NONE { THROW "study_plan_update_failed"; }; '
                "}; LET $removed = $link_guard != NONE; "
                "COMMIT TRANSACTION; RETURN { removed: $removed };",
                params,
            )
            after = await self.get(plan_id)
            if after is None:
                raise StudyPlanRepositoryError("invalid source link transaction receipt")
            before_had_link = link.source_id in {item.source_id for item in before.source_links}
            after_has_link = link.source_id in {item.source_id for item in after.source_links}
            if before_had_link and after_has_link:
                raise StudyPlanRepositoryError("invalid source link transaction receipt")
            return before_had_link
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to remove study source link")
            if _is_transaction_conflict(exc):
                raise StudyPlanConflictError("study plan revision conflict") from exc
            raise StudyPlanRepositoryError("Failed to remove study source link") from exc

    async def save_syllabus(
        self,
        syllabus: StudySyllabus,
        *,
        expected_revision: int,
        lifecycle_action: Literal["propose", "edit"] | None = None,
    ) -> StudySyllabus:
        try:
            _record_id(syllabus.plan_id, "study_plan")
            expected_revision = _expected_revision(expected_revision)
            if lifecycle_action not in {None, "propose", "edit"}:
                raise StudyPlanRepositoryError("invalid syllabus lifecycle action")
            syllabus_record = ensure_record_id(
                f"study_syllabus:{_stable_record_token(syllabus.plan_id, str(syllabus.version))}"
            )
            params: dict[str, Any] = {
                "syllabus": syllabus_record,
                "syllabus_data": _syllabus_data(syllabus),
                "plan": _record_id(syllabus.plan_id, "study_plan"),
                "plan_id": syllabus.plan_id,
                "expected_revision": expected_revision,
            }
            if lifecycle_action == "propose":
                guard = _guard_plan_sql(
                    expected_revision,
                    expected_state="analyzing_sources",
                )
                lifecycle_update = (
                    "LET $updated_plan = (UPDATE $plan SET "
                    'state = "syllabus_proposed", '
                    "revision = revision + 1, updated_at = time::now() "
                    "WHERE id = $plan AND revision = $expected_revision RETURN AFTER)[0]; "
                    'IF $updated_plan = NONE { THROW "study_plan_update_failed"; }; '
                )
            elif lifecycle_action == "edit":
                guard = _guard_plan_sql(
                    expected_revision,
                    expected_state=("syllabus_proposed", "editing"),
                )
                lifecycle_update = (
                    "LET $updated_plan = (UPDATE $plan SET "
                    'state = "editing", '
                    "revision = revision + 1, updated_at = time::now() "
                    "WHERE id = $plan AND revision = $expected_revision RETURN AFTER)[0]; "
                    'IF $updated_plan = NONE { THROW "study_plan_update_failed"; }; '
                )
            else:
                guard = _guard_plan_sql(expected_revision)
                lifecycle_update = ""
            statements = [
                "BEGIN TRANSACTION; ",
                guard,
                "CREATE $syllabus CONTENT $syllabus_data RETURN AFTER;",
            ]
            for index, unit in enumerate(syllabus.units):
                unit_record = ensure_record_id(
                    f"study_unit:{_stable_record_token(syllabus.plan_id, str(syllabus.version), unit.unit_id)}"
                )
                key = f"unit_{index}"
                data_key = f"unit_data_{index}"
                params[key] = unit_record
                params[data_key] = _unit_data(syllabus, unit, index)
                statements.append(f"CREATE ${key} CONTENT ${data_key} RETURN AFTER;")
            if lifecycle_update:
                statements.append(lifecycle_update)
            statements.append("COMMIT TRANSACTION; RETURN { saved: true };")
            await repo_query(" ".join(statements), params)
            persisted = await repo_query(
                "SELECT id, plan_id, version FROM $syllabus;", {"syllabus": syllabus_record}
            )
            if _record_or_none(persisted, kind="syllabus") is None:
                raise StudyPlanRepositoryError("invalid syllabus transaction receipt")
            # The immutable input is the complete validated projection.  Return
            # it rather than trusting a driver-specific transaction result shape.
            return syllabus
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to save study syllabus")
            if _is_transaction_conflict(exc):
                raise StudyPlanConflictError("study plan revision conflict") from exc
            raise StudyPlanRepositoryError("study syllabus version already exists or is unavailable") from exc

    async def approve_syllabus(
        self,
        plan_id: str,
        *,
        syllabus_version: int,
        expected_revision: int,
    ) -> StudyPlan:
        if isinstance(syllabus_version, bool) or not isinstance(syllabus_version, int) or syllabus_version < 1:
            raise StudyPlanRepositoryError("invalid syllabus version")
        expected_revision = _expected_revision(expected_revision)
        try:
            plan_record = _record_id(plan_id, "study_plan")
            syllabus_record = ensure_record_id(
                f"study_syllabus:{_stable_record_token(plan_id, str(syllabus_version))}"
            )
            await repo_query(
                "BEGIN TRANSACTION; "
                + _guard_plan_sql(expected_revision, expected_state="editing")
                + "LET $syllabus_guard = (SELECT id, plan_id, version, source_manifest_sha256 FROM $syllabus "
                "WHERE id = $syllabus AND plan_id = $plan_id AND version = $version)[0]; "
                'IF $syllabus_guard = NONE { THROW "study_syllabus_guard_failed"; }; '
                "UPDATE $syllabus SET approved_at = time::now() WHERE id = $syllabus; "
                "LET $updated_plan = (UPDATE $plan SET "
                'state = "approved", '
                "active_syllabus_version = $version, "
                "source_manifest_sha256 = $syllabus_guard.source_manifest_sha256, "
                "revision = revision + 1, updated_at = time::now() "
                "WHERE id = $plan AND revision = $expected_revision RETURN AFTER)[0]; "
                'IF $updated_plan = NONE { THROW "study_plan_update_failed"; }; '
                "COMMIT TRANSACTION; RETURN $updated_plan;",
                {
                    "syllabus": syllabus_record,
                    "plan": plan_record,
                    "plan_id": plan_id,
                    "version": syllabus_version,
                    "expected_revision": expected_revision,
                },
            )
            # SurrealDB returns the first statement's RETURN payload for some
            # client/server combinations (the syllabus row), even though the
            # plan UPDATE committed. Re-read the canonical plan projection so
            # transaction result ordering cannot authorize a stale response.
            approved = await self.get(plan_id)
            if (
                approved is None
                or approved.state != "approved"
                or approved.approved_syllabus_version != syllabus_version
                or approved.version != expected_revision + 1
            ):
                raise StudyPlanConflictError(
                    "study plan revision conflict or syllabus version not found"
                )
            return approved
        except StudyPlanRepositoryError:
            raise
        except Exception as exc:
            logger.exception("Failed to approve study syllabus")
            if _is_transaction_conflict(exc):
                raise StudyPlanConflictError(
                    "study plan revision conflict or syllabus version not found"
                ) from exc
            raise StudyPlanRepositoryError("Failed to approve study syllabus") from exc


__all__ = [
    "StudyPlanConflictError",
    "StudyPlanNotFoundError",
    "StudyPlanRepository",
    "StudyPlanRepositoryError",
]
