"""v0.8.39d — Persistent download jobs across API restart.

The in-memory `_JOBS` dict is lost on restart, but a download
interrupted mid-flight leaves a `.part` file + a `.part.meta` sidecar
on disk. `reconcile_jobs(dest_dir)` rebuilds those as `cancelled`
(resumable) jobs so the frontend can show a Resume affordance after a
restart. v0.8.39e already handles the actual resume from the `.part`
offset on the next download click.

Tests (no network — reconcile is pure filesystem):
  - reconcile rebuilds a job from a sidecar + surviving .part
  - reconstructed job has status="cancelled" + resume_from_bytes set
  - reconcile is idempotent (second call doesn't duplicate)
  - sidecar with no surviving .part is pruned, no job created
  - corrupt sidecar is pruned, no crash
  - reconcile skips a (repo,filename) already owned by a live job
  - the GET /local-models/downloads endpoint reconciles + lists
"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as lm_router
from deeper_notebook.local_models import downloader as dl_mod


@pytest.fixture(autouse=True)
def _reset_jobs():
    dl_mod.reset_for_tests()
    yield
    dl_mod.reset_for_tests()


def _write_sidecar(dest_dir, filename, repo_id, bytes_total, job_id="job-x"):
    (dest_dir / f"{filename}.part.meta").write_text(
        json.dumps(
            {
                "job_id": job_id,
                "repo_id": repo_id,
                "filename": filename,
                "bytes_total": bytes_total,
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_reconcile_rebuilds_job_from_sidecar(tmp_path):
    # Simulate an interrupted download: a .part with bytes + its sidecar.
    (tmp_path / "qwen.gguf.part").write_bytes(b"x" * 1500)
    _write_sidecar(tmp_path, "qwen.gguf", "bartowski/Qwen-GGUF", 5000)

    n = await dl_mod.reconcile_jobs(tmp_path)
    assert n == 1

    jobs = dl_mod.list_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.repo_id == "bartowski/Qwen-GGUF"
    assert job.filename == "qwen.gguf"
    # Reconstructed as resumable (reuses the cancelled status + frontend
    # Resume affordance).
    assert job.status == "cancelled"
    assert job.resume_from_bytes == 1500
    assert job.bytes_downloaded == 1500
    assert job.bytes_total == 5000


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(tmp_path):
    (tmp_path / "m.gguf.part").write_bytes(b"y" * 800)
    _write_sidecar(tmp_path, "m.gguf", "r/m", 1600)

    first = await dl_mod.reconcile_jobs(tmp_path)
    second = await dl_mod.reconcile_jobs(tmp_path)
    assert first == 1
    # Second call must NOT duplicate — the (repo, filename) is already live.
    assert second == 0
    assert len(dl_mod.list_jobs()) == 1


@pytest.mark.asyncio
async def test_reconcile_prunes_sidecar_without_part(tmp_path):
    # Sidecar present but the .part is gone (e.g. completed download
    # whose sidecar-removal failed). No job created; sidecar pruned.
    _write_sidecar(tmp_path, "ghost.gguf", "r/ghost", 1000)
    assert (tmp_path / "ghost.gguf.part.meta").exists()

    n = await dl_mod.reconcile_jobs(tmp_path)
    assert n == 0
    assert dl_mod.list_jobs() == []
    assert not (tmp_path / "ghost.gguf.part.meta").exists()


@pytest.mark.asyncio
async def test_reconcile_prunes_corrupt_sidecar(tmp_path):
    (tmp_path / "bad.gguf.part").write_bytes(b"z" * 100)
    (tmp_path / "bad.gguf.part.meta").write_text("{ this is not json", encoding="utf-8")

    n = await dl_mod.reconcile_jobs(tmp_path)
    assert n == 0
    # Corrupt sidecar pruned; no crash.
    assert not (tmp_path / "bad.gguf.part.meta").exists()


@pytest.mark.asyncio
async def test_reconcile_skips_live_job(tmp_path):
    # A live in-flight job already owns this (repo, filename).
    live = dl_mod.DownloadJob(
        job_id="live-1",
        repo_id="r/m",
        filename="m.gguf",
        target_path=str(tmp_path / "m.gguf"),
        status="downloading",
    )
    dl_mod._JOBS["live-1"] = live

    (tmp_path / "m.gguf.part").write_bytes(b"q" * 400)
    _write_sidecar(tmp_path, "m.gguf", "r/m", 800, job_id="stale-id")

    n = await dl_mod.reconcile_jobs(tmp_path)
    assert n == 0  # live job wins; no phantom reconstruction
    assert len(dl_mod.list_jobs()) == 1
    assert dl_mod.list_jobs()[0].job_id == "live-1"


@pytest.mark.asyncio
async def test_reconcile_missing_dir_returns_zero():
    from pathlib import Path

    n = await dl_mod.reconcile_jobs(Path("/no/such/dir/v0_8_39d"))
    assert n == 0


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(lm_router.router)
    return a


def test_downloads_list_endpoint_reconciles_and_lists(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    (tmp_path / "hermes.gguf.part").write_bytes(b"h" * 2048)
    _write_sidecar(tmp_path, "hermes.gguf", "r/hermes", 8192, job_id="jh")

    with TestClient(app) as client:
        resp = client.get("/api/local-models/downloads")
    assert resp.status_code == 200
    body = resp.json()
    assert "downloads" in body
    assert len(body["downloads"]) == 1
    d = body["downloads"][0]
    assert d["repo_id"] == "r/hermes"
    assert d["filename"] == "hermes.gguf"
    assert d["status"] == "cancelled"
    assert d["bytes_downloaded"] == 2048
    assert d["bytes_total"] == 8192


def test_downloads_list_endpoint_empty_when_no_parts(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/local-models/downloads")
    assert resp.status_code == 200
    assert resp.json() == {"downloads": []}
