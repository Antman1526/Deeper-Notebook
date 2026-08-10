"""v0.8.39b — HuggingFace GGUF downloader tests.

No real network — `_stream_download` is the network-touching function
and we mock httpx.AsyncClient there. Everything else is in-process
state management + URL composition + dedupe logic.

Coverage:
  - RECOMMENDATIONS shape — each entry has the required fields, no
    duplicates, sizes sane.
  - URL composition for hf_resolve.
  - start_download happy path (creates a job, fires the background
    task, atomic-renames the .part file on success).
  - start_download de-dupes in-flight jobs.
  - start_download surfaces HTTP / network / disk errors as
    job.status="failed" + job.error (never raises).
  - Endpoint validation (missing repo_id/filename, path-traversal in
    filename, non-.gguf filename).
  - Endpoint 404 for unknown job_id.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import get_type_hints
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.local_models import downloader as dl_mod


@pytest.fixture(autouse=True)
def _reset_jobs():
    """Each test starts with an empty registry."""
    dl_mod.reset_for_tests()
    yield
    dl_mod.reset_for_tests()


# ---------------------------------------------------------------------------
# RECOMMENDATIONS shape
# ---------------------------------------------------------------------------


def test_recommendations_have_required_fields():
    """Every recommendation must have the keys the frontend expects.
    A field missing here would cascade to undefined-error renders."""
    required = {"id", "label", "description", "repo_id", "filename",
                "approx_size_gb", "tags", "context_length"}
    for entry in dl_mod.RECOMMENDATIONS:
        missing = required - entry.keys()
        assert not missing, f"Recommendation {entry.get('id', '?')} missing: {missing}"
        # Hint sanity: tags is a list, sizes positive, repo_id is non-empty.
        assert isinstance(entry["tags"], list)
        assert entry["approx_size_gb"] > 0
        assert entry["repo_id"]
        assert entry["filename"].endswith(".gguf")


def test_recommendation_ids_unique():
    """No duplicate IDs — they're used as React keys."""
    ids = [r["id"] for r in dl_mod.RECOMMENDATIONS]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# URL composition
# ---------------------------------------------------------------------------


def test_hf_resolve_url_format():
    """Canonical HF resolve URL shape."""
    url = dl_mod._hf_resolve_url(
        "bartowski/Qwen2.5-7B-Instruct-GGUF",
        "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
    )
    assert url == (
        "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF"
        "/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    )


# ---------------------------------------------------------------------------
# start_download happy path + dedupe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_download_completes_and_renames(tmp_path):
    """Mock httpx to return a tiny payload; verify the atomic .part →
    final rename happens and the job ends in status='completed'."""

    fake_bytes = b"FAKE-GGUF-PAYLOAD" * 100  # 1700 bytes

    # Build a mocked AsyncClient that yields chunks via aiter_bytes.
    class _FakeStreamResponse:
        status_code = 200
        headers = {"content-length": str(len(fake_bytes))}

        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size: int = 1024 * 1024):
            # Yield in 2 chunks so we exercise the progress-update loop.
            mid = len(fake_bytes) // 2
            yield fake_bytes[:mid]
            yield fake_bytes[mid:]

    class _FakeStreamCtx:
        def __init__(self, resp):
            self.resp = resp

        async def __aenter__(self):
            return self.resp

        async def __aexit__(self, *_a):
            return None

    class _FakeAsyncClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        def stream(self, method, url, headers=None):
            return _FakeStreamCtx(_FakeStreamResponse())

    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient",
               _FakeAsyncClient):
        job = await dl_mod.start_download(
            "bartowski/Some-Model-GGUF",
            "model.gguf",
            tmp_path,
        )
        # Background task fires asynchronously — give it a tick to run.
        await asyncio.wait_for(job._task, timeout=5.0)

    assert job.status == "completed", f"job.error={job.error}"
    assert job.bytes_downloaded == len(fake_bytes)
    assert job.bytes_total == len(fake_bytes)

    # Atomic rename happened — final file exists, .part is gone.
    final = tmp_path / "model.gguf"
    part = tmp_path / "model.gguf.part"
    assert final.exists()
    assert final.read_bytes() == fake_bytes
    assert not part.exists()


