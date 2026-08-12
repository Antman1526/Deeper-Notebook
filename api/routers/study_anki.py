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
from deeper_notebook.config import DATA_FOLDER
from deeper_notebook.database.repository import ensure_record_id, repo_query
from deeper_notebook.feature_flags import study_workbench_enabled
from deeper_notebook.study.anki_jobs import (
    EXPORT_TTL,
    JOB_TTL,
    AnkiExportMetadata,
    AnkiExportRepository,
    AnkiJobMetadata,
    AnkiJobRepository,
)
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
    metadata: AnkiJobMetadata | None = None


@dataclass
class AnkiExportResult:
    path: Path
    receipt: AnkiExportReceipt


@dataclass(frozen=True)
class AnkiExportInspection:
    card_count: int
    stable_note_guids: tuple[str, ...]
    stable_model_ids: tuple[int, ...]
    stable_deck_ids: tuple[int, ...]
    note_fields: tuple[tuple[str, ...], ...]


_MAX_RETAINED_JOBS: Final = 256
_MAX_RETAINED_DOWNLOADS: Final = 256
_IMPORT_JOBS: OrderedDict[str, _ImportJob] = OrderedDict()
_DOWNLOADS: OrderedDict[str, Path] = OrderedDict()
_STATE_LOCK = asyncio.Lock()


def _canonical_data_root() -> Path:
    """Resolve the launcher-provided absolute application data root.

    Development's ``./data`` fallback is made absolute here, but callers can
    never override the Anki subroots with an arbitrary path or symlink.
    """
    configured = Path(DATA_FOLDER).expanduser()
    try:
        absolute = configured if configured.is_absolute() else Path.cwd() / configured
        resolved = absolute.resolve(strict=False)
        if resolved == Path(resolved.anchor) or absolute != resolved:
            raise AnkiHttpError("storage_unavailable", 503)
        resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(resolved, 0o700)
        stat_result = resolved.stat()
        if not resolved.is_dir() or hasattr(os, "getuid") and stat_result.st_uid != os.getuid():
            raise AnkiHttpError("storage_unavailable", 503)
    except AnkiHttpError:
        raise
    except (OSError, ValueError) as exc:
        raise AnkiHttpError("storage_unavailable", 503) from exc
    return resolved


def _owned_subroot(name: str) -> Path:
    root = _canonical_data_root() / "study-anki"
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        if root.is_symlink() or root.resolve() != root:
            raise AnkiHttpError("storage_unavailable", 503)
        child = root / name
        child.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(child, 0o700)
        if child.is_symlink() or child.resolve() != child or not child.is_relative_to(root):
            raise AnkiHttpError("storage_unavailable", 503)
        return child
    except AnkiHttpError:
        raise
    except OSError as exc:
        raise AnkiHttpError("storage_unavailable", 503) from exc


def _export_root() -> Path:
    return _owned_subroot("exports")


def _import_root() -> Path:
    return _owned_subroot("imports")


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


def _assert_replay_authority(
    receipt: AnkiCompatibilityReceipt,
    metadata: AnkiJobMetadata,
    request_id: str,
    options_sha256: str,
) -> None:
    """Bind a replay receipt to the exact durable job claim.

    Request IDs are plan-scoped idempotency keys, not package authority.  A
    receipt found by request ID is usable only when the current job's package,
    claim package, request, and options all agree with it.
    """
    if (
        receipt.request_id != request_id
        or metadata.claim_request_id != request_id
        or metadata.claim_options_sha256 != options_sha256
        or metadata.package_sha256 != receipt.package_sha256
        or metadata.claim_package_sha256 != metadata.package_sha256
        or receipt.package_sha256 != metadata.claim_package_sha256
    ):
        raise AnkiHttpError("request_id_conflict", 409)


def _http_receipt(receipt: AnkiCompatibilityReceipt) -> AnkiCompatibilityReceiptResponse:
    return AnkiCompatibilityReceiptResponse.model_validate(receipt.model_dump(mode="python"))


def _preview(job: _ImportJob, metadata: AnkiJobMetadata | None = None) -> AnkiImportPreviewResponse:
    inspection = job.inspection
    if metadata is not None:
        return AnkiImportPreviewResponse(
            job_id=metadata.job_id,
            status=metadata.status,
            card_count=metadata.card_count,
            transformed_count=metadata.transformed_count,
            skipped_count=metadata.skipped_count,
            rejected_count=metadata.rejected_count,
            package_sha256=metadata.package_sha256,
            collection_member=metadata.collection_member,
        )
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


