"""v0.8.39b — HuggingFace GGUF downloader.

In-process async background-task downloader for GGUF files from
HuggingFace. Streams the file via httpx so progress is observable at a
fine grain, writes to a `.part` sibling, then atomically renames on
success — same atomic-rename pattern the launcher's tail drainer uses
(v0.8.38) so a half-downloaded file is never seen by `enumerate_models`.

Job state lives in a module-level dict; lost on API restart. The
partial `.part` file remains on disk so the user can re-trigger
(downloader detects the partial and currently starts over — resume is
a future-work item; HuggingFace serves Range so resume is feasible).

Why in-process rather than `surreal_commands`:
  - `surreal_commands` is the desktop bundle's job queue and requires
    a worker process registered alongside the API. Cleaner long-term,
    but pulling a worker just for downloads doubles the install
    footprint for a feature most users hit once.
  - Background asyncio.create_task() with a polling status endpoint is
    sufficient for a desktop single-user app. Multi-user multi-tenant
    deployments should swap to surreal_commands; that's tracked as
    v0.8.39d.
"""
from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

# Curated GGUF recommendations. Each entry is a known-good
# combination of HuggingFace `repo_id` + filename that we've validated
# works with our llama-cpp-python chat sidecar. Tags drive the UI
# grouping (chat vs embedding). `approx_size_gb` is a UX hint shown
# before the user commits to the download — actual size is fetched from
# the Content-Length header at download time.
#
# Keep this list short + opinionated. Three high-quality picks beat
# twenty unranked choices for a Settings → Local Models recommendations
# panel. Pull requests adding new entries should include a maintainer
# note on why the recommendation matters (size/speed tradeoff, license,
# tool-calling support, etc.).
RECOMMENDATIONS: list[dict] = [
    {
        "id": "qwen2.5-7b-instruct-q4_k_m",
        "label": "Qwen 2.5 7B Instruct (Q4_K_M)",
        "description": (
            "Excellent general-purpose chat model with strong tool-calling. "
            "32k context, ~4.7 GB on disk. The recommended starter for "
            "most users."
        ),
        "repo_id": "bartowski/Qwen2.5-7B-Instruct-GGUF",
        "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "approx_size_gb": 4.7,
        "tags": ["chat", "tools", "recommended"],
        "context_length": 32768,
    },
    {
        "id": "qwen2.5-3b-instruct-q5_k_m",
        "label": "Qwen 2.5 3B Instruct (Q5_K_M)",
        "description": (
            "Smaller / faster alternative for low-RAM machines. Sacrifices "
            "some capability for ~2.3 GB on disk; still good for chat + "
            "transformations."
        ),
        "repo_id": "bartowski/Qwen2.5-3B-Instruct-GGUF",
        "filename": "Qwen2.5-3B-Instruct-Q5_K_M.gguf",
        "approx_size_gb": 2.3,
        "tags": ["chat", "tools", "small"],
        "context_length": 32768,
    },
    {
        "id": "nomic-embed-text-v1.5-q5_k_m",
        "label": "Nomic Embed Text v1.5 (Q5_K_M)",
        "description": (
            "Embedding model for the search + memory features. ~100 MB. "
            "Install this if you've selected `embedding` as your default "
            "embedding type."
        ),
        "repo_id": "nomic-ai/nomic-embed-text-v1.5-GGUF",
        "filename": "nomic-embed-text-v1.5.Q5_K_M.gguf",
        "approx_size_gb": 0.1,
        "tags": ["embedding"],
        "context_length": 2048,
    },
]


@dataclass
class DownloadJob:
    """In-memory state for one download. Polled by
    GET /local-models/downloads/{job_id}.

    Status transitions:
      queued → downloading → (completed | failed | cancelled)
    """
    job_id: str
    repo_id: str
    filename: str
    target_path: str
    # v0.8.39e added "cancelled" terminal status.
    status: Literal[
        "queued", "downloading", "completed", "failed", "cancelled",
    ] = "queued"
    bytes_downloaded: int = 0
    bytes_total: int = 0  # 0 until first chunk reveals Content-Length
    error: str | None = None
    # v0.8.39e — cancel flag set by POST /local-models/downloads/{id}/cancel.
    # The stream loop checks it between chunks and tears down cleanly,
    # leaving the .part file on disk for a future resume.
    cancelled: bool = False
    # v0.8.39e — `resume_from_bytes` captures the existing .part size at
    # the moment start_download decided to resume. The stream loop uses
    # it as the seed for bytes_downloaded (so UI progress shows the
    # combined "already downloaded + this run" total against
    # bytes_total) and passes it as the HTTP Range header.
    resume_from_bytes: int = 0
    # Track the asyncio task so callers can request cancellation.
    _task: object | None = field(default=None, repr=False)