@pytest.mark.asyncio
async def test_start_download_dedupes_in_flight(tmp_path):
    """Two start_download calls for the same (repo, filename) while
    the first is still in-flight return the SAME job — no duplicate
    .part writes."""
    # Make the stream block forever so the first job stays in 'downloading'.
    event = asyncio.Event()

    class _BlockingResp:
        status_code = 200
        headers = {"content-length": "1000"}

        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size: int = 1024 * 1024):
            await event.wait()  # Never set.
            yield b""

    class _BlockingStreamCtx:
        async def __aenter__(self):
            return _BlockingResp()

        async def __aexit__(self, *_a):
            return None

    class _BlockingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        def stream(self, m, u, headers=None):
            return _BlockingStreamCtx()

    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient",
               _BlockingClient):
        job1 = await dl_mod.start_download("repo/a", "x.gguf", tmp_path)
        job2 = await dl_mod.start_download("repo/a", "x.gguf", tmp_path)

    assert job1.job_id == job2.job_id, "Second call must return the in-flight job"
    # Cleanup: cancel the blocked task so the event loop closes cleanly.
    job1._task.cancel()
    try:
        await job1._task
    except (asyncio.CancelledError, Exception):
        pass


@pytest.mark.asyncio
async def test_start_download_handles_http_error(tmp_path):
    """A 404 from HuggingFace ends the job as failed with a readable
    error — never raises out of the background task."""

    class _NotFoundResp:
        status_code = 404
        headers = {}
        # Mimic httpx.Response surface enough for raise_for_status.
        request = MagicMock()

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                "Not Found", request=self.request, response=self,
            )

    class _Ctx:
        async def __aenter__(self):
            return _NotFoundResp()

        async def __aexit__(self, *_a):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return None

        def stream(self, m, u, headers=None):
            return _Ctx()

    with patch("deeper_notebook.local_models.downloader.httpx.AsyncClient",
               _Client):
        job = await dl_mod.start_download("repo/bad", "x.gguf", tmp_path)
        await asyncio.wait_for(job._task, timeout=5.0)

    assert job.status == "failed"
    assert "404" in (job.error or "")


# ---------------------------------------------------------------------------
# Endpoint validation
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(local_models_router.router)
    return a


def test_download_endpoint_requires_repo_id(app):
    with TestClient(app) as client:
        resp = client.post("/api/local-models/download",
                           json={"filename": "x.gguf"})
    assert resp.status_code == 400
    assert "repo_id" in resp.text


def test_download_endpoint_requires_filename(app):
    with TestClient(app) as client:
        resp = client.post("/api/local-models/download",
                           json={"repo_id": "repo/a"})
    assert resp.status_code == 400


def test_download_endpoint_rejects_path_traversal(app):
    with TestClient(app) as client:
        resp = client.post("/api/local-models/download",
                           json={"repo_id": "r/a", "filename": "../etc/passwd"})
    assert resp.status_code == 400
    assert "path" in resp.text.lower()


def test_download_endpoint_rejects_non_gguf(app):
    with TestClient(app) as client:
        resp = client.post("/api/local-models/download",
                           json={"repo_id": "r/a", "filename": "evil.exe"})
    assert resp.status_code == 400
    assert "gguf" in resp.text.lower()


