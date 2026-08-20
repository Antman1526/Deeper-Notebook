"""v0.8.67l — tests for the self-healing SurrealDB live-query repair.

Covers the pure, deterministic logic: crash-signature detection, the one-shot
flag lifecycle, and auto_repair's safe-guard early returns. The full
export/move/reimport happy path needs a real surreal binary and is exercised
by scripts/repair_desktop_db.sh + the launcher in the field, not here.
"""

from __future__ import annotations

import logging

import pytest

from desktop import db_repair

# --- crash-signature detection -------------------------------------------------


def test_detects_the_lq_key_collision():
    sample = (
        "ERROR worker.py:142 db.live('command', diff=True)\n"
        "InternalError: There was a problem with the database: "
        "The key being inserted already exists"
    )
    assert db_repair.looks_like_lq_corruption(sample) is True


def test_detection_is_case_insensitive():
    assert (
        db_repair.looks_like_lq_corruption("The Key Being Inserted Already Exists")
        is True
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        "worker started; subscribing to commands",
        "ConnectionError: connection refused",
        "some unrelated 'already exists' note about a file",  # not the LQ phrase
    ],
)
def test_ignores_unrelated_or_empty_logs(text):
    assert db_repair.looks_like_lq_corruption(text) is False


# --- one-shot flag lifecycle ---------------------------------------------------


def test_flag_set_check_clear_roundtrip(tmp_path):
    assert db_repair.needs_repair(tmp_path) is False
    db_repair.set_needs_repair(tmp_path)
    assert db_repair.needs_repair(tmp_path) is True
    assert db_repair.flag_path(tmp_path).exists()
    db_repair.clear_needs_repair(tmp_path)
    assert db_repair.needs_repair(tmp_path) is False


def test_clear_is_idempotent_when_absent(tmp_path):
    # Clearing a flag that was never set must not raise.
    db_repair.clear_needs_repair(tmp_path)
    assert db_repair.needs_repair(tmp_path) is False


# --- auto_repair safe-guard early returns -------------------------------------


def test_auto_repair_returns_false_when_binary_missing(tmp_path):
    data = tmp_path / "surreal_data"
    data.mkdir()
    ok = db_repair.auto_repair(
        surreal_bin=tmp_path / "does-not-exist",
        data_dir=data,
        backup_dir=tmp_path / "backups",
        surreal_user="root",
        surreal_password="pw",
        ts="20260601-000000",
        log=logging.getLogger("test"),
    )
    assert ok is False
    # Nothing destructive happened: the data dir is untouched.
    assert data.exists()


def test_auto_repair_returns_false_when_data_dir_missing(tmp_path):
    fake_bin = tmp_path / "surreal-darwin-arm64"
    fake_bin.write_text("#!/bin/sh\n")  # exists, but data dir does not
    ok = db_repair.auto_repair(
        surreal_bin=fake_bin,
        data_dir=tmp_path / "surreal_data",  # absent
        backup_dir=tmp_path / "backups",
        surreal_user="root",
        surreal_password="pw",
        ts="20260601-000000",
        log=logging.getLogger("test"),
    )
    assert ok is False
