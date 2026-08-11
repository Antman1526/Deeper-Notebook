"""Managed Hugging Face snapshot installs for repo-style local models."""
from __future__ import annotations

import asyncio
import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class SnapshotInstallJob:
    job_id: str
    repo_id: str
    target_path: str
    status: Literal[
        "queued",
        "downloading",
        "completed",
        "failed",
        "cancelled",
    ] = "queued"
    error: str | None = None
    log_tail: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    _task: object | None = field(default=None, repr=False)
    revision: str | None = None
    _requested_revision: str | None = field(default=None, repr=False)


_JOBS: dict[str, SnapshotInstallJob] = {}
_REGISTRY_LOCK: "asyncio.Lock | None" = None
_MAX_LOG_LINES = 20
_MAX_TERMINAL_JOBS = 512
_COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_SNAPSHOT_META_FILENAME = ".snapshot-install.meta"
_MODEL_CONFIG_FILENAMES = {
    "config.json",
    "params.json",
    "tokenizer.json",
    "tokenizer_config.json",
}
_MODEL_WEIGHT_SUFFIXES = {
    ".bin",
    ".gguf",
    ".mlmodel",
    ".npz",
    ".onnx",
    ".pt",
    ".pth",
    ".safetensors",
}


def _get_registry_lock() -> asyncio.Lock:
    global _REGISTRY_LOCK
    if _REGISTRY_LOCK is None:
        _REGISTRY_LOCK = asyncio.Lock()
    return _REGISTRY_LOCK


def _append_log(job: SnapshotInstallJob, line: str) -> None:
    job.log_tail.append(line)
    if len(job.log_tail) > _MAX_LOG_LINES:
        del job.log_tail[:-_MAX_LOG_LINES]


def _prune_job_history() -> None:
    """Retain a generous terminal history without evicting active jobs."""
    terminal = {
        "completed",
        "failed",
        "cancelled",
    }
    terminal_ids = [
        job_id for job_id, job in _JOBS.items() if job.status in terminal
    ]
    excess = len(terminal_ids) - _MAX_TERMINAL_JOBS
    for job_id in terminal_ids[: max(0, excess)]:
        _JOBS.pop(job_id, None)


def _validate_commit_sha(value: object) -> str:
    if not isinstance(value, str) or not _COMMIT_SHA_RE.fullmatch(value.strip()):
        raise ValueError("Hugging Face snapshot revision is not a 40-character commit SHA")
    return value.strip().lower()


def _resolve_snapshot_revision(repo_id: str, revision: str | None = None) -> str:
    """Resolve a branch/tag to the immutable commit SHA returned by HF."""
    requested = revision.strip() if isinstance(revision, str) else None
    if requested == "":
        requested = None
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo_id, revision=requested or "main")
        resolved = getattr(info, "sha", None)
    except Exception as exc:
        raise RuntimeError(
            f"Could not resolve an immutable Hugging Face revision for {repo_id}"
        ) from exc
    try:
        return _validate_commit_sha(resolved)
    except ValueError as exc:
        raise RuntimeError(
            f"Hugging Face returned an invalid immutable revision for {repo_id}"
        ) from exc


def _snapshot_meta_path(target_dir: Path) -> Path:
    return target_dir / _SNAPSHOT_META_FILENAME