def test_download_endpoint_honors_nested_manifest_target_path(app, monkeypatch, tmp_path):
    import deeper_notebook.local_models as lm

    calls: list[tuple[str, str, Path]] = []

    async def fake_start_download(repo_id: str, filename: str, dest_dir: Path):
        calls.append((repo_id, filename, dest_dir))

        class Job:
            job_id = "job-nested"
            status = "queued"
            target_path = str(dest_dir / filename)
            bytes_downloaded = 0
            bytes_total = None

        return Job()

    # Keep the local downloader seam's type annotations resolvable for tools
    # and runtime introspection, not only stringized by ``__future__``.
    assert get_type_hints(fake_start_download)["dest_dir"].__name__ == "Path"

    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(lm, "start_download", fake_start_download, raising=False)
    target = (
        tmp_path
        / "GGUF"
        / "bartowski__Qwen2.5-7B-Instruct-GGUF"
        / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    )

    with TestClient(app) as client:
        resp = client.post(
            "/api/local-models/download",
            json={
                "repo_id": "bartowski/Qwen2.5-7B-Instruct-GGUF",
                "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
                "target_path": str(target),
            },
        )

    assert resp.status_code == 200
    assert calls == [
        (
            "bartowski/Qwen2.5-7B-Instruct-GGUF",
            "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
            target.parent.resolve(),
        )
    ]
    assert resp.json()["target_path"] == str(target)


def test_download_endpoint_rejects_target_path_outside_model_dir(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path / "models"))
    outside = tmp_path / "outside" / "model.gguf"

    with TestClient(app) as client:
        resp = client.post(
            "/api/local-models/download",
            json={
                "repo_id": "repo/model",
                "filename": "model.gguf",
                "target_path": str(outside),
            },
        )

    assert resp.status_code == 400
    assert "configured model directory" in resp.text


def test_download_endpoint_rejects_target_path_filename_mismatch(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.post(
            "/api/local-models/download",
            json={
                "repo_id": "repo/model",
                "filename": "model.gguf",
                "target_path": str(tmp_path / "other.gguf"),
            },
        )

    assert resp.status_code == 400
    assert "basename" in resp.text


def test_download_status_404_for_unknown_job(app):
    with TestClient(app) as client:
        resp = client.get("/api/local-models/downloads/unknown-id-xyz")
    assert resp.status_code == 404


def test_recommendations_endpoint_returns_static_fallback_without_manifest(app, monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/recommendations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "static"
    assert "recommendations" in body
    assert len(body["recommendations"]) >= 1
    first = body["recommendations"][0]
    assert "repo_id" in first
    assert "filename" in first


def test_recommendations_endpoint_returns_manifest_cards_when_manifest_exists(
    app,
    monkeypatch,
    tmp_path,
):
    mlx_path = tmp_path / "MLX" / "mlx-community__North-Mini-Code-1.0-6bit"
    gguf_path = (
        tmp_path
        / "GGUF"
        / "bartowski__Qwen2.5-7B-Instruct-GGUF"
        / "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    )
    manifest = tmp_path / "manifests" / "model_inventory.md"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "\n".join([
            "# Local Model Inventory",
            "",
            "| Category | Role | Repo | Local Path | Runtime Type | Estimated Status | Notes |",
            "|---|---|---|---|---|---|---|",
            f"| General Chat - GGUF | primary | `bartowski/Qwen2.5-7B-Instruct-GGUF` | `{gguf_path}` | GGUF | missing from scan | exact quant |",
            f"| Coding Assistant - Mac MLX | primary | `mlx-community/North-Mini-Code-1.0-6bit` | `{mlx_path}` | MLX | missing from scan | coding and agent workflows |",
        ])
    )
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/api/local-models/recommendations")

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "manifest"
    assert body["manifest_path"] == str(manifest)
    assert body["recommendations"][0]["runtime_type"] == "MLX"
    assert body["recommendations"][0]["setup_task"]["action_type"] == "download_snapshot"
    assert body["recommendations"][1]["runtime_type"] == "GGUF"
    assert body["recommendations"][1]["setup_task"]["action_type"] == "download_gguf"
    assert body["recommendations"][1]["setup_task"]["target_path"] == str(gguf_path)
