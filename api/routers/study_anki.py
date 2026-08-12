"""Feature-gated Anki portability endpoints and deterministic native export."""

from __future__ import annotations

import asyncio
import hashlib
import html
import inspect
import json
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import genanki
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from api.schemas.study_anki import (
    AnkiCompatibilityReceiptResponse,
    AnkiExportReceipt,
    AnkiExportRequest,
    AnkiExportResponse,
    AnkiHttpOptions,
    AnkiImportPreviewResponse,
    AnkiImportPublishRequest,
    AnkiImportPublishResponse,
    AnkiImportStatusResponse,
)
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.feature_flags import study_workbench_enabled
from deeper_notebook.study.anki_package import (
    AnkiImportOptions,
    AnkiPackageInspection,
    AnkiPackageRejected,
    inspect_anki_package,
)
from deeper_notebook.study.anki_repository import (
    AnkiCompatibilityReceipt,
    AnkiImportConflict,
    AnkiImportRepository,
    AnkiImportRepositoryError,
)
from deeper_notebook.study.plan_repository import (
    StudyPlanNotFoundError,
    StudyPlanRepository,
    StudyPlanRepositoryError,
)
from deeper_notebook.study.repository import StudyRepository

MAX_UPLOAD_BYTES: Final = 128 * 1024 * 1024
MAX_EXPORT_CARDS: Final = 10_000
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,127}:[a-f0-9]{32,64}$")
_DOWNLOAD_ID = re.compile(r"^anki_download:[a-f0-9]{64}$")
_PLAN_STATES = frozenset({"approved", "generating", "active", "completed"})


class AnkiHttpError(ValueError):
    """A stable, safe error for this HTTP boundary."""

    def __init__(self, code: str, status_code: int = 422):
        self.code = code
        self.status_code = status_code
        super().__init__(code)


@dataclass
class _ImportJob:
    job_id: str
    plan_id: str
    path: Path
    inspection: AnkiPackageInspection
    status: str = "preview_ready"
    receipt: AnkiCompatibilityReceipt | None = None
    publish_request_id: str | None = None
    publish_options_sha256: str | None = None


@dataclass
class AnkiExportResult:
    path: Path
    receipt: AnkiExportReceipt


@dataclass(frozen=True)
class AnkiExportInspection:
    stable_note_guids: tuple[str, ...]
    stable_model_ids: tuple[int, ...]
    stable_deck_ids: tuple[int, ...]
    note_fields: tuple[tuple[str, ...], ...]


_MAX_RETAINED_JOBS: Final = 256
_MAX_RETAINED_DOWNLOADS: Final = 256
_IMPORT_JOBS: OrderedDict[str, _ImportJob] = OrderedDict()
_DOWNLOADS: OrderedDict[str, Path] = OrderedDict()
_STATE_LOCK = asyncio.Lock()


def _export_root() -> Path:
    root = Path(os.getenv("DEEPER_NOTEBOOK_ANKI_EXPORT_ROOT", "data/study-anki/exports"))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def _import_root() -> Path:
    root = Path(os.getenv("DEEPER_NOTEBOOK_ANKI_IMPORT_ROOT", "data/study-anki/imports"))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def _require_study_workbench() -> None:
    # This dependency is intentionally attached to the whole router: FastAPI
    # evaluates it before multipart/body/query validation.
    if not study_workbench_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Study plan not found")


router = APIRouter(
    prefix="/study/plans",
    tags=["study-anki"],
    dependencies=[Depends(_require_study_workbench)],
)