def _durable_metadata_enabled() -> bool:
    """Durable metadata is always authoritative in production."""
    return not _test_in_memory_metadata()


def _test_in_memory_metadata() -> bool:
    """Private test seam; production defaults to durable metadata."""
    return False


def _job_metadata(job: _ImportJob) -> AnkiJobMetadata:
    now = datetime.now(UTC)
    return AnkiJobMetadata(
        job_id=job.job_id,
        plan_id=job.plan_id,
        file_token=job.path.name,
        package_sha256=job.inspection.package_sha256,
        collection_sha256=job.inspection.collection_sha256,
        collection_member=job.inspection.collection_member,
        card_count=len(job.inspection.cards),
        transformed_count=job.inspection.transformed_count,
        skipped_count=job.inspection.skipped_count,
        rejected_count=job.inspection.skipped_count,
        created_at=now,
        updated_at=now,
        expires_at=now + JOB_TTL,
    )


async def _persist_job(job: _ImportJob) -> None:
    if not _durable_metadata_enabled():
        return
    try:
        job.metadata = await AnkiJobRepository().create(_job_metadata(job))
    except Exception as exc:
        raise AnkiHttpError("study_anki_unavailable", 503) from exc


def _path_for_file_token(root: Path, token: str, *, prefix: str) -> Path:
    if not isinstance(token, str) or not re.fullmatch(rf"{prefix}-[a-f0-9]{{64}}\.apkg", token):
        raise AnkiHttpError("job_not_found", 404)
    path = root / token
    return _validate_root_file(path, root)


def _tombstone_path(root: Path, token: str, *, prefix: str) -> Path | None:
    match = re.fullmatch(rf"{prefix}-([a-f0-9]{{64}})\.apkg", token)
    if match is None:
        return None
    return root / f".expired-{prefix}-{match.group(1)}.apkg"


def _stage_expired_file(root: Path, token: str, *, prefix: str) -> tuple[Path | None, Path] | None:
    """Move an expired file to a same-root tombstone without symlink follow."""
    if not isinstance(token, str):
        return None
    tombstone = _tombstone_path(root, token, prefix=prefix)
    if tombstone is None:
        return None
    source = root / token
    try:
        root_resolved = root.resolve(strict=True)
        if root.is_symlink() or source.is_symlink() or tombstone.is_symlink():
            return None
        if tombstone.exists():
            if tombstone.resolve(strict=False).parent != root_resolved or not tombstone.is_file():
                return None
            if source.exists():
                return None
            return tombstone, source
        if not source.exists():
            return None, source
        if source.resolve(strict=False).parent != root_resolved or not source.is_file():
            return None
        source.replace(tombstone)
        return tombstone, source
    except OSError:
        return None


def _restore_tombstone(tombstone: Path, source: Path) -> None:
    try:
        if tombstone.is_symlink() or source.exists() or source.is_symlink():
            return
        if tombstone.resolve(strict=False).parent != source.parent.resolve(strict=True):
            return
        tombstone.replace(source)
    except OSError:
        return


def _remove_tombstone(tombstone: Path) -> None:
    try:
        if tombstone.is_symlink() or not tombstone.is_file():
            return
        if tombstone.resolve(strict=False).parent != tombstone.parent.resolve(strict=True):
            return
        tombstone.unlink(missing_ok=True)
    except OSError:
        return


async def _sweep_tombstones(root: Path, *, prefix: str, repository: Any) -> None:
    """Bounded retry for exact tombstones left after an unlink failure."""
    try:
        root_resolved = root.resolve(strict=True)
        if root.is_symlink():
            return
        pattern = re.compile(rf"^\.expired-{prefix}-[a-f0-9]{{64}}\.apkg$")
        for path in sorted(root.iterdir(), key=lambda item: item.name)[:_MAX_RETAINED_JOBS]:
            if not pattern.fullmatch(path.name) or path.resolve(strict=False).parent != root_resolved:
                continue
            token = f"{prefix}-{path.name.split('-', 2)[2]}"
            try:
                referenced = await repository.has_file_token(token)
            except Exception:
                # Keep the tombstone when the authority cannot be checked;
                # deleting it would risk losing a still-referenced file.
                referenced = True
            if referenced:
                _restore_tombstone(path, root / token)
            else:
                _remove_tombstone(path)
    except OSError:
        return


