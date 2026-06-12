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
from open_notebook.local_models.downloader import (
    RECOMMENDATIONS,
    DownloadJob,
    cancel_job,
    get_job,
    list_jobs,
    reconcile_jobs,
    start_download,
)
from open_notebook.local_models.gguf_metadata import (
    GGUFMetadata,
    parse_gguf_metadata,
    parse_quant_from_filename,
)
from open_notebook.local_models.inventory import (
    LocalModelInfo,
    enumerate_models,
)

__all__ = [
    "DownloadJob",
    "GGUFMetadata",
    "LocalModelInfo",
    "RECOMMENDATIONS",
    "cancel_job",
    "enumerate_models",
    "get_job",
    "list_jobs",
    "parse_gguf_metadata",
    "parse_quant_from_filename",
    "reconcile_jobs",
    "start_download",
]
