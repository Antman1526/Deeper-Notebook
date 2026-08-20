"""Centralized loguru configuration for Deeper Notebook.

v0.7.14 — for local-deploy use (the project's documented target), the
launcher and API both run as long-lived subprocesses on the user's
machine. Without a configured sink, loguru's default is stderr only —
when something breaks at 2am the user has nothing to `tail`. The README
references `~/.deeper-notebook/logs/*.log` but no code wrote there.

This module wires loguru to:
  - rotated file sinks under `~/.deeper-notebook/logs/<component>.log`
  - rotation: 20 MB per file
  - retention: 14 days
  - compression: zstd (or gzip on platforms without zstandard)
  - configurable level via DEEPER_NOTEBOOK_LOG_LEVEL (default INFO)
  - optional JSON sink via DEEPER_NOTEBOOK_LOG_JSON=1 for log aggregators

Legacy environment spellings remain fallback-only through the central
resolver. Canonical DEEPER_NOTEBOOK_* names always take precedence.

Each process calls `configure_logging("api" | "launcher" | "worker" | ...)`
at startup. The stderr sink is preserved so docker/systemd users still
see live output. Idempotent — safe to call multiple times (e.g. when
reloading uvicorn).
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

from loguru import logger

from deeper_notebook.environment import LegacyEnvironmentWarning, resolve_env
from desktop.data_root import active_data_root

_DEFAULT_ROTATION = "20 MB"
_DEFAULT_RETENTION = "14 days"
_DEFAULT_LEVEL = "INFO"
# loguru only accepts stdlib-known compression names; gzip is always
# available. (zstd would need a different rotation/compression mechanism.)
_DEFAULT_COMPRESSION = "gz"
_CANONICAL_CONTAINER_LOG_DIR = Path("/var/log/deeper-notebook")
_LEGACY_CONTAINER_LOG_DIR = Path("/var/log/open-notebook-plus")

# v0.7.120 — Custom log format with request_id column for correlation.
# The RequestIDMiddleware (api/middleware/request_id.py) calls
# `logger.contextualize(request_id=...)` to set `extra[request_id]`
# for the duration of each HTTP request. Code paths outside a request
# (startup, workers, scheduled tasks) emit with the process-wide
# default `"-"` set via `logger.configure(extra=...)` below.
#
# Format renders as:
#   2026-05-17 23:01:00.123 | INFO     | req=abc12345 | api.routers.studio:foo:42 - message
#
# The `:<8` width keeps columns aligned even when no request is in flight.
_LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<yellow>req={extra[request_id]:<8}</yellow> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)
# The file sink doesn't render ANSI color tags, but loguru strips them
# automatically when writing to a non-TTY sink.


def default_log_dir() -> Path:
    """Resolve the log directory. Honors DEEPER_NOTEBOOK_LOG_DIR if set, else uses
    the standard ~/.deeper-notebook/logs path.

    v0.7.24 — improved Docker fallback. Previously, when HOME and
    USERPROFILE were both unset (common in stripped-down containers
    using distroless/scratch bases), this returned `cwd/.logs/`.
    For the standard `/app` workdir that put logs at `/app/.logs`,
    invisible to host volume mounts unless the operator happened to
    bind-mount that exact path. Result: logs were *hidden* compared
    to the pre-v0.7.14 stderr-only behavior that `docker logs`
    captured cleanly.

    The container fallback uses `/var/log/deeper-notebook`. An existing
    `/var/log/open-notebook-plus` directory is honored only when the
    canonical directory does not yet exist, preserving upgrades without
    making the legacy path the default. Operators should override with
    DEEPER_NOTEBOOK_LOG_DIR; deprecated spellings are handled centrally.
    """
    raw = resolve_env("DEEPER_NOTEBOOK_LOG_DIR")
    if raw:
        return Path(raw).expanduser()
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        if (
            _LEGACY_CONTAINER_LOG_DIR.exists()
            and not _CANONICAL_CONTAINER_LOG_DIR.exists()
        ):
            warnings.warn(
                f"{_LEGACY_CONTAINER_LOG_DIR} is deprecated; migrate logs to "
                f"{_CANONICAL_CONTAINER_LOG_DIR}.",
                LegacyEnvironmentWarning,
                stacklevel=2,
            )
            return _LEGACY_CONTAINER_LOG_DIR
        return _CANONICAL_CONTAINER_LOG_DIR
    return active_data_root() / "logs"


def configure_logging(
    component: str,
    *,
    log_dir: Path | None = None,
    level: str | None = None,
    rotation: str = _DEFAULT_ROTATION,
    retention: str = _DEFAULT_RETENTION,
    keep_stderr: bool = True,
    json_sink: bool | None = None,
) -> Path:
    """Configure loguru for one process.

    Args:
        component: Short tag used in the filename (e.g. "api", "launcher",
            "worker"). Lowercased and sanitized.
        log_dir: Override directory; defaults to default_log_dir().
        level: Override level; defaults to DEEPER_NOTEBOOK_LOG_LEVEL or INFO.
        rotation: loguru rotation policy. Default "20 MB".
        retention: loguru retention policy. Default "14 days".
        keep_stderr: When True (default), preserve a stderr sink for
            interactive runs (uvicorn --reload, dev). Set False in
            release builds if you only want files.
        json_sink: When True, emit a parallel `.jsonl` file with
            `serialize=True` for log-aggregator consumption. Defaults
            to DEEPER_NOTEBOOK_LOG_JSON=1.

    Returns:
        The resolved log directory (useful for tests / docs).
    """
    if log_dir is None:
        log_dir = default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    if level is None:
        level = resolve_env("DEEPER_NOTEBOOK_LOG_LEVEL", _DEFAULT_LEVEL).upper()

    if json_sink is None:
        json_sink = resolve_env("DEEPER_NOTEBOOK_LOG_JSON", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    # Sanitize component for filesystem use — keep alnum + dash + underscore.
    safe_component = (
        "".join(c if c.isalnum() or c in "-_" else "_" for c in component.lower())
        or "app"
    )

    # Clear any prior config so this function is idempotent — important
    # when uvicorn reloads or when tests configure logging repeatedly.
    logger.remove()

    # v0.7.120 — Process-wide default for the request_id extra field.
    # Without this, any log call outside a RequestIDMiddleware-wrapped
    # request (startup, workers, scheduled tasks, tests) would raise
    # KeyError when the format string tries to substitute
    # extra[request_id]. The default "-" makes those lines self-evident
    # as "not in a request context".
    logger.configure(extra={"request_id": "-"})

    if keep_stderr:
        logger.add(
            sys.stderr,
            level=level,
            format=_LOG_FORMAT,  # v0.7.120 — request_id column
            backtrace=False,
            diagnose=False,  # avoid leaking local variables in tracebacks
        )

    compression = _DEFAULT_COMPRESSION
    text_path = log_dir / f"{safe_component}.log"
    logger.add(
        text_path,
        level=level,
        format=_LOG_FORMAT,  # v0.7.120 — request_id column
        rotation=rotation,
        retention=retention,
        compression=compression,
        enqueue=True,  # non-blocking I/O; safe across threads/processes
        backtrace=False,
        diagnose=False,
        encoding="utf-8",
    )

    if json_sink:
        json_path = log_dir / f"{safe_component}.jsonl"
        logger.add(
            json_path,
            level=level,
            # JSON sink uses serialize=True which produces a structured
            # JSON object including the extra dict — no format string
            # needed (request_id lands in the JSON automatically).
            rotation=rotation,
            retention=retention,
            compression=compression,
            serialize=True,
            enqueue=True,
            encoding="utf-8",
        )

    logger.info(
        "loguru configured for component={} level={} dir={} rotation={} "
        "retention={} json={}",
        safe_component,
        level,
        log_dir,
        rotation,
        retention,
        json_sink,
    )
    return log_dir