# Module-level job registry. Lost on API restart; acceptable for
# desktop single-user use per the docstring at the top.
_JOBS: dict[str, DownloadJob] = {}
_REGISTRY_LOCK: "asyncio.Lock | None" = None
_MAX_TERMINAL_JOBS = 512


def _prune_job_history() -> None:
    """Retain recent terminal jobs while never evicting active transfers."""
    terminal = {"completed", "failed", "cancelled"}
    terminal_ids = [
        job_id for job_id, job in _JOBS.items() if job.status in terminal
    ]
    excess = len(terminal_ids) - _MAX_TERMINAL_JOBS
    for job_id in terminal_ids[: max(0, excess)]:
        _JOBS.pop(job_id, None)


def _get_registry_lock() -> asyncio.Lock:
    """Lazy-init asyncio.Lock for the jobs dict. Same lazy-construct
    pattern as `deeper_notebook/ai/provision.py:_get_health_cache_lock`
    so we don't capture an event loop at import time."""
    global _REGISTRY_LOCK
    if _REGISTRY_LOCK is None:
        _REGISTRY_LOCK = asyncio.Lock()
    return _REGISTRY_LOCK


def _hf_resolve_url(repo_id: str, filename: str) -> str:
    """Compose the canonical HuggingFace resolve URL. `/resolve/main/`
    follows redirects to the underlying CDN; both httpx (with
    follow_redirects=True) and the user's network handle that."""
    # No URL encoding needed — repo_ids and gguf filenames are
    # restricted-charset by HF convention.
    return f"https://huggingface.co/{repo_id}/resolve/main/{filename}"


# v0.8.39d — persistent-job sidecar. The in-memory `_JOBS` dict is lost
# on API restart, but the `.part` file survives (v0.8.39e resume reads
# it). The missing piece for proactive "you have a resumable download"
# visibility is the `repo_id` — a bare `.part` filename tells us the
# model filename but not which HF repo to resume from. So alongside
# each in-flight `.part` we write a tiny JSON sidecar `{filename}.part.meta`
# carrying `{job_id, repo_id, filename, bytes_total}`. `reconcile_jobs`
# reads these on first list to rebuild interrupted jobs as "cancelled"
# (which the frontend already renders with a Resume affordance).
import json as _json


def _part_meta_path(dest_dir: Path, filename: str) -> Path:
    return dest_dir / f"{filename}.part.meta"


def _write_part_meta(dest_dir: Path, job: "DownloadJob") -> None:
    """Best-effort sidecar write. A failure here must never break the
    download — the worst case is losing proactive resume-visibility
    after a restart (the .part itself + a fresh Download click still
    resume via v0.8.39e)."""
    try:
        meta = {
            "job_id": job.job_id,
            "repo_id": job.repo_id,
            "filename": job.filename,
            "bytes_total": job.bytes_total,
        }
        _part_meta_path(dest_dir, job.filename).write_text(
            _json.dumps(meta), encoding="utf-8",
        )
    except OSError:
        pass


def _remove_part_meta(dest_dir: Path, filename: str) -> None:
    """Remove the sidecar (on successful completion). Best-effort."""
    try:
        p = _part_meta_path(dest_dir, filename)
        if p.exists():
            p.unlink()
    except OSError:
        pass


