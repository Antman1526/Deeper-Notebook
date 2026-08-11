"""Deterministic bounded-history regressions for local-model job registries."""

from __future__ import annotations

from pathlib import Path

from deeper_notebook.local_models import benchmarks, downloader, snapshot_installer
from deeper_notebook.local_models.benchmarks import BenchmarkJob
from deeper_notebook.local_models.downloader import DownloadJob
from deeper_notebook.local_models.snapshot_installer import SnapshotInstallJob


def test_downloader_terminal_history_bound_preserves_active_jobs(monkeypatch):
    monkeypatch.setattr(downloader, "_MAX_TERMINAL_JOBS", 3)
    for index in range(5):
        downloader._JOBS[f"done-{index}"] = DownloadJob(
            job_id=f"done-{index}",
            repo_id="org/repo",
            filename=f"{index}.gguf",
            target_path=f"/{index}.gguf",
            status="completed",
        )
    active = DownloadJob(
        job_id="active",
        repo_id="org/repo",
        filename="active.gguf",
        target_path="/active.gguf",
        status="downloading",
    )
    downloader._JOBS[active.job_id] = active

    downloader._prune_job_history()

    assert downloader.get_job("active") is active
    assert sum(job.status == "completed" for job in downloader.list_jobs()) == 3


def test_snapshot_terminal_history_bound_preserves_queued_jobs(monkeypatch):
    monkeypatch.setattr(snapshot_installer, "_MAX_TERMINAL_JOBS", 2)
    for index in range(4):
        snapshot_installer._JOBS[f"done-{index}"] = SnapshotInstallJob(
            job_id=f"done-{index}",
            repo_id="org/repo",
            target_path=f"/{index}",
            status="completed",
        )
    active = SnapshotInstallJob(
        job_id="active",
        repo_id="org/repo",
        target_path="/active",
        status="downloading",
    )
    snapshot_installer._JOBS[active.job_id] = active

    snapshot_installer._prune_job_history()

    assert snapshot_installer.get_snapshot_install("active") is active
    assert sum(
        job.status == "completed"
        for job in snapshot_installer.list_snapshot_installs()
    ) == 2


def test_benchmark_terminal_history_bound_preserves_running_jobs(monkeypatch):
    monkeypatch.setattr(benchmarks, "_MAX_TERMINAL_JOBS", 2)
    for index in range(4):
        benchmarks._JOBS[f"done-{index}"] = BenchmarkJob(
            job_id=f"done-{index}", roles=["chat"], status="completed"
        )
    active = BenchmarkJob(job_id="active", roles=["chat"], status="running")
    benchmarks._JOBS[active.job_id] = active

    benchmarks._prune_job_history()

    assert benchmarks.get_benchmark_job("active") is active
    assert sum(
        job.status == "completed" for job in benchmarks.list_benchmark_jobs()
    ) == 2