async def _cleanup_expired_metadata() -> None:
    """Bounded opportunistic TTL cleanup for metadata and owned bytes."""
    if not _durable_metadata_enabled():
        return
    try:
        import_root = _import_root()
        export_root = _export_root()
    except AnkiHttpError:
        return
    await _sweep_tombstones(
        import_root, prefix="upload", repository=AnkiJobRepository()
    )
    await _sweep_tombstones(
        export_root, prefix="export", repository=AnkiExportRepository()
    )
    expired_jobs: tuple[tuple[str, str], ...] = ()
    try:
        expired_jobs = await AnkiJobRepository().list_expired(limit=_MAX_RETAINED_JOBS)
    except Exception:
        # Cleanup must not turn a valid upload/export into a 503; status and
        # download still enforce expiry on every access.
        expired_jobs = ()
    for job_id, token in expired_jobs:
        staged = _stage_expired_file(import_root, token, prefix="upload")
        if staged is None:
            continue
        tombstone, source = staged
        try:
            deleted = await AnkiJobRepository().delete_expired(job_id)
        except Exception:
            deleted = False
        if deleted:
            if tombstone is not None:
                _remove_tombstone(tombstone)
        elif tombstone is not None:
            _restore_tombstone(tombstone, source)
    expired_exports: tuple[tuple[str, str], ...] = ()
    try:
        expired_exports = await AnkiExportRepository().list_expired(limit=_MAX_RETAINED_DOWNLOADS)
    except Exception:
        expired_exports = ()
    for download_id, token in expired_exports:
        staged = _stage_expired_file(export_root, token, prefix="export")
        if staged is None:
            continue
        tombstone, source = staged
        try:
            deleted = await AnkiExportRepository().delete_expired(download_id)
        except Exception:
            deleted = False
        if deleted:
            if tombstone is not None:
                _remove_tombstone(tombstone)
        elif tombstone is not None:
            _restore_tombstone(tombstone, source)


async def _load_job(plan_id: str, job_id: str) -> _ImportJob:
    if not _ID.fullmatch(job_id):
        raise AnkiHttpError("job_not_found", 404)
    if _durable_metadata_enabled():
        try:
            metadata = await AnkiJobRepository().get(job_id, plan_id)
        except Exception as exc:
            raise AnkiHttpError("study_anki_unavailable", 503) from exc
        if metadata is None or metadata.plan_id != plan_id or metadata.expires_at <= datetime.now(UTC):
            raise AnkiHttpError("job_not_found", 404)
        if metadata.status == "published":
            inspection = AnkiPackageInspection(
                package_sha256=metadata.package_sha256,
                collection_sha256=metadata.collection_sha256,
                collection_member=metadata.collection_member,
                cards=(),
                note_count=0,
                transformed_count=metadata.transformed_count,
                skipped_count=metadata.skipped_count,
            )
            return _ImportJob(
                job_id=metadata.job_id,
                plan_id=metadata.plan_id,
                path=_import_root() / metadata.file_token,
                inspection=inspection,
                status=metadata.status,
                publish_request_id=metadata.claim_request_id,
                publish_options_sha256=metadata.claim_options_sha256,
                metadata=metadata,
            )
        path = _path_for_file_token(_import_root(), metadata.file_token, prefix="upload")
        try:
            inspection = inspect_anki_package(path)
        except AnkiPackageRejected as exc:
            raise AnkiHttpError(f"invalid_upload:{exc.code}") from exc
        if inspection.package_sha256 != metadata.package_sha256:
            raise AnkiHttpError("job_not_found", 404)
        return _ImportJob(
            job_id=metadata.job_id,
            plan_id=metadata.plan_id,
            path=path,
            inspection=inspection,
            status=metadata.status,
            publish_request_id=metadata.claim_request_id,
            publish_options_sha256=metadata.claim_options_sha256,
            metadata=metadata,
        )
    job = _IMPORT_JOBS.get(job_id)
    if job is None or job.plan_id != plan_id:
        raise AnkiHttpError("job_not_found", 404)
    return job


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
        _IMPORT_JOBS.popitem(last=False)