async def _stream_download(job: DownloadJob, dest_dir: Path) -> None:
    """Background task body. Streams the GGUF from HuggingFace into a
    `.part` file with periodic progress updates, then atomically
    renames to the final path. Any exception is captured on the job
    rather than re-raised — callers poll status instead of awaiting.

    v0.8.39e — supports two new behaviors:
      1. **Cancellation**: caller sets `job.cancelled = True`; the
         loop notices between chunks, sets status="cancelled", and
         leaves the .part file on disk for a future resume.
      2. **Resume**: when `job.resume_from_bytes > 0`, sends a Range
         request to HuggingFace (which serves Range for GGUFs) and
         APPENDS to the existing .part file. Combines the resumed
         byte counter with the new bytes so UI progress reads as
         (already_have + this_run) / total.
    """
    job.status = "downloading"
    final_path = dest_dir / job.filename
    part_path = dest_dir / f"{job.filename}.part"
    url = _hf_resolve_url(job.repo_id, job.filename)

    # v0.8.39e — Resume support. If we're picking up from a previous
    # .part file, open in append-binary mode and ask the server to
    # skip the bytes we already have. Otherwise standard write-binary.
    resume_from = job.resume_from_bytes
    headers: dict[str, str] = {}
    open_mode = "wb"
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"
        open_mode = "ab"
        # Pre-seed the progress counter so the UI shows the existing
        # bytes immediately rather than appearing to start from zero.
        job.bytes_downloaded = resume_from

    # v0.8.39d — write the resume sidecar so a restart mid-download can
    # reconstruct this job (repo_id is otherwise unrecoverable from a
    # bare .part filename). Best-effort; refreshed with bytes_total
    # once headers arrive below.
    _write_part_meta(dest_dir, job)

    try:
        # Long read timeout — multi-GB GGUFs over a slow connection
        # legitimately take minutes per chunk. Connect/write/pool
        # stay tight so a black-hole DNS doesn't hang the slot.
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as resp:
                # v0.8.39e — A Range-request response should be 206
                # Partial Content. If the server returned 200 instead
                # (e.g. mirror that doesn't support Range), the body
                # is the FULL file from byte 0, not the requested
                # range. Append-mode + a 200 response would duplicate
                # the leading bytes and corrupt the file. Detect and
                # fail clearly rather than silently corrupt.
                if resume_from > 0 and resp.status_code == 200:
                    job.status = "failed"
                    job.error = (
                        f"HuggingFace mirror does not support Range requests "
                        f"for {job.filename}. Delete the .part file and "
                        f"re-trigger to start over."
                    )
                    return
                # v0.8.42b — Even a 206 isn't trustworthy on its own:
                # a broken or malicious mirror could return 206 with a
                # Content-Range whose START is not the requested offset
                # (e.g. asked `bytes=1500-` but got `bytes 0-1499/3000`).
                # Appending those bytes would corrupt the file. Verify
                # the Content-Range start matches resume_from BEFORE
                # opening the .part for append. The header shape is
                # `bytes <start>-<end>/<total>`.
                if resume_from > 0 and resp.status_code == 206:
                    cr = resp.headers.get("content-range", "")
                    try:
                        # "bytes 1500-2999/3000" → "1500"
                        start_str = cr.split(" ", 1)[1].split("-", 1)[0]
                        served_start = int(start_str)
                    except (IndexError, ValueError):
                        served_start = -1
                    if served_start != resume_from:
                        job.status = "failed"
                        job.error = (
                            f"Server returned a 206 with mismatched range "
                            f"({cr!r}); expected start at byte {resume_from}. "
                            "Refusing to append potentially-misaligned bytes. "
                            f"Delete the .part file and re-trigger."
                        )
                        return
                resp.raise_for_status()

                # Content-Length is the authoritative size for THIS
                # response. For a Range request it's the remaining
                # bytes (not the file's total). Use Content-Range when
                # present to get the true total, else fall back.
                if resume_from > 0:
                    content_range = resp.headers.get("content-range", "")
                    # Format: "bytes 0-1023/1024" → total after `/`.
                    if "/" in content_range:
                        try:
                            job.bytes_total = int(content_range.rsplit("/", 1)[1])
                        except ValueError:
                            job.bytes_total = 0
                else:
                    total_hdr = resp.headers.get("content-length")
                    if total_hdr:
                        try:
                            job.bytes_total = int(total_hdr)
                        except ValueError:
                            job.bytes_total = 0

                # v0.8.39d — refresh the sidecar now that bytes_total is
                # known, so a post-restart reconcile can show an accurate
                # progress denominator.
                if job.bytes_total:
                    _write_part_meta(dest_dir, job)

                # Atomic-write pattern: stream into .part, rename on
                # success. On cancellation the .part remains for
                # resume; on failure same.
                with open(part_path, open_mode) as f:
                    async for chunk in resp.aiter_bytes(chunk_size=1024 * 1024):
                        # v0.8.39e — cancellation check between chunks.
                        # Setting status here makes the polling endpoint
                        # report "cancelled" before the function exits.
                        if job.cancelled:
                            job.status = "cancelled"
                            return
                        if chunk:
                            f.write(chunk)
                            job.bytes_downloaded += len(chunk)

        # Atomic rename — readers of enumerate_models never see the
        # half-finished file (the part has the `.part` suffix which
        # the inventory module already filters out).
        part_path.replace(final_path)
        # v0.8.39d — download done, the .part is gone; drop its sidecar
        # so a later reconcile doesn't resurrect a phantom resumable job.
        _remove_part_meta(dest_dir, job.filename)
        job.status = "completed"
    except httpx.HTTPStatusError as exc:
        job.status = "failed"
        job.error = f"HTTP {exc.response.status_code} from HuggingFace"
    except httpx.HTTPError as exc:
        job.status = "failed"
        job.error = f"Network error: {exc.__class__.__name__}"
    except OSError as exc:
        # Disk full, perms changed mid-download, etc.
        job.status = "failed"
        job.error = f"Filesystem error: {exc.strerror or str(exc)}"
    except Exception as exc:
        # Belt-and-braces — never crash the background task without
        # leaving a status the UI can render.
        job.status = "failed"
        job.error = f"Unexpected error: {exc.__class__.__name__}"
    finally:
        _prune_job_history()


