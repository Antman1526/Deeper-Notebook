"""ONP v0.6.25 — Tests for launcher.log handling.

Two bugs fixed in desktop/app.py:
  1. _setup_launcher_log_handler was missing entirely — launcher.log
     was promised by docstrings but never actually populated except for
     the one-line .write_text on supervisor crash.
  2. That .write_text() also OVERWROTE the file every time, losing the
     prior failure trace AND any accumulated FileHandler lines.

These tests confirm:
  - _setup_launcher_log_handler is idempotent (no duplicate handlers)
  - Calling it actually causes desktop.* logger output to land in the
    file with the expected format
  - The handler is RotatingFileHandler with sensible defaults
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from desktop.app import _setup_launcher_log_handler


@pytest.fixture(autouse=True)
def _detach_handlers():
    """Each test gets a clean `desktop` logger — strip prior handlers."""
    log = logging.getLogger("desktop")
    saved = list(log.handlers)
    log.handlers.clear()
    saved_level = log.level
    yield
    log.handlers.clear()
    for h in saved:
        log.addHandler(h)
    log.setLevel(saved_level)


def test_handler_writes_to_file(tmp_path):
    log_path = tmp_path / "launcher.log"
    _setup_launcher_log_handler(log_path)
    logging.getLogger("desktop.launcher").info("hello from supervisor")
    # Flush so the file is on disk before we read.
    for h in logging.getLogger("desktop").handlers:
        h.flush()
    contents = log_path.read_text()
    assert "hello from supervisor" in contents
    assert "[desktop.launcher]" in contents
    assert "INFO" in contents


def test_handler_is_idempotent(tmp_path):
    log_path = tmp_path / "launcher.log"
    _setup_launcher_log_handler(log_path)
    _setup_launcher_log_handler(log_path)
    _setup_launcher_log_handler(log_path)
    file_handlers = [
        h
        for h in logging.getLogger("desktop").handlers
        if isinstance(h, RotatingFileHandler)
        and getattr(h, "baseFilename", "") == str(log_path)
    ]
    assert len(file_handlers) == 1, (
        f"Expected exactly 1 handler for {log_path}; got {len(file_handlers)}"
    )


def test_handler_is_rotating_with_sensible_cap(tmp_path):
    log_path = tmp_path / "launcher.log"
    _setup_launcher_log_handler(log_path)
    file_handlers = [
        h
        for h in logging.getLogger("desktop").handlers
        if isinstance(h, RotatingFileHandler)
        and getattr(h, "baseFilename", "") == str(log_path)
    ]
    assert len(file_handlers) == 1
    handler = file_handlers[0]
    # Don't pin to exact values, just sanity-check the cap is in MB-range
    # and at least one backup file is kept.
    assert handler.maxBytes >= 1024 * 1024
    assert handler.maxBytes <= 100 * 1024 * 1024
    assert handler.backupCount >= 1


def test_logger_level_set_to_at_least_info(tmp_path):
    """If the launcher's root logger is left at the default WARNING level,
    auto_register's log.info calls (which the comments promise will land
    in launcher.log) get filtered out. The setup must lower the level
    to INFO when called."""
    log_path = tmp_path / "launcher.log"
    log = logging.getLogger("desktop")
    log.setLevel(logging.WARNING)
    _setup_launcher_log_handler(log_path)
    assert log.level <= logging.INFO


def test_handler_setup_creates_parent_dir_safely(tmp_path):
    """If log_dir gets passed a nested path that doesn't exist yet, we
    should still raise a clear error rather than silently failing. The
    caller in _phase_load_config does mkdir(parents=True) before calling
    us, so the file's parent always exists in production. This test
    verifies that contract — if the parent doesn't exist, we expect the
    standard FileNotFoundError, NOT a silent swallow."""
    log_path = tmp_path / "does" / "not" / "exist" / "launcher.log"
    with pytest.raises((FileNotFoundError, OSError)):
        _setup_launcher_log_handler(log_path)
        # Trigger an actual write; RotatingFileHandler may delay-open.
        logging.getLogger("desktop").info("test")
        for h in logging.getLogger("desktop").handlers:
            h.flush()
