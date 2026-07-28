from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from desktop.build.verify_windows_uninstall import (
    ResidualInstallError,
    wait_for_install_directory_removal,
)


def test_waits_for_asynchronous_uninstaller_cleanup(tmp_path: Path) -> None:
    install_dir = tmp_path / "installed-app"
    install_dir.mkdir()
    uninstaller = install_dir / "uninstaller.tmp"
    uninstaller.write_text("pending", encoding="utf-8")

    def finish_cleanup() -> None:
        time.sleep(0.05)
        uninstaller.unlink()
        install_dir.rmdir()

    worker = threading.Thread(target=finish_cleanup)
    worker.start()
    try:
        wait_for_install_directory_removal(
            install_dir,
            timeout_seconds=1,
            poll_seconds=0.01,
        )
    finally:
        worker.join()


def test_reports_persistent_install_residue(tmp_path: Path) -> None:
    install_dir = tmp_path / "installed-app"
    residue = install_dir / "runtime" / "leftover.log"
    residue.parent.mkdir(parents=True)
    residue.write_text("still present", encoding="utf-8")

    with pytest.raises(ResidualInstallError) as exc_info:
        wait_for_install_directory_removal(
            install_dir,
            timeout_seconds=0,
            poll_seconds=0,
        )

    message = str(exc_info.value)
    assert "runtime" in message
    assert "runtime/leftover.log" in message