async def start_download(
    repo_id: str,
    filename: str,
    dest_dir: Path,
) -> DownloadJob:
    """Spawn a background download task. Returns the DownloadJob
    immediately so the caller can return a job_id to the client; the
    client then polls GET /local-models/downloads/{job_id} for status.

    Idempotency: if a job for the same (repo_id, filename) is already
    queued/downloading, return that job instead of starting a duplicate.
    The same model getting kicked off twice from two tabs would otherwise
    write the same .part file from two coroutines and corrupt it.
    """
    async with _get_registry_lock():
        target_path = dest_dir / filename

        # De-dupe in-flight jobs. Include the destination because manifest
        # rows can intentionally place the same HF filename in nested
        # AI_Models folders.
        for existing in _JOBS.values():
            if (
                existing.repo_id == repo_id
                and existing.filename == filename
                and existing.target_path == str(target_path)
                and existing.status in ("queued", "downloading")
            ):
                return existing

        # New job.
        job_id = secrets.token_urlsafe(12)
        dest_dir.mkdir(parents=True, exist_ok=True)
        job = DownloadJob(
            job_id=job_id,
            repo_id=repo_id,
            filename=filename,
            target_path=str(target_path),
        )

        # v0.8.40c — Skip the network round-trip when the final file
        # already exists on disk and is non-empty. Pre-v0.8.40c a
        # second Download click on an already-installed model would
        # re-download multi-GB GGUFs from scratch (the dedupe above
        # only catches IN-FLIGHT jobs, not completed ones). Zero-byte
        # files are NOT treated as already-downloaded — those are
        # failed-download artifacts the v0.8.39 inventory already
        # filters out as not-real-models. We DON'T cache the synthetic
        # job in _JOBS so a subsequent download after file deletion
        # produces a fresh real job.
        target = target_path
        try:
            size = target.stat().st_size if target.exists() else 0
        except OSError:
            size = 0
        if size > 0:
            job.status = "completed"
            job.bytes_total = size
            job.bytes_downloaded = size
            # _task stays None — the synthetic job is complete from
            # the start, no background work to track.
            return job

        # v0.8.39e — Resume support. If a previous run (cancelled,
        # crashed, or interrupted) left a .part file on disk, pick up
        # where it stopped instead of restarting from byte 0. Skip if
        # the .part is zero bytes (failed cold-start; just overwrite).
        part = dest_dir / f"{filename}.part"
        try:
            part_size = part.stat().st_size if part.exists() else 0
        except OSError:
            part_size = 0
        if part_size > 0:
            job.resume_from_bytes = part_size

        _prune_job_history()
        _JOBS[job_id] = job

    # Fire the background task OUTSIDE the lock so the lock is held
    # only for registry mutation, not for the long-running download.
    task = asyncio.create_task(_stream_download(job, dest_dir))
    job._task = task
    return job


def get_job(job_id: str) -> DownloadJob | None:
    """Look up a job. Returns None if unknown (job_id from a previous
    API process, or a typo from the client)."""
    _prune_job_history()
    return _JOBS.get(job_id)