def _safe_plan_id(value: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value or len(value) > 512:
        raise AnkiHttpError("invalid_plan_id")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise AnkiHttpError("invalid_plan_id")
    return value


def _parse_options(raw: str) -> tuple[AnkiHttpOptions, AnkiImportOptions]:
    try:
        decoded = json.loads(raw)
        http_options = AnkiHttpOptions.model_validate(decoded)
        return http_options, AnkiImportOptions.model_validate(http_options.model_dump(mode="python"))
    except Exception as exc:
        raise AnkiHttpError("invalid_options") from exc


def _options_sha256(options: AnkiImportOptions) -> str:
    encoded = json.dumps(options.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _http_receipt(receipt: AnkiCompatibilityReceipt) -> AnkiCompatibilityReceiptResponse:
    return AnkiCompatibilityReceiptResponse.model_validate(receipt.model_dump(mode="python"))


def _preview(job: _ImportJob) -> AnkiImportPreviewResponse:
    inspection = job.inspection
    return AnkiImportPreviewResponse(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        card_count=len(inspection.cards),
        transformed_count=inspection.transformed_count,
        skipped_count=inspection.skipped_count,
        rejected_count=inspection.skipped_count,
        package_sha256=inspection.package_sha256,
        collection_member=inspection.collection_member,
    )


async def _save_upload(upload: UploadFile) -> Path:
    filename = upload.filename or ""
    if not filename.lower().endswith(".apkg"):
        raise AnkiHttpError("invalid_package_type")
    root = _import_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    path = root / f"upload-{secrets.token_hex(32)}.apkg"
    total = 0
    try:
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise AnkiHttpError("upload_size_exceeded", 413)
                handle.write(chunk)
    except AnkiHttpError:
        path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise AnkiHttpError("upload_unavailable", 503) from exc
    if total == 0:
        path.unlink(missing_ok=True)
        raise AnkiHttpError("empty_upload")
    return path


def _package_error(exc: AnkiPackageRejected) -> AnkiHttpError:
    return AnkiHttpError(exc.code, 422)


def _validate_root_file(path: Path, root: Path) -> Path:
    try:
        root_resolved = root.resolve()
        candidate = path.resolve(strict=True)
        if candidate.parent != root_resolved or path.is_symlink() or not candidate.is_file():
            raise AnkiHttpError("download_not_found", 404)
        return candidate
    except AnkiHttpError:
        raise
    except OSError as exc:
        raise AnkiHttpError("download_not_found", 404) from exc


def _retain_job(job: _ImportJob) -> None:
    _IMPORT_JOBS[job.job_id] = job
    _IMPORT_JOBS.move_to_end(job.job_id)
    while len(_IMPORT_JOBS) > _MAX_RETAINED_JOBS:
        _old_id, old_job = _IMPORT_JOBS.popitem(last=False)
        old_job.path.unlink(missing_ok=True)


def _retain_download(download_id: str, path: Path) -> None:
    _DOWNLOADS[download_id] = path
    _DOWNLOADS.move_to_end(download_id)
    while len(_DOWNLOADS) > _MAX_RETAINED_DOWNLOADS:
        _old_id, old_path = _DOWNLOADS.popitem(last=False)
        old_path.unlink(missing_ok=True)


def _error_response(exc: AnkiHttpError) -> HTTPException:
    if exc.status_code == 503:
        return HTTPException(status_code=503, detail={"code": "study_anki_unavailable", "message": "Study Anki is unavailable"})
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": "Invalid Study Anki request" if exc.status_code == 422 else "Study Anki item not found"},
    )


async def _publish_import(
    plan_id: str,
    job: _ImportJob,
    options: AnkiImportOptions,
    request_id: str,
) -> AnkiCompatibilityReceipt:
    # Re-inspect the exact task-owned upload before native publication.  A
    # changed/replaced file is a conflict, never a different import.
    try:
        inspection = inspect_anki_package(job.path)
    except AnkiPackageRejected:
        raise
    if inspection.package_sha256 != job.inspection.package_sha256:
        raise AnkiImportConflict("Anki upload changed before publish")
    return await AnkiImportRepository().publish(plan_id, inspection, options, request_id)


@router.post("/{plan_id}/anki/import", response_model=AnkiImportPreviewResponse)
async def preview_anki_import(
    plan_id: str,
    file: UploadFile = File(...),
    options: str = Form(default="{}"),
) -> AnkiImportPreviewResponse:
    try:
        plan_id = _safe_plan_id(plan_id)
        _http_options, _import_options = _parse_options(options)
        path = await _save_upload(file)
        try:
            inspection = inspect_anki_package(path)
        except AnkiPackageRejected:
            path.unlink(missing_ok=True)
            raise
        job_id = f"anki_job:{secrets.token_hex(32)}"
        job = _ImportJob(job_id, plan_id, path, inspection)
        async with _STATE_LOCK:
            _retain_job(job)
        return _preview(job)
    except AnkiPackageRejected as exc:
        raise _error_response(_package_error(exc)) from None
    except AnkiHttpError as exc:
        raise _error_response(exc) from None
    finally:
        await file.close()


@router.get("/{plan_id}/anki/import/{job_id}", response_model=AnkiImportStatusResponse)
async def anki_import_status(plan_id: str, job_id: str) -> AnkiImportStatusResponse:
    try:
        plan_id = _safe_plan_id(plan_id)
        if not _ID.fullmatch(job_id):
            raise AnkiHttpError("job_not_found", 404)
        job = _IMPORT_JOBS.get(job_id)
        if job is None or job.plan_id != plan_id:
            raise AnkiHttpError("job_not_found", 404)
        base = _preview(job).model_dump(mode="python")
        return AnkiImportStatusResponse(**base, receipt_id=job.receipt.receipt_id if job.receipt else None)
    except AnkiHttpError as exc:
        raise _error_response(exc) from None


@router.post("/{plan_id}/anki/import/{job_id}:publish", response_model=AnkiImportPublishResponse)
async def publish_anki_import(plan_id: str, job_id: str, payload: AnkiImportPublishRequest) -> AnkiImportPublishResponse:
    try:
        plan_id = _safe_plan_id(plan_id)
        if not _ID.fullmatch(job_id):
            raise AnkiHttpError("job_not_found", 404)
        job = _IMPORT_JOBS.get(job_id)
        if job is None or job.plan_id != plan_id:
            raise AnkiHttpError("job_not_found", 404)
        if payload.upload_id != job_id:
            raise AnkiHttpError("upload_id_mismatch")
        options = AnkiImportOptions.model_validate(payload.options.model_dump(mode="python"))
        options_hash = _options_sha256(options)
        existing = job.receipt
        if existing is not None:
            if existing.request_id != payload.request_id or job.publish_options_sha256 != options_hash:
                raise AnkiHttpError("request_id_conflict", 409)
            return AnkiImportPublishResponse(status="replayed", receipt=_http_receipt(existing))
        try:
            receipt = await _publish_import(plan_id, job, options, payload.request_id)
        except AnkiPackageRejected as exc:
            raise _package_error(exc) from None
        except AnkiImportConflict as exc:
            raise AnkiHttpError("request_id_conflict", 409) from exc
        except AnkiImportRepositoryError as exc:
            raise AnkiHttpError("study_anki_unavailable", 503) from exc
        job.receipt = receipt
        job.status = "published"
        job.publish_request_id = payload.request_id
        job.publish_options_sha256 = options_hash
        job.path.unlink(missing_ok=True)
        return AnkiImportPublishResponse(status="published", receipt=_http_receipt(receipt))
    except AnkiHttpError as exc:
        raise _error_response(exc) from None


async def _load_export_plan(plan_id: str) -> dict[str, Any]:
    """Load only native card projections needed by the exporter."""
    plan = await StudyPlanRepository().get(plan_id)
    if plan is None:
        raise AnkiHttpError("plan_not_found", 404)
    if plan.state not in _PLAN_STATES or plan.approved_syllabus_version is None:
        raise AnkiHttpError("approved_plan_required", 409)
    rows = await repo_query(
        "SELECT card_id FROM study_plan_card WHERE plan_id = $plan_id LIMIT 10001",
        {"plan_id": plan.plan_id},
    )
    if len(rows) > MAX_EXPORT_CARDS:
        raise AnkiHttpError("card_limit_exceeded")
    cards: list[dict[str, Any]] = []
    repository = StudyRepository()
    for row in rows:
        if not isinstance(row, dict):
            raise AnkiHttpError("invalid_card_projection", 503)
        card_id = row.get("card_id")
        try:
            record = ensure_record_id(card_id)
        except Exception as exc:
            raise AnkiHttpError("invalid_card_projection", 503) from exc
        if getattr(record, "table_name", None) != "study_card" or not isinstance(getattr(record, "id", None), str):
            raise AnkiHttpError("invalid_card_projection", 503)
        try:
            card = await repository.get(str(record))
        except Exception as exc:
            raise AnkiHttpError("study_anki_unavailable", 503) from exc
        if card is None:
            continue
        persisted_kind = _persisted_card_kind(card.artifact_card_id)
        cards.append({
            "card_id": card.id or card.artifact_card_id,
            "version": card.version,
            "front": card.front,
            "back": card.back,
            "tags": ["study", "deeper-notebook"],
            "kind": persisted_kind if persisted_kind != "basic" else ("cloze" if "{{c" in card.front else "basic"),
        })
    # Re-read the plan after its card projection so a revision/state/syllabus
    # change during the bounded load cannot silently produce a stale package.
    latest = await StudyPlanRepository().get(plan_id)
    if latest is None or (
        latest.version != plan.version
        or latest.state != plan.state
        or latest.approved_syllabus_version != plan.approved_syllabus_version
    ):
        raise AnkiHttpError("plan_changed", 409)
    return {
        "plan_id": plan.plan_id,
        "plan_revision": plan.version,
        "state": plan.state,
        "approved_syllabus_version": plan.approved_syllabus_version,
        "goal": plan.goal,
        "cards": cards,
    }


def _stable_int(namespace: str, value: str) -> int:
    result = int(hashlib.sha256(f"{namespace}|{value}".encode()).hexdigest()[:15], 16)
    return max(result, 1)


def _bounded_card(card: object, index: int) -> dict[str, Any]:
    if hasattr(card, "model_dump"):
        card = card.model_dump(mode="python")
    if not isinstance(card, dict):
        raise AnkiHttpError("invalid_card_projection")
    card_id = card.get("card_id", card.get("id", card.get("artifact_card_id")))
    front = card.get("front")
    back = card.get("back")
    if not isinstance(card_id, str) or card_id != card_id.strip() or not card_id or len(card_id) > 512 or any(ord(char) < 32 or ord(char) == 127 for char in card_id):
        raise AnkiHttpError("invalid_card_projection")
    if not isinstance(front, str) or not 1 <= len(front) <= 8_000 or any(ord(char) == 0 or ord(char) == 127 for char in front):
        raise AnkiHttpError("invalid_card_projection")
    if not isinstance(back, str) or not 1 <= len(back) <= 16_000 or any(ord(char) == 0 or ord(char) == 127 for char in back):
        raise AnkiHttpError("invalid_card_projection")
    kind = card.get("kind", "cloze" if "{{c" in front else "basic")
    if kind not in {"basic", "reverse", "cloze"}:
        raise AnkiHttpError("invalid_card_projection")
    raw_version = card.get("version", 1)
    if isinstance(raw_version, bool) or not isinstance(raw_version, int) or not 1 <= raw_version <= 10_000:
        raise AnkiHttpError("invalid_card_projection")
    tags = card.get("tags", ())
    if not isinstance(tags, (list, tuple)) or len(tags) > 100:
        raise AnkiHttpError("invalid_card_projection")
    clean_tags_list: list[str] = []
    for tag in tags:
        if not isinstance(tag, str) or tag != tag.strip() or not tag or len(tag) > 64 or any(ord(char) < 33 or ord(char) == 127 for char in tag):
            raise AnkiHttpError("invalid_card_projection")
        clean_tags_list.append(tag)
    if len(set(clean_tags_list)) != len(clean_tags_list):
        raise AnkiHttpError("invalid_card_projection")
    return {"card_id": card_id, "version": raw_version, "front": front, "back": back, "kind": kind, "tags": tuple(sorted(clean_tags_list)), "index": index}


def _persisted_card_kind(artifact_card_id: object) -> str:
    """Recover only the finite kind marker emitted by Task 15 imports."""
    if not isinstance(artifact_card_id, str) or len(artifact_card_id) > 512:
        return "basic"
    prefix, separator, remainder = artifact_card_id.partition(":")
    if prefix != "anki_card" or not separator:
        return "basic"
    marker, marker_separator, _card_id = remainder.partition(":")
    return marker if marker_separator and marker in {"reverse", "cloze"} else "basic"


def _escape_field(value: str) -> str:
    # Native StudyCard content is plain source-grounded text.  Escape every
    # HTML character before passing to genanki; Cloze delimiters remain inert.
    return html.escape(value, quote=True)


_CLOZE_TOKEN = re.compile(r"\{\{c([1-9][0-9]{0,2})::(.*?)\}\}", re.DOTALL)


def _escape_cloze(value: str) -> str:
    pieces: list[str] = []
    cursor = 0
    for match in _CLOZE_TOKEN.finditer(value):
        pieces.append(_escape_field(value[cursor : match.start()]))
        pieces.append(f"{{{{c{match.group(1)}::{_escape_field(match.group(2))}}}}}")
        cursor = match.end()
    pieces.append(_escape_field(value[cursor:]))
    return "".join(pieces)


def _semantic_export_payload(plan: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plan_id": str(plan["plan_id"]),
        "plan_revision": int(plan.get("plan_revision", plan.get("version", 1))),
        "syllabus_version": int(plan.get("approved_syllabus_version", plan.get("active_syllabus_version", 1))),
        "cards": [
            {key: card[key] for key in ("card_id", "version", "front", "back", "kind", "tags")}
            for card in cards
        ],
    }


def _build_package(plan: dict[str, Any], cards: list[dict[str, Any]], destination: Path) -> tuple[tuple[str, ...], tuple[int, ...], tuple[int, ...]]:
    deck_id = _stable_int("deck", f"{plan['plan_id']}|{plan.get('approved_syllabus_version', 1)}")
    deck_name = f"Deeper Notebook - {str(plan.get('goal', 'Study Plan'))[:120]}"
    deck = genanki.Deck(deck_id, deck_name)
    basic_id = _stable_int("model", "deeper-notebook-basic")
    reverse_id = _stable_int("model", "deeper-notebook-reverse")
    cloze_id = _stable_int("model", "deeper-notebook-cloze")
    basic_model = genanki.Model(
        basic_id,
        "Deeper Notebook Basic",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
    )
    reverse_model = genanki.Model(
        reverse_id,
        "Deeper Notebook Basic + Reverse",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[
            {"name": "Forward", "qfmt": "{{Front}}", "afmt": "{{Back}}"},
            {"name": "Reverse", "qfmt": "{{Back}}", "afmt": "{{Front}}"},
        ],
    )
    cloze_model = genanki.Model(
        cloze_id,
        "Deeper Notebook Cloze",
        fields=[{"name": "Text"}, {"name": "Extra"}],
        templates=[{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<hr id=answer>{{Extra}}"}],
        model_type=genanki.Model.CLOZE,
    )
    note_guids: list[str] = []
    for card in cards:
        canonical = f"{plan['plan_id']}|{card['card_id']}|{card['version']}|1"
        guid = hashlib.sha256(canonical.encode()).hexdigest()[:32]
        note_guids.append(guid)
        model = {"basic": basic_model, "reverse": reverse_model, "cloze": cloze_model}[card["kind"]]
        if card["kind"] == "cloze":
            fields = [_escape_cloze(card["front"]), _escape_field(card["back"])]
        else:
            fields = [_escape_field(card["front"]), _escape_field(card["back"])]
        note = genanki.Note(model=model, fields=fields, tags=list(card["tags"]), guid=guid)
        deck.add_note(note)
    genanki.Package(deck).write_to_file(destination)
    return tuple(note_guids), tuple(sorted({basic_id, reverse_id, cloze_id})), (deck_id,)


def inspect_export(path: str | os.PathLike[str]) -> AnkiExportInspection:
    """Read stable semantic identity after native Task 15 validation."""
    package_path = Path(path)
    try:
        inspect_anki_package(package_path)
    except AnkiPackageRejected as exc:
        raise AnkiHttpError(f"invalid_export:{exc.code}") from exc
    with tempfile.TemporaryDirectory(prefix="dn-anki-export-read-") as temp_root:
        snapshot = Path(temp_root) / "package.apkg"
        shutil.copyfile(package_path, snapshot)
        os.chmod(snapshot, 0o600)
        package_path = snapshot
        with zipfile.ZipFile(package_path, "r") as archive:
            member = "collection.anki2" if "collection.anki2" in archive.namelist() else "collection.anki21"
            if member not in archive.namelist():
                raise AnkiHttpError("invalid_export")
            sqlite_path = Path(temp_root) / "collection.sqlite"
            sqlite_path.write_bytes(archive.read(member))
            with sqlite3.connect(f"file:{sqlite_path}?mode=ro&immutable=1", uri=True) as connection:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("PRAGMA trusted_schema=OFF")
                notes = connection.execute("SELECT guid, flds FROM notes ORDER BY id").fetchall()
                models_raw, decks_raw = connection.execute("SELECT models, decks FROM col").fetchone()
                models = json.loads(models_raw)
                decks = json.loads(decks_raw)
    return AnkiExportInspection(
        stable_note_guids=tuple(str(row[0]) for row in notes),
        stable_model_ids=tuple(sorted(int(value["id"]) for value in models.values())),
        stable_deck_ids=tuple(sorted(int(value["id"]) for value in decks.values())),
        note_fields=tuple(tuple(str(value) for value in row[1].split("\x1f")) for row in notes),
    )


def export_anki_package(plan: object, destination: str | os.PathLike[str]) -> AnkiExportResult:
    """Write one deterministic-semantic package from native Study card data."""
    if hasattr(plan, "model_dump"):
        plan = plan.model_dump(mode="python")
    if not isinstance(plan, dict):
        raise AnkiHttpError("invalid_plan_projection")
    if plan.get("state") not in _PLAN_STATES or plan.get("approved_syllabus_version") is None:
        raise AnkiHttpError("approved_plan_required", 409)
    raw_cards = plan.get("cards", ())
    if not isinstance(raw_cards, (list, tuple)) or not raw_cards or len(raw_cards) > MAX_EXPORT_CARDS:
        raise AnkiHttpError("invalid_card_projection")
    cards = [_bounded_card(card, index) for index, card in enumerate(raw_cards)]
    semantic = _semantic_export_payload(plan, cards)
    semantic_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output.parent, 0o700)
    with tempfile.TemporaryDirectory(prefix="dn-anki-export-") as temp_root:
        temp_path = Path(temp_root) / "package.apkg"
        os.chmod(temp_root, 0o700)
        note_guids, model_ids, deck_ids = _build_package(plan, cards, temp_path)
        # Validate the produced bytes before publication.  The native Task 15
        # inspector is intentionally the trust boundary; this output contains
        # no external/package-controlled paths or add-ons.
        try:
            inspect_anki_package(temp_path)
        except AnkiPackageRejected as exc:
            # genanki's fixed native indexes are safe but older Task 15 builds
            # may reject them as package input.  Keep this failure typed.
            raise AnkiHttpError(f"generated_package_invalid:{exc.code}") from exc
        staged = output.parent / f".{output.name}.{secrets.token_hex(8)}.tmp"
        shutil.copyfile(temp_path, staged)
        os.chmod(staged, 0o600)
        os.replace(staged, output)
    receipt_id = f"anki_export:{semantic_hash}"
    receipt = AnkiExportReceipt(
        receipt_id=receipt_id,
        plan_id=str(plan["plan_id"]),
        plan_revision=int(plan.get("plan_revision", plan.get("version", 1))),
        syllabus_version=int(plan["approved_syllabus_version"]),
        package_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        card_count=len(cards),
        stable_note_guids=note_guids,
        stable_model_ids=model_ids,
        stable_deck_ids=deck_ids,
        created_at=datetime.now(UTC),
    )
    return AnkiExportResult(path=output, receipt=receipt)


@router.post("/{plan_id}/anki/export", response_model=AnkiExportResponse)
async def export_study_plan_anki(plan_id: str, payload: AnkiExportRequest) -> AnkiExportResponse:
    try:
        plan_id = _safe_plan_id(plan_id)
        # A Study Plan is exported as one native deck. `deck_names` and
        # `syllabus_unit_id` are import selectors; the shared strict options
        # contract is validated, but those selectors do not filter exports.
        loaded = _load_export_plan(plan_id)
        plan = await loaded if inspect.isawaitable(loaded) else loaded
        result = export_anki_package(plan, _export_root() / f"export-{secrets.token_hex(32)}.apkg")
        download_id = f"anki_download:{secrets.token_hex(32)}"
        _retain_download(download_id, result.path)
        return AnkiExportResponse(download_id=download_id, receipt=result.receipt)
    except AnkiHttpError as exc:
        raise _error_response(exc) from None
    except AnkiPackageRejected as exc:
        raise _error_response(AnkiHttpError(f"generated_package_invalid:{exc.code}")) from None
    except Exception as exc:
        if isinstance(exc, (ValueError, TypeError)):
            raise _error_response(AnkiHttpError("invalid_export")) from None
        raise _error_response(AnkiHttpError("study_anki_unavailable", 503)) from exc


@router.get("/anki/download/{download_id}")
async def download_study_plan_anki(download_id: str) -> FileResponse:
    try:
        if not _DOWNLOAD_ID.fullmatch(download_id):
            raise AnkiHttpError("download_not_found", 404)
        path = _DOWNLOADS.get(download_id)
        if path is None:
            raise AnkiHttpError("download_not_found", 404)
        resolved = _validate_root_file(path, _export_root())
        if resolved.stat().st_size > MAX_UPLOAD_BYTES:
            raise AnkiHttpError("download_size_exceeded", 404)
        return FileResponse(
            resolved,
            media_type="application/zip",
            filename="study-plan.apkg",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": 'attachment; filename="study-plan.apkg"'},
        )
    except AnkiHttpError as exc:
        raise _error_response(exc) from None


__all__ = [
    "AnkiExportInspection",
    "AnkiExportResult",
    "AnkiHttpError",
    "export_anki_package",
    "inspect_export",
    "router",
]