def _retain_download(download_id: str, path: Path) -> None:
    _DOWNLOADS[download_id] = path
    _DOWNLOADS.move_to_end(download_id)
    while len(_DOWNLOADS) > _MAX_RETAINED_DOWNLOADS:
        _DOWNLOADS.popitem(last=False)


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
        await _cleanup_expired_metadata()
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
        try:
            await _persist_job(job)
        except AnkiHttpError:
            path.unlink(missing_ok=True)
            _IMPORT_JOBS.pop(job_id, None)
            raise
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
        if _durable_metadata_enabled():
            try:
                metadata = await AnkiJobRepository().get(job_id, plan_id)
            except Exception as exc:
                raise AnkiHttpError("study_anki_unavailable", 503) from exc
            if metadata is None or metadata.expires_at <= datetime.now(UTC):
                raise AnkiHttpError("job_not_found", 404)
            base = _preview(_ImportJob(metadata.job_id, metadata.plan_id, Path("."), AnkiPackageInspection(
                package_sha256=metadata.package_sha256,
                collection_sha256=metadata.collection_sha256,
                collection_member=metadata.collection_member,
                cards=(),
                note_count=0,
                transformed_count=metadata.transformed_count,
                skipped_count=metadata.skipped_count,
            )), metadata).model_dump(mode="python")
            receipt_id = metadata.receipt_id
            return AnkiImportStatusResponse(**base, receipt_id=receipt_id)
        job = await _load_job(plan_id, job_id)
        base = _preview(job).model_dump(mode="python")
        return AnkiImportStatusResponse(**base, receipt_id=job.receipt.receipt_id if job.receipt else None)
    except AnkiHttpError as exc:
        raise _error_response(exc) from None