def _write_snapshot_meta(target_dir: Path, job: SnapshotInstallJob) -> None:
    """Best-effort restart marker for long-running repo-folder installs."""
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        _snapshot_meta_path(target_dir).write_text(
            json.dumps(
                {
                    "job_id": job.job_id,
                    "repo_id": job.repo_id,
                    "target_path": job.target_path,
                    "revision": job.revision,
                    "status": job.status,
                    "cancel_requested": job.cancel_requested,
                    "log_tail": job.log_tail[-_MAX_LOG_LINES:],
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _remove_snapshot_meta(target_dir: Path) -> None:
    try:
        meta_path = _snapshot_meta_path(target_dir)
        if meta_path.exists():
            meta_path.unlink()
    except OSError:
        pass


def _has_existing_model_files(target_dir: Path) -> bool:
    """Return True only for a plausibly complete local model snapshot.

    Hugging Face downloads can leave behind `.cache`, README files, or a lone
    config after interruption. Those should not make the installer report
    success, because users need the next click to repair the folder.
    """
    try:
        if not target_dir.exists():
            return False
        has_config = False
        has_weight = False
        for child in target_dir.rglob("*"):
            if child.name == _SNAPSHOT_META_FILENAME or not child.is_file():
                continue
            relative_parts = child.relative_to(target_dir).parts
            if any(part.startswith(".") for part in relative_parts):
                continue
            lower_name = child.name.lower()
            if lower_name in _MODEL_CONFIG_FILENAMES:
                has_config = True
            if child.suffix.lower() in _MODEL_WEIGHT_SUFFIXES:
                has_weight = True
            if has_weight and (has_config or child.suffix.lower() == ".gguf"):
                return True
    except OSError:
        return False
    return False


def _snapshot_download(
    repo_id: str, local_dir: str, *, revision: str | None = None,
) -> None:
    from huggingface_hub import snapshot_download

    if revision is None:
        raise ValueError("An immutable Hugging Face revision is required")
    snapshot_download(repo_id=repo_id, local_dir=local_dir, revision=revision)


async def _run_snapshot_install(
    job: SnapshotInstallJob,
    target_dir: Path,
) -> None:
    if job.cancel_requested:
        job.status = "cancelled"
        _append_log(job, "Snapshot install cancelled before download started.")
        _write_snapshot_meta(target_dir, job)
        _prune_job_history()
        return

    try:
        requested_revision = getattr(job, "_requested_revision", None)
        if requested_revision is None:
            # Preserve compatibility for direct internal callers that set
            # ``job.revision`` before invoking this task body.
            requested_revision = job.revision
        resolved_revision = await asyncio.to_thread(
            _resolve_snapshot_revision, job.repo_id, requested_revision
        )
        job.revision = _validate_commit_sha(resolved_revision)
        _write_snapshot_meta(target_dir, job)
        job.status = "downloading"
        _append_log(job, f"Downloading {job.repo_id} at {job.revision} into {target_dir}")
        _write_snapshot_meta(target_dir, job)
        target_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            _snapshot_download,
            job.repo_id,
            str(target_dir),
            revision=job.revision,
        )
        if job.cancel_requested:
            job.status = "cancelled"
            _append_log(
                job,
                "Snapshot install cancelled after the current transfer returned.",
            )
            _write_snapshot_meta(target_dir, job)
            return
        job.status = "completed"
        _append_log(job, "Snapshot install completed.")
        _remove_snapshot_meta(target_dir)
    except Exception as exc:
        if job.cancel_requested:
            job.status = "cancelled"
            _append_log(job, "Snapshot install cancelled.")
            _write_snapshot_meta(target_dir, job)
            return
        job.status = "failed"
        job.error = str(exc) or exc.__class__.__name__
        _append_log(job, f"Snapshot install failed: {job.error}")
        _write_snapshot_meta(target_dir, job)
    finally:
        _prune_job_history()


async def start_snapshot_install(
    repo_id: str,
    target_dir: Path,
    *,
    revision: str | None = None,
) -> SnapshotInstallJob:
    target_dir = Path(target_dir)
    existing_complete = False
    async with _get_registry_lock():
        for existing in _JOBS.values():
            if (
                existing.repo_id == repo_id
                and Path(existing.target_path) == target_dir
                and existing.status in {"queued", "downloading"}
            ):
                return existing

        job = SnapshotInstallJob(
            job_id=secrets.token_urlsafe(12),
            repo_id=repo_id,
            target_path=str(target_dir),
        )

        # Keep a caller's branch/tag separate from the immutable receipt so
        # restart metadata never advertises an unresolved mutable ref.
        job._requested_revision = revision
        existing_complete = (
            _has_existing_model_files(target_dir)
            and not _snapshot_meta_path(target_dir).exists()
        )
        if existing_complete:
            # Existing files are a local-first no-download path. A prior
            # sidecar's immutable revision is retained by reconciliation, but
            # do not require network metadata just to reuse a complete folder.
            if revision is not None:
                try:
                    job.revision = _validate_commit_sha(revision)
                except ValueError:
                    job.revision = None
            pass
        else:
            _prune_job_history()
            _JOBS[job.job_id] = job
            _write_snapshot_meta(target_dir, job)

    if existing_complete:
        job.status = "completed"
        _append_log(
            job,
            "Target directory already contains model files; skipping download.",
        )
        return job

    task = asyncio.create_task(_run_snapshot_install(job, target_dir))
    job._task = task
    return job


def cancel_snapshot_install(job_id: str) -> tuple[bool, str]:
    job = _JOBS.get(job_id)
    if job is None:
        return False, f"Unknown snapshot install job {job_id!r}"
    if job.status in {"completed", "failed", "cancelled"}:
        return False, f"Job already {job.status}"
    job.cancel_requested = True
    _append_log(
        job,
        "Cancellation requested. The active Hugging Face transfer may finish before stopping.",
    )
    _write_snapshot_meta(Path(job.target_path), job)
    return True, "Cancellation requested"


def get_snapshot_install(job_id: str) -> SnapshotInstallJob | None:
    _prune_job_history()
    return _JOBS.get(job_id)


def list_snapshot_installs() -> list[SnapshotInstallJob]:
    _prune_job_history()
    return list(_JOBS.values())


async def reconcile_snapshot_installs(model_dir: Path) -> int:
    """Rebuild interrupted repo-folder install jobs from sidecars."""
    model_dir = Path(model_dir)
    if not model_dir.exists() or not model_dir.is_dir():
        return 0

    reconstructed = 0
    async with _get_registry_lock():
        live_keys = {
            (job.repo_id, str(Path(job.target_path)))
            for job in _JOBS.values()
        }
        try:
            meta_files = list(model_dir.rglob(_SNAPSHOT_META_FILENAME))
        except OSError:
            return 0

        for meta_path in meta_files:
            target_dir = meta_path.parent
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                try:
                    meta_path.unlink()
                except OSError:
                    pass
                continue

            repo_id = (meta.get("repo_id") or "").strip()
            if not repo_id:
                continue

            raw_revision = meta.get("revision")
            revision: str | None = None
            revision_error: str | None = None
            if raw_revision is not None:
                try:
                    revision = _validate_commit_sha(raw_revision)
                except ValueError as exc:
                    revision_error = str(exc)

            key = (repo_id, str(target_dir))
            if key in live_keys:
                continue

            job_id = meta.get("job_id") or secrets.token_urlsafe(12)
            log_tail = meta.get("log_tail")
            job = SnapshotInstallJob(
                job_id=job_id,
                repo_id=repo_id,
                target_path=str(target_dir),
                status="failed" if revision_error else "cancelled",
                revision=revision,
                error=revision_error,
                log_tail=log_tail if isinstance(log_tail, list) else [],
                cancel_requested=not revision_error,
            )
            _append_log(
                job,
                (
                    "Interrupted snapshot install has malformed revision metadata."
                    if revision_error
                    else "Interrupted snapshot install found. Start install again to resume."
                ),
            )
            _JOBS[job_id] = job
            live_keys.add(key)
            reconstructed += 1

    _prune_job_history()
    return reconstructed


def reset_snapshot_installs_for_tests() -> None:
    global _REGISTRY_LOCK
    _JOBS.clear()
    _REGISTRY_LOCK = None
