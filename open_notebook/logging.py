"""Centralized loguru configuration for Open Notebook Plus.

v0.7.14 — for local-deploy use (the project's documented target), the
launcher and API both run as long-lived subprocesses on the user's
machine. Without a configured sink, loguru's default is stderr only —
when something breaks at 2am the user has nothing to `tail`. The README
references `~/.open-notebook-plus/logs/*.log` but no code wrote there.

This module wires loguru to:
  - rotated file sinks under `~/.open-notebook-plus/logs/<component>.log`
  - rotation: 20 MB per file
  - retention: 14 days
  - compression: zstd (or gzip on platforms without zstandard)
  - configurable level via ONP_LOG_LEVEL (default INFO)
  - optional JSON sink via ONP_LOG_JSON=1 for log aggregators

Each process calls `configure_logging("api" | "launcher" | "worker" | ...)`
at startup. The stderr sink is preserved so docker/systemd users still
see live output. Idempotent — safe to call multiple times (e.g. when
reloading uvicorn).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger


_DEFAULT_ROTATION = "20 MB"
_DEFAULT_RETENTION = "14 days"
_DEFAULT_LEVEL = "INFO"
# loguru only accepts stdlib-known compression names; gzip is always
# available. (zstd would need a different rotation/compression mechanism.)
_DEFAULT_COMPRESSION = "gz"


def default_log_dir() -> Path:
    """Resolve the log directory. Honors ONP_LOG_DIR if set, else uses
    the standard ~/.open-notebook-plus/logs path.

    v0.7.24 — improved Docker fallback. Previously, when HOME and
    USERPROFILE were both unset (common in stripped-down containers
    using distroless/scratch bases), this returned `cwd/.logs/`.
    For the standard `/app` workdir that put logs at `/app/.logs`,
    invisible to host volume mounts unless the operator happened to
    bind-mount that exact path. Result: logs were *hidden* compared
    to the pre-v0.7.14 stderr-only behavior that `docker logs`
    captured cleanly.

    Now the Docker-style fallback prefers `/var/log/open-notebook-plus`
    (the conventional container log location). If that path isn't
    writable (e.g. read-only filesystem), the caller can override via
    ONP_LOG_DIR.
    """
    raw = os.environ.get("ONP_LOG_DIR")
    if raw:
        return Path(raw).expanduser()
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        # Container fallback: use /var/log/<app>. This is the
        # conventional Linux container log location; ops folk know to
        # mount/scrape it. If write fails (read-only fs), the caller
        # can set ONP_LOG_DIR explicitly.
        return Path("/var/log/open-notebook-plus")
    return Path(home) / ".open-notebook-plus" / "logs"


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
        level: Override level; defaults to ONP_LOG_LEVEL or INFO.
        rotation: loguru rotation policy. Default "20 MB".
        retention: loguru retention policy. Default "14 days".
        keep_stderr: When True (default), preserve a stderr sink for
            interactive runs (uvicorn --reload, dev). Set False in
            release builds if you only want files.
        json_sink: When True, emit a parallel `.jsonl` file with
            `serialize=True` for log-aggregator consumption. Defaults
            to ONP_LOG_JSON=1.

    Returns:
        The resolved log directory (useful for tests / docs).
    """
    if log_dir is None:
        log_dir = default_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    if level is None:
        level = os.environ.get("ONP_LOG_LEVEL", _DEFAULT_LEVEL).upper()

    if json_sink is None:
        json_sink = os.environ.get("ONP_LOG_JSON", "").lower() in {
            "1", "true", "yes", "on"
        }

    # Sanitize component for filesystem use — keep alnum + dash + underscore.
    safe_component = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in component.lower()
    ) or "app"

    # Clear any prior config so this function is idempotent — important
    # when uvicorn reloads or when tests configure logging repeatedly.
    logger.remove()

    if keep_stderr:
        logger.add(
            sys.stderr,
            level=level,
            backtrace=False,
            diagnose=False,  # avoid leaking local variables in tracebacks
        )

    compression = _DEFAULT_COMPRESSION
    text_path = log_dir / f"{safe_component}.log"
    logger.add(
        text_path,
        level=level,
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
        safe_component, level, log_dir, rotation, retention, json_sink,
    )
    return log_dir
