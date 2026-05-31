"""Phase 1 Task 3 — Aggregated local-model health endpoint.

Frontend's sidebar badge component polls this every 30s; the
launcher also calls it via the in-process function at startup
so launcher.log captures verified-working status.

v0.8.38 — also exposes per-sidecar stderr tail + classified hint
via /healthz/sidecars/{kind}/log. The launcher (v0.8.38) writes
the rolling tail to {OPEN_NOTEBOOK_LAUNCHER_LOG_DIR}/supervisor.{kind}.tail;
this router reads it on demand.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()


# v0.8.38 — the launcher's supervisor names map to user-facing "kinds"
# that the frontend uses in the badge popover URL. Keep this map narrow
# so a malicious / typo'd `kind` path-param can't escape the log_dir.
_KIND_TO_SUPERVISOR: dict[str, str] = {
    "chat": "supervisor.llamacpp_chat",
    "embed": "supervisor.llamacpp_embed",
    "whisper": "supervisor.whisper",
    "piper": "supervisor.piper",
    "memory": "supervisor.memory",
}


async def _load_local_credentials() -> list[dict]:
    """Fetch credentials whose `provider == 'openai_compatible'`
    AND whose `base_url` points to a local sidecar (127.0.0.1
    OR localhost). The local-only filter is load-bearing — we
    don't want this endpoint to probe a user-configured remote
    LM Studio or Ollama on a LAN box. That's a different concern
    and would belong on a different surface.

    v0.8.0 Task 3 refactor — was sync + `asyncio.run`; converted
    to async to eliminate the future-refactor footgun (the
    `asyncio.run` would explode if the caller ever became async).
    Also widened the local-sidecar match to include `localhost`
    so users who registered an openai_compatible credential as
    `http://localhost:PORT/v1` (common LM Studio default) are
    picked up by the probe."""
    from open_notebook.domain.credential import Credential

    creds = await Credential.get_all()
    return [
        {
            "name": c.name,
            "kind": c.provider,
            "base_url": c.base_url or "",
        }
        for c in creds
        if c.provider == "openai_compatible"
        and _is_local_sidecar_url(c.base_url or "")
    ]


def _is_local_sidecar_url(url: str) -> bool:
    """Match `http://127.0.0.1[:PORT]...` or `http://localhost[:PORT]...`.
    https:// is intentionally NOT matched today — none of our
    bundled sidecars use TLS, and a user-configured https endpoint
    is more likely to be a remote service than a local sidecar."""
    return (
        url.startswith("http://127.0.0.1")
        or url.startswith("http://localhost")
    )


@router.get("/api/local-models/health")
async def local_models_health():
    """Active health probe across all local sidecars. Each probe
    has its own ≤9s timeout; total endpoint latency scales with
    the number of registered local credentials (typically 4-5).

    v0.8.20 CRITICAL — `probe_all_local_models` drives sync
    `httpx.Client` requests with up to a 9s per-probe budget. The
    earlier code called it directly inside this `async def` handler,
    so a wedged sidecar (or a couple of them) would block the
    FastAPI event loop for the full 9-45s sweep — every other
    in-flight request (chat SSE streams, status polls, frontend
    badge polls) stalled in lockstep. With the frontend polling
    /api/local-models/health every 30s, a single hung local model
    cascaded into freezing the app for 9s every poll. `to_thread`
    pushes the sync httpx calls onto the default executor so the
    loop keeps serving everyone else."""
    from open_notebook.health.local_models import probe_all_local_models

    creds = await _load_local_credentials()
    results = await asyncio.to_thread(probe_all_local_models, creds)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    total_configured = sum(
        1 for r in results if r["status"] != "not_configured"
    )
    if total_configured == 0:
        overall = "down"
    elif healthy == total_configured:
        overall = "healthy"
    else:
        overall = "degraded"
    return {"overall": overall, "models": results}


@router.get("/api/local-models/inventory")
async def local_models_inventory():
    """v0.8.39 — List GGUF files in the configured model dir with
    metadata (architecture, context length, quant, parameter count,
    file size).

    The model dir is resolved from environment in this order:
      1. `OPEN_NOTEBOOK_MODEL_DIR` (explicit override)
      2. The launcher-exported `OPEN_NOTEBOOK_MODEL_DIR_DEFAULT` (set
         in `desktop/launcher.py` session_env in v0.8.39 — but
         falling back gracefully when running the API standalone)
      3. `~/Desktop/AI_Models` (matches `desktop/config.py:default_model_dir`
         POSIX default — the same path the launcher uses out-of-box)

    Returns:
      {
        "model_dir": str,
        "available": bool,    # False when dir doesn't exist
        "models": [
          {
            "name": "qwen2.5-7b-instruct-q4_k_m",
            "path": "/Users/.../qwen2.5-7b-instruct-q4_k_m.gguf",
            "architecture": "qwen2" | null,
            "context_length": 32768 | null,
            "quant": "Q4_K_M" | null,
            "parameter_count_b": 7.0 | null,
            "file_size_bytes": 4368450336
          },
          ...
        ]
      }

    Surfaces only metadata — no mutation, no download. Future
    `POST /local-models/download` (v0.8.39b) + `POST /local-models/set-active`
    (v0.8.39c) extend this read-only foundation.
    """
    from open_notebook.local_models import enumerate_models
    from pathlib import Path as _Path

    # Resolve model dir per docstring precedence.
    raw = (
        os.environ.get("OPEN_NOTEBOOK_MODEL_DIR")
        or os.environ.get("OPEN_NOTEBOOK_MODEL_DIR_DEFAULT")
        or ""
    ).strip()
    if not raw:
        # Final POSIX fallback (matches desktop/config.py:default_model_dir).
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
        raw = str(_Path(home) / "Desktop" / "AI_Models") if home else ""

    if not raw:
        return {"model_dir": "", "available": False, "models": []}

    model_dir = _Path(raw)
    available = model_dir.exists() and model_dir.is_dir()

    # Inventory is sync (filesystem stat per file); push to a thread so
    # the event loop doesn't block on slow disks.
    if not available:
        return {"model_dir": str(model_dir), "available": False, "models": []}

    rows = await asyncio.to_thread(enumerate_models, model_dir)
    return {
        "model_dir": str(model_dir),
        "available": True,
        "models": [
            {
                "name": r.name,
                "path": r.path,
                "architecture": r.metadata.architecture,
                "context_length": r.metadata.context_length,
                "quant": r.metadata.quant,
                "parameter_count_b": r.metadata.parameter_count_b,
                "file_size_bytes": r.metadata.file_size_bytes,
            }
            for r in rows
        ],
    }


@router.get("/api/local-models/recommendations")
async def local_models_recommendations():
    """v0.8.39b — Curated HuggingFace GGUF recommendations.

    Static list maintained in
    `open_notebook/local_models/downloader.py:RECOMMENDATIONS`. The
    frontend renders these as one-click download cards on the Local
    Models page. Each entry carries:
      - `id`: stable key for React.
      - `label`, `description`: UI copy.
      - `repo_id`, `filename`: HuggingFace location.
      - `approx_size_gb`: pre-download size hint.
      - `tags`: ["chat", "tools", "small", "recommended", "embedding"…]
      - `context_length`: native n_ctx; informs router headroom.
    """
    from open_notebook.local_models import RECOMMENDATIONS
    return {"recommendations": RECOMMENDATIONS}


@router.post("/api/local-models/download")
async def local_models_download(body: dict):
    """v0.8.39b — Start a background HuggingFace GGUF download.

    Body: `{repo_id: str, filename: str}` — typically lifted from a
    recommendation card; the frontend can also pass a custom pair for
    expert users.

    Response: `{job_id: str, status: str, target_path: str, ...}` —
    poll `GET /local-models/downloads/{job_id}` for progress.

    Idempotency: re-POSTing with the same (repo_id, filename) while a
    job is already queued/downloading returns that existing job rather
    than starting a duplicate. Prevents the .part file corruption that
    two concurrent downloaders would cause.

    The target directory is resolved the same way as `inventory` above
    (OPEN_NOTEBOOK_MODEL_DIR > launcher default > POSIX default).
    """
    from open_notebook.local_models import start_download
    from pathlib import Path as _Path

    repo_id = (body.get("repo_id") or "").strip()
    filename = (body.get("filename") or "").strip()
    if not repo_id or not filename:
        raise HTTPException(
            status_code=400,
            detail="Both `repo_id` and `filename` are required.",
        )
    # Defense-in-depth: filename must look like a GGUF file and not
    # contain path separators (so it can't escape dest_dir).
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(
            status_code=400,
            detail="`filename` must not contain path separators.",
        )
    if not filename.lower().endswith(".gguf"):
        raise HTTPException(
            status_code=400,
            detail="`filename` must end in .gguf.",
        )
    # v0.8.66 (audit S-1) — validate repo_id to the HuggingFace
    # `namespace/name` shape. It is interpolated into the download URL
    # (https://huggingface.co/{repo_id}/resolve/main/{filename}); leaving it
    # unsanitized let a caller smuggle path-traversal / query / fragment / `@`
    # sequences into the path. The host is pinned to huggingface.co so this is
    # defense-in-depth (matching the filename guard above), keeping malformed
    # input + traversal out of the composed URL.
    import re as _re
    if not _re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", repo_id
    ):
        raise HTTPException(
            status_code=400,
            detail="`repo_id` must be of the form `namespace/name` "
            "(letters, digits, dot, dash, underscore only).",
        )

    raw = (
        os.environ.get("OPEN_NOTEBOOK_MODEL_DIR")
        or os.environ.get("OPEN_NOTEBOOK_MODEL_DIR_DEFAULT")
        or ""
    ).strip()
    if not raw:
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
        raw = str(_Path(home) / "Desktop" / "AI_Models") if home else ""
    if not raw:
        raise HTTPException(
            status_code=500,
            detail="No model directory configured. Set OPEN_NOTEBOOK_MODEL_DIR.",
        )
    dest_dir = _Path(raw)

    job = await start_download(repo_id, filename, dest_dir)
    return {
        "job_id": job.job_id,
        "status": job.status,
        "target_path": job.target_path,
        "bytes_downloaded": job.bytes_downloaded,
        "bytes_total": job.bytes_total,
    }


@router.post("/api/local-models/downloads/{job_id}/cancel")
async def local_models_download_cancel(job_id: str):
    """v0.8.39e — Request cancellation of an in-flight GGUF download.

    Sets a flag the streaming task checks between 1 MiB chunks. The
    job transitions to `status="cancelled"` and the `.part` file stays
    on disk — a subsequent `POST /local-models/download` for the same
    `(repo_id, filename)` automatically resumes via HTTP Range (see
    v0.8.39e in `_stream_download`).

    Returns:
      200 + `{ok: true, detail: ...}` — cancellation flag set.
      404 if `job_id` is unknown (typo, or job from a previous API
          process; in-memory registry).
      409 if the job is already in a terminal state (completed /
          failed / cancelled) — caller should poll for current status
          rather than retry.
    """
    from open_notebook.local_models import cancel_job, get_job
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown download job {job_id!r}.",
        )
    ok, detail = cancel_job(job_id)
    if not ok:
        # Already terminal — 409 Conflict so the client doesn't keep
        # retrying. Status is in the detail string.
        raise HTTPException(status_code=409, detail=detail)
    return {"ok": True, "detail": detail}


@router.get("/api/local-models/downloads")
async def local_models_downloads_list():
    """v0.8.39d — List all known download jobs, reconciling against
    on-disk `.part.meta` sidecars first.

    On a fresh API process the in-memory job registry is empty, but a
    download interrupted by the restart left a `.part` file + sidecar
    on disk. `reconcile_jobs` rebuilds those as `cancelled` (resumable)
    jobs so the frontend can proactively show a "Resume" affordance on
    the Local Models page after a restart — instead of the user having
    to rediscover which model was mid-download.

    Response: `{ "downloads": [ {job_id, status, repo_id, filename,
    target_path, bytes_downloaded, bytes_total, error}, ... ] }`.
    """
    from open_notebook.local_models import list_jobs, reconcile_jobs
    from pathlib import Path as _Path

    raw = (
        os.environ.get("OPEN_NOTEBOOK_MODEL_DIR")
        or os.environ.get("OPEN_NOTEBOOK_MODEL_DIR_DEFAULT")
        or ""
    ).strip()
    if not raw:
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
        raw = str(_Path(home) / "Desktop" / "AI_Models") if home else ""

    if raw:
        # Reconcile is async (holds the registry lock); cheap glob + a
        # few file stats, but keep it off any sync path.
        await reconcile_jobs(_Path(raw))

    return {
        "downloads": [
            {
                "job_id": j.job_id,
                "status": j.status,
                "repo_id": j.repo_id,
                "filename": j.filename,
                "target_path": j.target_path,
                "bytes_downloaded": j.bytes_downloaded,
                "bytes_total": j.bytes_total,
                "error": j.error,
            }
            for j in list_jobs()
        ]
    }


@router.get("/api/local-models/downloads/{job_id}")
async def local_models_download_status(job_id: str):
    """v0.8.39b — Poll a download's progress.

    Response: `{job_id, status, repo_id, filename, target_path,
    bytes_downloaded, bytes_total, error}`. `status` cycles through
    queued → downloading → (completed | failed | cancelled).

    404 if the job_id is unknown. After an API restart the in-memory
    registry is empty, but `GET /local-models/downloads` (v0.8.39d)
    reconciles interrupted downloads from disk sidecars first — call
    that to repopulate, then poll individual job IDs.
    """
    from open_notebook.local_models import get_job
    job = get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown download job {job_id!r}.",
        )
    return {
        "job_id": job.job_id,
        "status": job.status,
        "repo_id": job.repo_id,
        "filename": job.filename,
        "target_path": job.target_path,
        "bytes_downloaded": job.bytes_downloaded,
        "bytes_total": job.bytes_total,
        "error": job.error,
    }


@router.get("/api/healthz/sidecars/{kind}/log")
async def sidecar_log(kind: str):
    """v0.8.38 — Return the most recent stderr tail for a local sidecar
    plus a user-friendly classified hint (e.g. "Model file not found")
    derived from the tail content.

    Shape:
      { "kind": "chat",
        "log": "<last ~50 lines, possibly empty>",
        "hint": "Out of memory — try a smaller model" | null,
        "available": true|false }

    `available: false` means we couldn't find a tail file — either the
    launcher hasn't run yet, OPEN_NOTEBOOK_LAUNCHER_LOG_DIR isn't set
    (the API is running outside the desktop launcher), or this
    sidecar kind never spawned (`embed` on a CPU-only install).

    Used by `LocalModelHealthBadges` popover when a user clicks a red
    badge. Path-traversal-safe: `kind` is validated against a fixed
    allowlist (_KIND_TO_SUPERVISOR) BEFORE composing the filename, so
    "../etc/passwd" can't escape the log dir even if a misconfigured
    proxy strips path-cleaning.
    """
    if kind not in _KIND_TO_SUPERVISOR:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown sidecar kind {kind!r}. Expected one of: "
                f"{', '.join(sorted(_KIND_TO_SUPERVISOR))}."
            ),
        )

    log_dir_str = os.environ.get("OPEN_NOTEBOOK_LAUNCHER_LOG_DIR", "").strip()
    if not log_dir_str:
        # API running standalone (no launcher) — no logs to surface.
        return {"kind": kind, "log": "", "hint": None, "available": False}

    log_dir = Path(log_dir_str)
    tail_path = log_dir / f"{_KIND_TO_SUPERVISOR[kind]}.tail"

    if not tail_path.exists():
        return {"kind": kind, "log": "", "hint": None, "available": False}

    # The tail file is small (≤ 50 lines), but the read is sync; push
    # to a worker thread to keep the event loop snappy in case the
    # filesystem is slow.
    def _read_tail() -> str:
        try:
            data = tail_path.read_bytes()
        except OSError:
            return ""
        # Defensive cap — never return more than 8 KiB even if the file
        # somehow grew past the deque's maxlen (e.g. user manually
        # edited it).
        if len(data) > 8 * 1024:
            data = data[-8 * 1024:]
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    log_text = await asyncio.to_thread(_read_tail)

    # Classify on the API side so the frontend doesn't have to ship
    # the pattern list. Falls back to None when no pattern matches —
    # UI then renders just the raw tail.
    from open_notebook.utils.error_classifier import classify_sidecar_error
    hint = classify_sidecar_error(log_text)

    return {"kind": kind, "log": log_text, "hint": hint, "available": True}


@router.post("/api/local-models/set-active")
async def local_models_set_active(body: dict):
    """v0.8.40b — Hot-swap the active chat GGUF without restarting
    the app.

    Body: `{"path": "/abs/path/to/model.gguf"}` — typically lifted
    from a row in `GET /local-models/inventory`.

    Response: `{ok: bool, path: str, detail: str}`.

    Validation:
      - File must exist + be a regular file + end in `.gguf`.
      - File must live under the configured model_dir (path-traversal
        defense at the API edge AND again at the launcher edge —
        belt-and-braces matching the v0.8.39b download endpoint).

    Failure modes (mirror sidecar_restart):
      - 400 if validation fails or the launcher rejects the swap
        (sidecar never spawned, file gone between API check and
        launcher check, etc).
      - 503 if launcher control plane isn't configured.
      - 502 if launcher control plane is unreachable / returns 5xx.
    """
    from pathlib import Path as _Path

    new_path = (body.get("path") or "").strip()
    if not new_path:
        raise HTTPException(status_code=400, detail="Body must include `path`.")

    p = _Path(new_path)
    if not p.exists() or not p.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"File not found or not a regular file: {new_path}",
        )
    if p.suffix.lower() != ".gguf":
        raise HTTPException(
            status_code=400,
            detail="`path` must point to a `.gguf` file.",
        )

    # Resolve the configured model dir using the same precedence as
    # the inventory + download endpoints — keeps the three in sync.
    raw_dir = (
        os.environ.get("OPEN_NOTEBOOK_MODEL_DIR")
        or os.environ.get("OPEN_NOTEBOOK_MODEL_DIR_DEFAULT")
        or ""
    ).strip()
    if not raw_dir:
        home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
        raw_dir = str(_Path(home) / "Desktop" / "AI_Models") if home else ""
    if not raw_dir:
        raise HTTPException(
            status_code=500,
            detail="No model directory configured. Set OPEN_NOTEBOOK_MODEL_DIR.",
        )
    model_dir = _Path(raw_dir).resolve()
    # Path-traversal guard at the API edge. The launcher does the
    # same check independently (defense-in-depth), but failing here
    # gives a faster 400 + no network hop.
    try:
        resolved = p.resolve()
    except OSError:
        raise HTTPException(status_code=400, detail="Could not resolve path.")
    if model_dir not in resolved.parents and resolved.parent != model_dir:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Path must be inside the configured model directory "
                f"({model_dir})."
            ),
        )

    # Reuse the same control-plane proxy machinery as the restart
    # endpoint.
    control_url = os.environ.get("OPEN_NOTEBOOK_LAUNCHER_CONTROL_URL", "").strip()
    control_token = os.environ.get("OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", "").strip()
    if not control_url or not control_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "Launcher control plane not available. The API is running "
                "outside the desktop launcher, or the launcher could not "
                "bind its control port. Quit and relaunch the app."
            ),
        )

    import httpx as _httpx

    # Generous read timeout — hot-swap kills + respawns the chat
    # sidecar, which mmap's a multi-GB GGUF. 60s upper bound for
    # cold-disk loads of large quants.
    timeout = _httpx.Timeout(connect=2.0, read=60.0, write=5.0, pool=5.0)
    headers = {"Authorization": f"Bearer {control_token}"}

    def _call_launcher() -> tuple[int, dict]:
        with _httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{control_url}/hot_swap_chat",
                json={"path": str(resolved)},
                headers=headers,
            )
            try:
                body = resp.json()
            except Exception:
                body = {"ok": False, "detail": resp.text[:500]}
            return resp.status_code, body

    try:
        status_code, lbody = await asyncio.to_thread(_call_launcher)
    except _httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Launcher control plane unreachable "
                f"({exc.__class__.__name__}). Relaunch the app."
            ),
        )

    if status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail=lbody.get("error") or lbody.get("detail")
                   or f"Launcher returned HTTP {status_code}",
        )
    if status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=lbody.get("error") or lbody.get("detail")
                   or f"Launcher returned HTTP {status_code}",
        )
    return {
        "ok": lbody.get("ok", False),
        "path": str(resolved),
        "detail": lbody.get("detail", ""),
    }


@router.post("/api/healthz/sidecars/{kind}/restart")
async def sidecar_restart(kind: str):
    """v0.8.40 — Restart a local sidecar by proxying to the launcher
    control plane (v0.8.40 `desktop/launcher_control.py:ControlServer`).

    Flow:
      1. Validate `kind` against the same allowlist
         (`_KIND_TO_SUPERVISOR`) the log endpoint uses.
      2. Read `OPEN_NOTEBOOK_LAUNCHER_CONTROL_URL` + `_TOKEN` from env
         (set by the launcher via session_env at boot).
      3. POST `{kind}` to the launcher's `/restart_sidecar` with the
         token in the Authorization header. The launcher kills the
         old Popen's process group and re-spawns with the same args.
      4. Return the launcher's `{ok, kind, detail}` directly.

    Failure modes:
      - 404 if kind not in allowlist.
      - 503 if the control URL isn't set (API running standalone, not
        under the desktop launcher) or the launcher control server
        is unreachable (down/crashed).
      - 502 if the launcher returns a non-2xx response (bad token,
        sidecar wasn't ever spawned, kill timed out, etc.) — we
        surface the launcher's `detail` for diagnosis.

    Defense-in-depth: the path-param allowlist check happens BEFORE
    we touch the network, so a malformed `kind` can't be forwarded
    to the launcher.
    """
    if kind not in _KIND_TO_SUPERVISOR:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown sidecar kind {kind!r}. Expected one of: "
                f"{', '.join(sorted(_KIND_TO_SUPERVISOR))}."
            ),
        )

    control_url = os.environ.get("OPEN_NOTEBOOK_LAUNCHER_CONTROL_URL", "").strip()
    control_token = os.environ.get("OPEN_NOTEBOOK_LAUNCHER_CONTROL_TOKEN", "").strip()
    if not control_url or not control_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "Launcher control plane not available. The API is "
                "running outside the desktop launcher, or the launcher "
                "could not bind its control port. Quit and relaunch the "
                "app to retry."
            ),
        )

    import httpx as _httpx

    # Short-but-realistic timeout — restarts often take 2-5s while the
    # new sidecar binds its port, but a hung launcher shouldn't tie up
    # the API request slot. 15s is generous; a real hang gets a
    # connect/read error which we map to 502 below.
    timeout = _httpx.Timeout(connect=2.0, read=15.0, write=5.0, pool=5.0)
    headers = {"Authorization": f"Bearer {control_token}"}

    def _call_launcher() -> tuple[int, dict]:
        with _httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{control_url}/restart_sidecar",
                json={"kind": kind},
                headers=headers,
            )
            try:
                body = resp.json()
            except Exception:
                body = {"ok": False, "detail": resp.text[:500]}
            return resp.status_code, body

    try:
        status_code, body = await asyncio.to_thread(_call_launcher)
    except _httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Launcher control plane unreachable ({exc.__class__.__name__}). "
                "The launcher may have crashed; relaunch the app."
            ),
        )

    if status_code >= 500:
        raise HTTPException(
            status_code=502,
            detail=body.get("error") or body.get("detail")
                   or f"Launcher returned HTTP {status_code}",
        )
    # 400/401 from the launcher → bubble as 400 so the UI sees a
    # specific message ("Sidecar never spawned this session", etc).
    if status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=body.get("error") or body.get("detail")
                   or f"Launcher returned HTTP {status_code}",
        )

    return {
        "kind": kind,
        "ok": body.get("ok", False),
        "detail": body.get("detail", ""),
    }
