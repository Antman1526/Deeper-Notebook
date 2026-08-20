"""v0.8.39 — Local GGUF model inventory + metadata.

Read-only module backing the /local-models/inventory endpoint and the
new Settings → Local Models page. Lets users see what's installed in
the configured model dir, with capability hints (architecture, quant,
context length, file size).

Companion modules (deferred to v0.8.39b / v0.8.39c):
  - downloader.py — HuggingFace download via async job.
  - hot_swap.py   — signal launcher to re-spawn chat sidecar with a
                    different GGUF without app restart.

This module is read-only and pure — no I/O outside the configured
model_dir, no mutation of any model state. Safe to call from the
FastAPI event loop in a `to_thread` shim.
"""

from deeper_notebook.local_models.benchmarks import (
    BenchmarkJob,
    BenchmarkMeasurement,
    BenchmarkResult,
    benchmark_history_path,
    clear_benchmark_jobs,
    get_benchmark_job,
    list_benchmark_jobs,
    load_benchmark_history,
    resolve_measured_model_id,
    save_benchmark_history,
    start_benchmark,
)
from deeper_notebook.local_models.contracts import (
    ExternalModelRootTrust,
    ModelReadinessAssessment,
    ModelReadinessEvidence,
    classify_model_readiness,
    trust_record_matches,
)
from deeper_notebook.local_models.downloader import (
    RECOMMENDATIONS,
    DownloadJob,
    cancel_job,
    get_job,
    list_jobs,
    reconcile_jobs,
    start_download,
)
from deeper_notebook.local_models.gguf_metadata import (
    GGUFMetadata,
    parse_gguf_metadata,
    parse_quant_from_filename,
)
from deeper_notebook.local_models.inventory import (
    LocalModelInfo,
    LocalModelReadinessInfo,
    build_readiness_inventory,
    enumerate_models,
)
from deeper_notebook.local_models.manifest import (
    ManifestModelEntry,
    ManifestRecommendation,
    ManifestReconciliationEntry,
    ManifestRowApplyResult,
    ManifestRowError,
    ManifestRowPreview,
    append_manifest_row,
    build_manifest_recommendations,
    build_manifest_reconciliation,
    find_manifest_matches,
    find_unmatched_manifest_entries,
    load_model_manifest,
    manifest_lifecycle_state,
    model_manifest_path,
    parse_model_manifest,
    preview_manifest_row,
)
from deeper_notebook.local_models.role_routing import (
    ModelRoleRecommendation,
    recommend_model_roles,
)
from deeper_notebook.local_models.snapshot_installer import (
    SnapshotInstallJob,
    cancel_snapshot_install,
    get_snapshot_install,
    list_snapshot_installs,
    reconcile_snapshot_installs,
    reset_snapshot_installs_for_tests,
    start_snapshot_install,
)

__all__ = [
    "DownloadJob",
    "GGUFMetadata",
    "LocalModelInfo",
    "LocalModelReadinessInfo",
    "BenchmarkJob",
    "BenchmarkMeasurement",
    "BenchmarkResult",
    "ModelRoleRecommendation",
    "SnapshotInstallJob",
    "ManifestModelEntry",
    "ManifestRecommendation",
    "ManifestReconciliationEntry",
    "ManifestRowApplyResult",
    "ManifestRowError",
    "ManifestRowPreview",
    "RECOMMENDATIONS",
    "append_manifest_row",
    "benchmark_history_path",
    "build_readiness_inventory",
    "build_manifest_recommendations",
    "build_manifest_reconciliation",
    "cancel_job",
    "cancel_snapshot_install",
    "clear_benchmark_jobs",
    "classify_model_readiness",
    "ExternalModelRootTrust",
    "ModelReadinessAssessment",
    "ModelReadinessEvidence",
    "enumerate_models",
    "get_benchmark_job",
    "get_job",
    "get_snapshot_install",
    "find_manifest_matches",
    "find_unmatched_manifest_entries",
    "load_benchmark_history",
    "load_model_manifest",
    "manifest_lifecycle_state",
    "list_benchmark_jobs",
    "list_jobs",
    "list_snapshot_installs",
    "parse_gguf_metadata",
    "parse_model_manifest",
    "parse_quant_from_filename",
    "preview_manifest_row",
    "recommend_model_roles",
    "reconcile_snapshot_installs",
    "reconcile_jobs",
    "resolve_measured_model_id",
    "reset_snapshot_installs_for_tests",
    "save_benchmark_history",
    "model_manifest_path",
    "start_benchmark",
    "start_download",
    "start_snapshot_install",
    "trust_record_matches",
]
