from __future__ import annotations

import asyncio
import json
import threading
import types
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import local_models as local_models_router
from deeper_notebook.local_models import snapshot_installer as snap_mod


@pytest.fixture(autouse=True)
def _reset_snapshot_jobs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        snap_mod,
        "_resolve_snapshot_revision",
        lambda _repo_id, revision=None: "a" * 40,
    )
    snap_mod.reset_snapshot_installs_for_tests()
    yield
    snap_mod.reset_snapshot_installs_for_tests()


@pytest.mark.asyncio
async def test_start_snapshot_install_completes_with_snapshot_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []

    def fake_snapshot_download(
        repo_id: str,
        local_dir: str,
        *,
        revision: str | None = None,
    ) -> None:
        calls.append((repo_id, local_dir))
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        Path(local_dir, "config.json").write_text("{}")

    monkeypatch.setattr(snap_mod, "_snapshot_download", fake_snapshot_download)

    target = tmp_path / "MLX" / "repo"
    job = await snap_mod.start_snapshot_install("mlx-community/Test-MLX", target)
    await asyncio.wait_for(job._task, timeout=5)

    assert job.status == "completed"
    assert job.error is None
    assert calls == [("mlx-community/Test-MLX", str(target))]
    assert target.joinpath("config.json").exists()
    assert any("completed" in line.lower() for line in job.log_tail)


@pytest.mark.asyncio
async def test_snapshot_install_resolves_and_passes_immutable_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    resolve_calls: list[tuple[str, str | None]] = []
    download_calls: list[tuple[str, str, str]] = []

    def fake_resolve(repo_id: str, revision: str | None = None) -> str:
        resolve_calls.append((repo_id, revision))
        return commit

    def fake_snapshot_download(
        repo_id: str,
        local_dir: str,
        *,
        revision: str,
    ) -> None:
        download_calls.append((repo_id, local_dir, revision))
        Path(local_dir, "config.json").write_text("{}")

    monkeypatch.setattr(snap_mod, "_resolve_snapshot_revision", fake_resolve)
    monkeypatch.setattr(snap_mod, "_snapshot_download", fake_snapshot_download)

    target = tmp_path / "MLX" / "repo"
    job = await snap_mod.start_snapshot_install("org/repo", target, revision="main")
    await job._task

    assert job.status == "completed"
    assert job.revision == commit
    assert resolve_calls == [("org/repo", "main")]
    assert download_calls == [("org/repo", str(target), commit)]


@pytest.mark.asyncio
async def test_snapshot_install_rejects_malformed_resolved_revision_before_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(
        snap_mod,
        "_resolve_snapshot_revision",
        lambda _repo_id, revision=None: "not-a-commit",
    )
    monkeypatch.setattr(
        snap_mod,
        "_snapshot_download",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    job = await snap_mod.start_snapshot_install("org/malformed", tmp_path / "repo")
    await job._task

    assert job.status == "failed"
    assert "revision" in (job.error or "").lower()
    assert job.revision is None
    assert calls == []
    assert not (tmp_path / "repo" / "config.json").exists()


@pytest.mark.asyncio
async def test_snapshot_install_fails_closed_when_revision_resolution_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        snap_mod,
        "_resolve_snapshot_revision",
        lambda _repo_id, revision=None: (_ for _ in ()).throw(
            RuntimeError("HF metadata unavailable")
        ),
    )

    job = await snap_mod.start_snapshot_install("org/unavailable", tmp_path / "repo")
    await job._task

    assert job.status == "failed"
    assert "metadata unavailable" in (job.error or "")
    assert job.revision is None


