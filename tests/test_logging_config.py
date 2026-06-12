"""v0.7.14 — regression tests for centralized loguru file logging.

Before v0.7.14, the API process imported `from loguru import logger`
but never called `logger.add(<file>)` — so the only sink was stderr.
For local-deploy use (the project's target), this meant the README's
`tail ~/.open-notebook-plus/logs/api.log` advice never worked because
no code wrote there. `configure_logging("api")` now wires a rotated
file sink at startup.
"""
from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from open_notebook import logging as onp_logging


def test_default_log_dir_uses_home(monkeypatch, tmp_path):
    """Default location is ~/.open-notebook-plus/logs without ONP_LOG_DIR."""
    monkeypatch.delenv("ONP_LOG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("USERPROFILE", raising=False)
    assert onp_logging.default_log_dir() == tmp_path / ".open-notebook-plus" / "logs"


def test_default_log_dir_respects_env(monkeypatch, tmp_path):
    """ONP_LOG_DIR overrides the home-relative default."""
    monkeypatch.setenv("ONP_LOG_DIR", str(tmp_path / "custom"))
    assert onp_logging.default_log_dir() == tmp_path / "custom"


def test_configure_logging_creates_dir_and_file(monkeypatch, tmp_path):
    """After configure, the component file exists and INFO logs land there."""
    monkeypatch.setenv("ONP_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("ONP_LOG_JSON", raising=False)

    out_dir = onp_logging.configure_logging("api", keep_stderr=False)
    assert out_dir == tmp_path
    log_path = tmp_path / "api.log"
    assert log_path.exists()

    test_message = "v0.7.14-logging-marker-xyz"
    logger.info(test_message)
    # loguru's `enqueue=True` makes writes async; force flush by
    # removing handlers, which closes the sink.
    logger.remove()

    assert test_message in log_path.read_text()


def test_configure_logging_is_idempotent(monkeypatch, tmp_path):
    """Calling configure twice doesn't duplicate handlers or crash."""
    monkeypatch.setenv("ONP_LOG_DIR", str(tmp_path))
    onp_logging.configure_logging("api", keep_stderr=False)
    onp_logging.configure_logging("api", keep_stderr=False)
    # Smoke: log doesn't double-write to the same file (we'd see the
    # marker twice if duplicate handlers existed).
    marker = "idem-marker-abc"
    logger.info(marker)
    logger.remove()
    text = (tmp_path / "api.log").read_text()
    assert text.count(marker) == 1


def test_json_sink_when_enabled(monkeypatch, tmp_path):
    """ONP_LOG_JSON=1 adds a parallel .jsonl file with serialized events."""
    monkeypatch.setenv("ONP_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("ONP_LOG_JSON", "1")

    onp_logging.configure_logging("worker", keep_stderr=False)
    logger.info("json-sink-test")
    logger.remove()

    json_path = tmp_path / "worker.jsonl"
    assert json_path.exists(), "JSON sink should be created when ONP_LOG_JSON=1"
    # First line should parse as JSON
    import json
    first = json_path.read_text().strip().split("\n")[0]
    parsed = json.loads(first)
    assert "record" in parsed or "text" in parsed  # loguru's serialize shape


def test_json_sink_disabled_by_default(monkeypatch, tmp_path):
    """Without ONP_LOG_JSON, no .jsonl file is created."""
    monkeypatch.setenv("ONP_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("ONP_LOG_JSON", raising=False)

    onp_logging.configure_logging("api", keep_stderr=False)
    logger.info("plain-only")
    logger.remove()

    assert not (tmp_path / "api.jsonl").exists()


def test_component_name_sanitized(monkeypatch, tmp_path):
    """Slashes and unicode in the component name don't escape the log dir."""
    monkeypatch.setenv("ONP_LOG_DIR", str(tmp_path))
    onp_logging.configure_logging("../etc/passwd", keep_stderr=False)
    logger.info("safe")
    logger.remove()
    # The file lives under tmp_path with a sanitized name; nothing
    # outside tmp_path got created.
    files = list(tmp_path.iterdir())
    assert all(f.parent == tmp_path for f in files)
    # And nothing escaped:
    assert not (tmp_path.parent / "etc").exists()


def test_log_level_respects_env(monkeypatch, tmp_path):
    """ONP_LOG_LEVEL=WARNING means DEBUG/INFO are filtered out."""
    monkeypatch.setenv("ONP_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("ONP_LOG_LEVEL", "WARNING")

    onp_logging.configure_logging("api", keep_stderr=False)
    logger.info("info-message-should-be-filtered")
    logger.warning("warning-message-should-appear")
    logger.remove()

    text = (tmp_path / "api.log").read_text()
    assert "warning-message-should-appear" in text
    assert "info-message-should-be-filtered" not in text


def test_missing_home_falls_back_to_container_path(monkeypatch, tmp_path):
    """v0.7.24 — when neither HOME nor USERPROFILE is set (typical
    inside distroless/scratch containers), fall back to the
    conventional Linux container log location `/var/log/<app>`
    rather than cwd/.logs. The previous behavior put logs at
    /app/.logs in a Docker workdir — invisible to host volume mounts
    unless the operator bind-mounted exactly that path."""
    monkeypatch.delenv("ONP_LOG_DIR", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.chdir(tmp_path)  # cwd should NOT be used

    result = onp_logging.default_log_dir()
    assert result == Path("/var/log/open-notebook-plus")