@router.post("/{plan_id}/anki/import/{job_id}:publish", response_model=AnkiImportPublishResponse)
async def publish_anki_import(plan_id: str, job_id: str, payload: AnkiImportPublishRequest) -> AnkiImportPublishResponse:
    try:
        plan_id = _safe_plan_id(plan_id)
        job = await _load_job(plan_id, job_id)
        if payload.upload_id != job_id:
            raise AnkiHttpError("upload_id_mismatch")
        options = AnkiImportOptions.model_validate(payload.options.model_dump(mode="python"))
        options_hash = _options_sha256(options)
        if _durable_metadata_enabled() and job.metadata is not None:
            if job.metadata.status == "published" and job.metadata.receipt_id:
                try:
                    replay = await AnkiImportRepository().find_by_receipt(plan_id, job.metadata.receipt_id)
                except Exception as exc:
                    raise AnkiHttpError("study_anki_unavailable", 503) from exc
                if replay is None:
                    raise AnkiHttpError("study_anki_unavailable", 503)
                _assert_replay_authority(
                    replay, job.metadata, payload.request_id, options_hash
                )
                return AnkiImportPublishResponse(status="replayed", receipt=_http_receipt(replay))
            try:
                claim = await AnkiJobRepository().claim(
                    job_id,
                    plan_id,
                    job.metadata.package_sha256,
                    payload.request_id,
                    options_hash,
                )
            except Exception as exc:
                raise AnkiHttpError("study_anki_unavailable", 503) from exc
            if claim == "conflict":
                raise AnkiHttpError("request_id_conflict", 409)
            if claim == "missing":
                raise AnkiHttpError("job_not_found", 404)
            if claim == "replay":
                try:
                    replay = await AnkiImportRepository()._find_by_request(plan_id, payload.request_id)
                except Exception as exc:
                    raise AnkiHttpError("study_anki_unavailable", 503) from exc
                if replay is None:
                    raise AnkiHttpError("publish_in_progress", 409)
                # Native publication and durable job completion are separate
                # commits.  If the worker crashed after the receipt committed,
                # a same-request replay must repair the durable job while the
                # original owner lease still fences the write.  Returning the
                # receipt alone would leave the job publishing forever.
                try:
                    current = await AnkiJobRepository().get(job_id, plan_id)
                except Exception as exc:
                    raise AnkiHttpError("study_anki_unavailable", 503) from exc
                if current is None:
                    raise AnkiHttpError("job_not_found", 404)
                _assert_replay_authority(
                    replay, current, payload.request_id, options_hash
                )
                if current.status != "published":
                    owner_token = current.claim_owner_token
                    if not isinstance(owner_token, str):
                        raise AnkiHttpError("publish_in_progress", 409)
                    try:
                        repaired = await AnkiJobRepository().complete(
                            job_id,
                            plan_id,
                            payload.request_id,
                            options_hash,
                            replay.receipt_id,
                            owner_token,
                            package_sha256=current.package_sha256,
                        )
                    except Exception as exc:
                        raise AnkiHttpError("study_anki_unavailable", 503) from exc
                    if repaired is None:
                        try:
                            latest = await AnkiJobRepository().get(job_id, plan_id)
                        except Exception as exc:
                            raise AnkiHttpError("study_anki_unavailable", 503) from exc
                        if latest is None or latest.status != "published" or latest.receipt_id != replay.receipt_id:
                            raise AnkiHttpError("publish_in_progress", 409)
                return AnkiImportPublishResponse(status="replayed", receipt=_http_receipt(replay))
            owner_token = getattr(claim, "owner_token", None)
            if not isinstance(owner_token, str):
                raise AnkiHttpError("publish_in_progress", 409)
        else:
            owner_token = None
        existing = job.receipt
        if existing is not None:
            if (
                existing.request_id != payload.request_id
                or job.publish_options_sha256 != options_hash
                or existing.package_sha256 != job.inspection.package_sha256
            ):
                raise AnkiHttpError("request_id_conflict", 409)
            return AnkiImportPublishResponse(status="replayed", receipt=_http_receipt(existing))
        try:
            receipt = await _publish_import(plan_id, job, options, payload.request_id)
        except AnkiPackageRejected as exc:
            if owner_token is not None:
                await AnkiJobRepository().fail(
                    job_id,
                    plan_id,
                    payload.request_id,
                    options_hash,
                    owner_token,
                    package_sha256=job.inspection.package_sha256,
                )
            raise _package_error(exc) from None
        except AnkiImportConflict as exc:
            if owner_token is not None:
                await AnkiJobRepository().fail(
                    job_id,
                    plan_id,
                    payload.request_id,
                    options_hash,
                    owner_token,
                    package_sha256=job.inspection.package_sha256,
                )
            raise AnkiHttpError("request_id_conflict", 409) from exc
        except AnkiImportRepositoryError as exc:
            if owner_token is not None:
                await AnkiJobRepository().fail(
                    job_id,
                    plan_id,
                    payload.request_id,
                    options_hash,
                    owner_token,
                    package_sha256=job.inspection.package_sha256,
                )
            raise AnkiHttpError("study_anki_unavailable", 503) from exc
        if owner_token is not None:
            try:
                completed = await AnkiJobRepository().complete(
                    job_id,
                    plan_id,
                    payload.request_id,
                    options_hash,
                    receipt.receipt_id,
                    owner_token,
                    package_sha256=job.inspection.package_sha256,
                )
            except Exception as exc:
                raise AnkiHttpError("study_anki_unavailable", 503) from exc
            if completed is None:
                raise AnkiHttpError("publish_in_progress", 409)
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
    try:
        canonical_plan_id = str(ensure_record_id(plan_id))
    except Exception as exc:
        raise AnkiHttpError("invalid_plan_id") from exc
    rows = await repo_query(
        "SELECT card_id FROM study_plan_card WHERE plan_id = $plan_id "
        "ORDER BY card_id LIMIT 10001",
        {"plan_id": canonical_plan_id},
    )
    if len(rows) > MAX_EXPORT_CARDS:
        raise AnkiHttpError("card_limit_exceeded")
    compat_rows = await repo_query(
        "SELECT card_id, source_note_id, source_model_kind, template_ord, kind, "
        "source_fields, deck_name, tags, package_sha256 FROM study_anki_card_compat "
        "WHERE plan_id = $plan_id ORDER BY card_id LIMIT 10001",
        {"plan_id": canonical_plan_id},
    )
    compatibility: dict[str, dict[str, Any]] = {}
    for compat_row in compat_rows:
        if not isinstance(compat_row, dict) or not isinstance(compat_row.get("card_id"), str):
            raise AnkiHttpError("invalid_card_projection", 503)
        compatibility[str(compat_row["card_id"])] = compat_row
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
        card_projection: dict[str, Any] = {
            "card_id": card.id or card.artifact_card_id,
            "version": card.version,
            "front": card.front,
            "back": card.back,
            "tags": ["study", "deeper-notebook"],
            "kind": persisted_kind if persisted_kind != "basic" else ("cloze" if "{{c" in card.front else "basic"),
        }
        compat = compatibility.get(str(record)) or compatibility.get(str(card.id or ""))
        if compat is not None:
            source_fields = compat.get("source_fields")
            if not isinstance(source_fields, (list, tuple)) or not 2 <= len(source_fields) <= 4:
                raise AnkiHttpError("invalid_card_projection", 503)
            card_projection.update(
                {
                    "source_note_id": compat.get("source_note_id"),
                    "source_model_kind": compat.get("source_model_kind"),
                    "template_ord": compat.get("template_ord"),
                    "source_fields": tuple(source_fields),
                    "kind": compat.get("kind", card_projection["kind"]),
                    "tags": compat.get("tags", card_projection["tags"]),
                    "deck_name": compat.get("deck_name"),
                    "package_sha256": compat.get("package_sha256"),
                }
            )
        cards.append(card_projection)
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
    source_note_id = card.get("source_note_id")
    if source_note_id is not None and (
        not isinstance(source_note_id, str)
        or not source_note_id.strip()
        or len(source_note_id) > 128
        or any(ord(char) < 32 or ord(char) == 127 for char in source_note_id)
    ):
        raise AnkiHttpError("invalid_card_projection")
    source_fields = card.get("source_fields", ())
    if not isinstance(source_fields, (list, tuple)) or len(source_fields) not in {0, 2}:
        raise AnkiHttpError("invalid_card_projection")
    if any(
        not isinstance(value, str)
        or len(value.encode("utf-8")) > 16_384
        or any(ord(char) == 0 or ord(char) == 127 for char in value)
        for value in source_fields
    ):
        raise AnkiHttpError("invalid_card_projection")
    source_model_kind = card.get("source_model_kind")
    if source_model_kind is not None and source_model_kind not in {"basic", "cloze"}:
        raise AnkiHttpError("invalid_card_projection")
    template_ord = card.get("template_ord")
    if template_ord is not None and (
        isinstance(template_ord, bool) or not isinstance(template_ord, int) or not 0 <= template_ord <= 999
        or ((kind != "cloze" or source_model_kind == "basic") and template_ord > 1)
    ):
        raise AnkiHttpError("invalid_card_projection")
    deck_name = card.get("deck_name")
    if deck_name is not None and (
        not isinstance(deck_name, str) or not deck_name.strip() or len(deck_name) > 200
    ):
        raise AnkiHttpError("invalid_card_projection")
    package_sha256 = card.get("package_sha256")
    if package_sha256 is not None and (
        not isinstance(package_sha256, str) or re.fullmatch(r"[a-f0-9]{64}", package_sha256) is None
    ):
        raise AnkiHttpError("invalid_card_projection")
    return {
        "card_id": card_id,
        "version": raw_version,
        "front": front,
        "back": back,
        "kind": kind,
        "tags": tuple(sorted(clean_tags_list)),
        "source_note_id": source_note_id,
        "source_model_kind": source_model_kind,
        "template_ord": template_ord,
        "source_fields": tuple(source_fields),
        "deck_name": deck_name,
        "package_sha256": package_sha256,
        "index": index,
    }


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