@pytest.mark.asyncio
async def test_start_snapshot_install_dedupes_in_flight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    unblock = threading.Event()

    def fake_snapshot_download(
        repo_id: str,
        local_dir: str,
        *,
        revision: str | None = None,
    ) -> None:
        unblock.wait(timeout=5)

    monkeypatch.setattr(snap_mod, "_snapshot_download", fake_snapshot_download)

    target = tmp_path / "Transformers" / "repo"
    first = await snap_mod.start_snapshot_install("org/repo", target)
    second = await snap_mod.start_snapshot_install("org/repo", target)

    assert first is second
    assert len(snap_mod.list_snapshot_installs()) == 1
    first.status = "completed"
    unblock.set()
    await asyncio.wait_for(first._task, timeout=5)


@pytest.mark.asyncio
async def test_start_snapshot_install_writes_and_removes_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started = threading.Event()
    unblock = threading.Event()

    def fake_snapshot_download(
        repo_id: str,
        local_dir: str,
        *,
        revision: str | None = None,
    ) -> None:
        started.set()
        unblock.wait(timeout=5)
        Path(local_dir, "config.json").write_text("{}")

    monkeypatch.setattr(snap_mod, "_snapshot_download", fake_snapshot_download)

    target = tmp_path / "MLX" / "repo"
    job = await snap_mod.start_snapshot_install("mlx-community/Test-MLX", target)

    assert await asyncio.to_thread(started.wait, 5)
    meta_path = target / ".snapshot-install.meta"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["job_id"] == job.job_id
    assert meta["repo_id"] == "mlx-community/Test-MLX"
    assert meta["target_path"] == str(target)
    assert meta["revision"] == "a" * 40

    unblock.set()
    await asyncio.wait_for(job._task, timeout=5)

    assert job.status == "completed"
    assert not meta_path.exists()


@pytest.mark.asyncio
async def test_cancel_snapshot_install_requests_stop_and_finishes_cancelled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    started = threading.Event()
    unblock = threading.Event()

    def fake_snapshot_download(
        repo_id: str,
        local_dir: str,
        *,
        revision: str | None = None,
    ) -> None:
        started.set()
        unblock.wait(timeout=5)
        Path(local_dir, "config.json").write_text("{}")

    monkeypatch.setattr(snap_mod, "_snapshot_download", fake_snapshot_download)

    job = await snap_mod.start_snapshot_install("org/cancellable", tmp_path / "repo")
    assert await asyncio.to_thread(started.wait, 5)

    ok, detail = snap_mod.cancel_snapshot_install(job.job_id)

    assert ok is True
    assert "Cancellation requested" in detail
    assert job.cancel_requested is True

    unblock.set()
    await asyncio.wait_for(job._task, timeout=5)

    assert job.status == "cancelled"
    assert any("cancel" in line.lower() for line in job.log_tail)


@pytest.mark.asyncio
async def test_reconcile_snapshot_installs_rebuilds_interrupted_sidecar(
    tmp_path: Path,
) -> None:
    target = tmp_path / "Transformers" / "org__repo"
    target.mkdir(parents=True)
    (target / ".snapshot-install.meta").write_text(
        json.dumps(
            {
                "job_id": "snap-restart",
                "repo_id": "org/repo",
                "target_path": str(target),
            }
        ),
        encoding="utf-8",
    )

    reconstructed = await snap_mod.reconcile_snapshot_installs(tmp_path)

    assert reconstructed == 1
    jobs = snap_mod.list_snapshot_installs()
    assert len(jobs) == 1
    assert jobs[0].job_id == "snap-restart"
    assert jobs[0].status == "cancelled"
    assert jobs[0].repo_id == "org/repo"
    assert "resume" in " ".join(jobs[0].log_tail).lower()


@pytest.mark.asyncio
async def test_reconcile_snapshot_installs_prunes_corrupt_sidecar(
    tmp_path: Path,
) -> None:
    target = tmp_path / "MLX" / "bad"
    target.mkdir(parents=True)
    meta_path = target / ".snapshot-install.meta"
    meta_path.write_text("{not-json", encoding="utf-8")

    reconstructed = await snap_mod.reconcile_snapshot_installs(tmp_path)

    assert reconstructed == 0
    assert not meta_path.exists()