def cancel_job(job_id: str) -> tuple[bool, str]:
    """v0.8.39e — Request cancellation of an in-flight download.

    Sets `job.cancelled = True`; the stream loop notices between
    chunks and tears down cleanly with status="cancelled", leaving
    the `.part` file on disk for a future resume.

    Returns (ok, detail). Not-found and already-terminal cases
    return False with a descriptive detail string — callers map
    these to 404 / 409 at the HTTP layer.
    """
    job = _JOBS.get(job_id)
    if job is None:
        return False, f"Unknown job {job_id!r}"
    if job.status in ("completed", "failed", "cancelled"):
        # Idempotent — already terminal, nothing to cancel. Return
        # False so the HTTP layer can map to 409 Conflict ("job is
        # already in a terminal state").
        return False, f"Job already {job.status}"
    job.cancelled = True
    return True, "Cancellation requested"


def list_jobs() -> list[DownloadJob]:
    """All known jobs across all states. Used by the frontend to render
    in-flight + recently-completed downloads on page load (so a user
    who comes back to the page after a few minutes still sees the
    completion notification)."""
    _prune_job_history()
    return list(_JOBS.values())


async def reconcile_jobs(dest_dir: Path) -> int:
    """v0.8.39d — Rebuild interrupted-download jobs from `.part.meta`
    sidecars after an API restart.

    The in-memory `_JOBS` dict is process-local, so a restart mid-
    download loses the job record even though the `.part` file (and
    its sidecar) survive on disk. This scans `dest_dir` for
    `*.part.meta` sidecars and, for any whose (repo_id, filename) is
    NOT already represented by a live job, reconstructs a
    `DownloadJob` with:

      - status = "cancelled"  — semantically "stopped, resumable". The
        frontend already renders cancelled downloads with a Resume
        affordance (v0.8.39e), and a fresh Download click resumes from
        the `.part` offset. Reusing the existing terminal status means
        zero new frontend enum handling.
      - resume_from_bytes / bytes_downloaded = current `.part` size.
      - bytes_total = the sidecar's recorded total (for the progress
        denominator).

    Sidecars whose `.part` file is gone (e.g. completed download whose
    sidecar removal failed, or a manual cleanup) are pruned. Returns
    the number of jobs reconstructed.

    Idempotent: re-running after reconstruction finds the jobs already
    in `_JOBS` and skips them. Safe to call on every list request.
    """
    if not dest_dir.exists() or not dest_dir.is_dir():
        return 0

    reconstructed = 0
    async with _get_registry_lock():
        # Index live jobs by (repo_id, filename) so we don't duplicate.
        live_keys = {(j.repo_id, j.filename) for j in _JOBS.values()}

        try:
            meta_files = list(dest_dir.glob("*.part.meta"))
        except OSError:
            return 0

        for meta_path in meta_files:
            try:
                meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                # Corrupt / unreadable sidecar — skip (and try to prune).
                try:
                    meta_path.unlink()
                except OSError:
                    pass
                continue

            repo_id = (meta.get("repo_id") or "").strip()
            filename = (meta.get("filename") or "").strip()
            if not repo_id or not filename:
                continue

            part_path = dest_dir / f"{filename}.part"
            try:
                part_size = part_path.stat().st_size if part_path.exists() else 0
            except OSError:
                part_size = 0

            # No surviving .part → nothing to resume; prune the orphan
            # sidecar so it doesn't linger.
            if part_size <= 0:
                try:
                    meta_path.unlink()
                except OSError:
                    pass
                continue

            if (repo_id, filename) in live_keys:
                # A live job already owns this download (in-flight, or
                # already reconstructed on a prior reconcile) — skip.
                continue

            job_id = meta.get("job_id") or secrets.token_urlsafe(12)
            try:
                bytes_total = int(meta.get("bytes_total") or 0)
            except (TypeError, ValueError):
                bytes_total = 0

            job = DownloadJob(
                job_id=job_id,
                repo_id=repo_id,
                filename=filename,
                target_path=str(dest_dir / filename),
                status="cancelled",
                bytes_downloaded=part_size,
                bytes_total=bytes_total,
                resume_from_bytes=part_size,
            )
            _JOBS[job_id] = job
            live_keys.add((repo_id, filename))
            reconstructed += 1

    _prune_job_history()
    return reconstructed


def reset_for_tests() -> None:
    """Clear the module-level state. Tests should call this in
    teardown so jobs don't leak between cases."""
    global _REGISTRY_LOCK
    _JOBS.clear()
    _REGISTRY_LOCK = None