def _build_package(
    plan: dict[str, Any], cards: list[dict[str, Any]], destination: Path
) -> tuple[tuple[str, ...], tuple[int, ...], tuple[int, ...], int]:
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
    used_model_ids: set[int] = set()
    emitted_groups: set[tuple[str, str, str]] = set()
    consumed: set[int] = set()
    expected_card_count = 0
    for index, card in enumerate(cards):
        if index in consumed:
            continue
        kind = card["kind"]
        source_note_id = card.get("source_note_id")
        package_sha256 = card.get("package_sha256")
        # A Task 15 reverse note arrives as two native cards (ord 0 and 1).
        # The compatibility projection binds both cards to one source note,
        # so rebuild one reverse note instead of emitting a basic note plus a
        # second reverse note.  Package hash is part of the identity because
        # source note IDs are only package-local.
        grouped_indices: list[int] = [index]
        if (
            isinstance(source_note_id, str)
            and isinstance(package_sha256, str)
            and card.get("source_model_kind") == "basic"
            and kind in {"basic", "reverse"}
        ):
            identity = (package_sha256, source_note_id)
            grouped_indices = [
                candidate_index
                for candidate_index, candidate in enumerate(cards)
                if candidate_index not in consumed
                and candidate.get("source_model_kind") == "basic"
                and candidate.get("kind") in {"basic", "reverse"}
                and candidate.get("package_sha256") == identity[0]
                and candidate.get("source_note_id") == identity[1]
            ]
            grouped_kinds = {cards[candidate_index]["kind"] for candidate_index in grouped_indices}
            if "reverse" in grouped_kinds:
                if not any(
                    cards[candidate_index].get("kind") == "basic"
                    and cards[candidate_index].get("template_ord") == 0
                    for candidate_index in grouped_indices
                ):
                    raise AnkiHttpError("reverse_template_subset_unsupported", 422)
                # Prefer the reverse projection as the representative so a
                # partial/legacy front cannot replace the original fields.
                representative_index = next(
                    candidate_index
                    for candidate_index in grouped_indices
                    if cards[candidate_index]["kind"] == "reverse"
                )
                card = cards[representative_index]
                kind = "reverse"
            else:
                kind = "basic"
            consumed.update(grouped_indices)
        elif kind in {"reverse", "cloze"} and isinstance(source_note_id, str):
            group_key = (kind, str(package_sha256 or "native"), source_note_id)
            if group_key in emitted_groups:
                consumed.add(index)
                continue
            emitted_groups.add(group_key)
            consumed.add(index)
        else:
            consumed.add(index)
        canonical_card_id = (
            f"{package_sha256}|{source_note_id}"
            if isinstance(source_note_id, str) and isinstance(package_sha256, str)
            else source_note_id if isinstance(source_note_id, str) else card["card_id"]
        )
        canonical = f"{plan['plan_id']}|{canonical_card_id}|{card['version']}|1"
        guid = hashlib.sha256(canonical.encode()).hexdigest()[:32]
        note_guids.append(guid)
        model = {"basic": basic_model, "reverse": reverse_model, "cloze": cloze_model}[kind]
        used_model_ids.add(int(model.model_id))
        source_fields = card.get("source_fields") or ()
        if kind == "cloze" and len(source_fields) == 2 and isinstance(package_sha256, str):
            source_ordinals = {
                int(match.group(1)) for match in _CLOZE_TOKEN.finditer(source_fields[0])
            }
            observed_ordinals = {
                int(candidate.get("template_ord")) + 1
                for candidate in cards
                if candidate.get("kind") == "cloze"
                and candidate.get("package_sha256") == package_sha256
                and candidate.get("source_note_id") == source_note_id
                and isinstance(candidate.get("template_ord"), int)
            }
            if source_ordinals != observed_ordinals:
                raise AnkiHttpError("cloze_template_subset_unsupported", 409)
        if kind == "reverse" and len(source_fields) == 2:
            fields = [_escape_field(source_fields[0]), _escape_field(source_fields[1])]
        elif kind == "cloze" and len(source_fields) == 2 and _CLOZE_TOKEN.search(source_fields[0]):
            fields = [_escape_cloze(source_fields[0]), _escape_field(source_fields[1])]
        elif kind == "cloze" and _CLOZE_TOKEN.search(card["front"]):
            fields = [_escape_cloze(card["front"]), _escape_field(card["back"])]
        else:
            fields = [_escape_field(card["front"]), _escape_field(card["back"])]
        if kind == "reverse":
            expected_card_count += 2
        elif kind == "cloze":
            expected_card_count += max(
                1,
                len({int(match.group(1)) for match in _CLOZE_TOKEN.finditer(source_fields[0] if len(source_fields) == 2 else card["front"])}),
            )
        else:
            expected_card_count += 1
        note = genanki.Note(model=model, fields=fields, tags=list(card["tags"]), guid=guid)
        deck.add_note(note)
    genanki.Package(deck).write_to_file(destination)
    # genanki always retains the built-in Default deck alongside the custom
    # deck; include both IDs in the package receipt identity.
    return tuple(note_guids), tuple(sorted(used_model_ids)), (1, deck_id), expected_card_count


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
                notes = connection.execute("SELECT guid, flds FROM notes ORDER BY id LIMIT 10001").fetchall()
                cards = connection.execute("SELECT id FROM cards ORDER BY id LIMIT 10001").fetchall()
                if len(cards) > MAX_EXPORT_CARDS:
                    raise AnkiHttpError("generated_package_card_count_exceeded", 503)
                models_raw, decks_raw = connection.execute("SELECT models, decks FROM col").fetchone()
                models = json.loads(models_raw)
                decks = json.loads(decks_raw)
    return AnkiExportInspection(
        card_count=len(cards),
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
    cards.sort(
        key=lambda card: (
            str(card.get("package_sha256") or ""),
            str(card.get("source_note_id") or card["card_id"]),
            int(card["template_ord"]) if card.get("template_ord") is not None else -1,
            str(card["kind"]),
            str(card["card_id"]),
        )
    )
    semantic = _semantic_export_payload(plan, cards)
    semantic_hash = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(output.parent, 0o700)
    with tempfile.TemporaryDirectory(prefix="dn-anki-export-") as temp_root:
        temp_path = Path(temp_root) / "package.apkg"
        os.chmod(temp_root, 0o700)
        note_guids, model_ids, deck_ids, expected_card_count = _build_package(plan, cards, temp_path)
        # Validate the produced bytes before publication.  The native Task 15
        # inspector is intentionally the trust boundary; this output contains
        # no external/package-controlled paths or add-ons.
        try:
            inspect_anki_package(temp_path)
        except AnkiPackageRejected as exc:
            # genanki's fixed native indexes are safe but older Task 15 builds
            # may reject them as package input.  Keep this failure typed.
            raise AnkiHttpError(f"generated_package_invalid:{exc.code}") from exc
        semantic_inspection = inspect_export(temp_path)
        if (
            set(semantic_inspection.stable_note_guids) != set(note_guids)
            or semantic_inspection.stable_model_ids != model_ids
            or semantic_inspection.stable_deck_ids != deck_ids
            or semantic_inspection.card_count != expected_card_count
        ):
            raise AnkiHttpError("generated_package_identity_mismatch", 503)
        staged = output.parent / f".{output.name}.{secrets.token_hex(8)}.tmp"
        shutil.copyfile(temp_path, staged)
        os.chmod(staged, 0o600)
        os.replace(staged, output)
    receipt_id = f"anki_export:{semantic_hash}"
    semantic_card_count = semantic_inspection.card_count
    if semantic_card_count != expected_card_count:
        raise AnkiHttpError("generated_package_card_count_mismatch", 503)
    receipt = AnkiExportReceipt(
        receipt_id=receipt_id,
        plan_id=str(plan["plan_id"]),
        plan_revision=int(plan.get("plan_revision", plan.get("version", 1))),
        syllabus_version=int(plan["approved_syllabus_version"]),
        package_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        card_count=semantic_card_count,
        stable_note_guids=semantic_inspection.stable_note_guids,
        stable_model_ids=semantic_inspection.stable_model_ids,
        stable_deck_ids=semantic_inspection.stable_deck_ids,
        created_at=datetime.now(UTC),
    )
    return AnkiExportResult(path=output, receipt=receipt)


@router.post("/{plan_id}/anki/export", response_model=AnkiExportResponse)
async def export_study_plan_anki(plan_id: str, payload: AnkiExportRequest) -> AnkiExportResponse:
    try:
        plan_id = _safe_plan_id(plan_id)
        await _cleanup_expired_metadata()
        # A Study Plan is exported as one native deck. `deck_names` and
        # `syllabus_unit_id` are import selectors; the shared strict options
        # contract is validated, but those selectors do not filter exports.
        loaded = _load_export_plan(plan_id)
        plan = await loaded if inspect.isawaitable(loaded) else loaded
        file_token = f"export-{secrets.token_hex(32)}.apkg"
        result = export_anki_package(plan, _export_root() / file_token)
        download_id = f"anki_download:{secrets.token_hex(32)}"
        _retain_download(download_id, result.path)
        if _durable_metadata_enabled():
            now = datetime.now(UTC)
            try:
                await AnkiExportRepository().create(
                    AnkiExportMetadata(
                        download_id=download_id,
                        plan_id=result.receipt.plan_id,
                        file_token=file_token,
                        plan_revision=result.receipt.plan_revision,
                        syllabus_version=result.receipt.syllabus_version,
                        package_sha256=result.receipt.package_sha256,
                        receipt_id=result.receipt.receipt_id,
                        card_count=result.receipt.card_count,
                        stable_note_guids=result.receipt.stable_note_guids,
                        stable_model_ids=result.receipt.stable_model_ids,
                        stable_deck_ids=result.receipt.stable_deck_ids,
                        created_at=now,
                        expires_at=now + EXPORT_TTL,
                    )
                )
            except Exception as exc:
                result.path.unlink(missing_ok=True)
                _DOWNLOADS.pop(download_id, None)
                raise AnkiHttpError("study_anki_unavailable", 503) from exc
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
        if _durable_metadata_enabled():
            try:
                metadata = await AnkiExportRepository().get(download_id)
            except Exception as exc:
                raise AnkiHttpError("study_anki_unavailable", 503) from exc
            if metadata is None or metadata.expires_at <= datetime.now(UTC):
                raise AnkiHttpError("download_not_found", 404)
            resolved = _path_for_file_token(_export_root(), metadata.file_token, prefix="export")
            try:
                if resolved.stat().st_size > MAX_UPLOAD_BYTES:
                    raise AnkiHttpError("download_size_exceeded", 404)
            except AnkiHttpError:
                raise
            except OSError as exc:
                raise AnkiHttpError("download_not_found", 404) from exc
            if hashlib.sha256(resolved.read_bytes()).hexdigest() != metadata.package_sha256:
                raise AnkiHttpError("download_not_found", 404)
        else:
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