@pytest.mark.asyncio
async def test_start_snapshot_install_skips_existing_non_empty_directory(
    tmp_path: Path,
) -> None:
    target = tmp_path / "MLX" / "ready"
    target.mkdir(parents=True)
    (target / "config.json").write_text("{}")
    (target / "model.safetensors").write_bytes(b"weights")

    job = await snap_mod.start_snapshot_install("org/ready", target)

    assert job.status == "completed"
    assert job._task is None
    assert "already contains model files" in " ".join(job.log_tail)


@pytest.mark.asyncio
async def test_start_snapshot_install_repairs_config_only_partial_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str]] = []
    target = tmp_path / "MLX" / "partial"
    target.mkdir(parents=True)
    (target / "config.json").write_text("{}")
    (target / "README.md").write_text("# partial")
    (target / ".cache").mkdir()

    def fake_snapshot_download(
        repo_id: str,
        local_dir: str,
        *,
        revision: str | None = None,
    ) -> None:
        calls.append((repo_id, local_dir))
        Path(local_dir, "model.safetensors").write_bytes(b"weights")

    monkeypatch.setattr(snap_mod, "_snapshot_download", fake_snapshot_download)

    job = await snap_mod.start_snapshot_install("org/partial", target)
    await asyncio.wait_for(job._task, timeout=5)

    assert job.status == "completed"
    assert calls == [("org/partial", str(target))]
    assert any("Downloading org/partial" in line for line in job.log_tail)


@pytest.mark.asyncio
async def test_start_snapshot_install_skips_existing_single_gguf_snapshot(
    tmp_path: Path,
) -> None:
    target = tmp_path / "GGUF" / "ready"
    target.mkdir(parents=True)
    (target / "model.gguf").write_bytes(b"weights")

    job = await snap_mod.start_snapshot_install("org/gguf", target)

    assert job.status == "completed"
    assert job._task is None


@pytest.mark.asyncio
async def test_existing_snapshot_skip_does_not_require_huggingface_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "GGUF" / "offline"
    target.mkdir(parents=True)
    (target / "model.gguf").write_bytes(b"weights")

    def unavailable(*_args, **_kwargs):
        raise AssertionError("complete local snapshots must not resolve online")

    monkeypatch.setattr(snap_mod, "_resolve_snapshot_revision", unavailable)

    job = await snap_mod.start_snapshot_install("org/offline", target)

    assert job.status == "completed"
    assert job.revision is None
    assert job._task is None


@pytest.mark.asyncio
async def test_start_snapshot_install_records_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_snapshot_download(
        repo_id: str,
        local_dir: str,
        *,
        revision: str | None = None,
    ) -> None:
        raise RuntimeError("network down")

    monkeypatch.setattr(snap_mod, "_snapshot_download", fake_snapshot_download)

    job = await snap_mod.start_snapshot_install("org/fail", tmp_path / "repo")
    await asyncio.wait_for(job._task, timeout=5)

    assert job.status == "failed"
    assert "network down" in (job.error or "")


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("DEEPER_NOTEBOOK_MODEL_DIR", str(tmp_path))

    async def fake_start_snapshot_install(repo_id: str, target_path: Path):
        return types.SimpleNamespace(
            job_id="snap-1",
            repo_id=repo_id,
            target_path=str(target_path),
            status="queued",
            error=None,
            log_tail=["queued"],
        )

    monkeypatch.setattr(
        local_models_router,
        "start_snapshot_install",
        fake_start_snapshot_install,
        raising=False,
    )
    app = FastAPI()
    app.include_router(local_models_router.router)
    return TestClient(app)


def test_snapshot_install_endpoint_starts_job_inside_model_dir(
    client: TestClient,
    tmp_path: Path,
) -> None:
    response = client.post(
        "/api/local-models/snapshot-installs",
        json={
            "repo_id": "mlx-community/Test-MLX",
            "target_path": str(tmp_path / "MLX" / "mlx-community__Test-MLX"),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == "snap-1"
    assert body["repo_id"] == "mlx-community/Test-MLX"
    assert body["status"] == "queued"


def test_snapshot_install_endpoint_exposes_immutable_revision(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commit = "b" * 40

    async def fake_start_snapshot_install(repo_id: str, target_path: Path):
        return types.SimpleNamespace(
            job_id="snap-revision",
            repo_id=repo_id,
            target_path=str(target_path),
            revision=commit,
            status="queued",
            error=None,
            log_tail=[],
        )

    monkeypatch.setattr(
        local_models_router,
        "start_snapshot_install",
        fake_start_snapshot_install,
        raising=False,
    )
    response = client.post(
        "/api/local-models/snapshot-installs",
        json={
            "repo_id": "org/repo",
            "target_path": str(tmp_path / "MLX" / "repo"),
        },
    )

    assert response.status_code == 200
    assert response.json()["revision"] == commit


@pytest.mark.parametrize(
    "repo_id",
    ["no-slash", "../../etc/passwd", "org/name?bad=1", "org/name/extra"],
)
def test_snapshot_install_endpoint_rejects_bad_repo_ids(
    client: TestClient,
    tmp_path: Path,
    repo_id: str,
) -> None:
    response = client.post(
        "/api/local-models/snapshot-installs",
        json={"repo_id": repo_id, "target_path": str(tmp_path / "repo")},
    )

    assert response.status_code == 400
    assert "repo_id" in response.json()["detail"]


def test_snapshot_install_endpoint_rejects_target_outside_model_dir(
    client: TestClient,
    tmp_path: Path,
) -> None:
    response = client.post(
        "/api/local-models/snapshot-installs",
        json={
            "repo_id": "org/repo",
            "target_path": str(tmp_path.parent / "repo"),
        },
    )

    assert response.status_code == 400
    assert "configured model directory" in response.json()["detail"]


def test_snapshot_install_list_reconciles_interrupted_sidecars(
    client: TestClient,
    tmp_path: Path,
) -> None:
    target = tmp_path / "MLX" / "org__repo"
    target.mkdir(parents=True)
    (target / ".snapshot-install.meta").write_text(
        json.dumps(
            {
                "job_id": "snap-reconciled",
                "repo_id": "org/repo",
                "target_path": str(target),
            }
        ),
        encoding="utf-8",
    )

    response = client.get("/api/local-models/snapshot-installs")

    assert response.status_code == 200, response.text
    installs = response.json()["snapshot_installs"]
    assert installs[0]["job_id"] == "snap-reconciled"
    assert installs[0]["status"] == "cancelled"


def test_snapshot_install_cancel_endpoint_requests_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    monkeypatch.setattr(
        local_models_router,
        "get_snapshot_install",
        lambda job_id: types.SimpleNamespace(job_id=job_id),
        raising=False,
    )
    monkeypatch.setattr(
        local_models_router,
        "cancel_snapshot_install",
        lambda job_id: (True, "Cancellation requested"),
        raising=False,
    )

    response = client.post("/api/local-models/snapshot-installs/snap-1/cancel")

    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True, "detail": "Cancellation requested"}


def test_snapshot_install_cancel_endpoint_conflicts_for_terminal_job(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    monkeypatch.setattr(
        local_models_router,
        "get_snapshot_install",
        lambda job_id: types.SimpleNamespace(job_id=job_id),
        raising=False,
    )
    monkeypatch.setattr(
        local_models_router,
        "cancel_snapshot_install",
        lambda job_id: (False, "Job already completed"),
        raising=False,
    )

    response = client.post("/api/local-models/snapshot-installs/snap-1/cancel")

    assert response.status_code == 409
    assert "already completed" in response.json()["detail"]
