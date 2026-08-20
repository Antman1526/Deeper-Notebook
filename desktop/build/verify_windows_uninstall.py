"""Verify that an asynchronous Windows uninstaller removed its install tree."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Sequence


class ResidualInstallError(RuntimeError):
    """The uninstaller left persistent files or directories behind."""


def _residue_inventory(install_dir: Path) -> list[str]:
    try:
        return sorted(
            path.relative_to(install_dir).as_posix() for path in install_dir.rglob("*")
        )
    except OSError as exc:
        return [f"<inventory failed: {exc}>"]


def wait_for_install_directory_removal(
    install_dir: Path,
    *,
    timeout_seconds: float = 60,
    poll_seconds: float = 0.25,
) -> None:
    """Wait for an uninstaller's deferred self-cleanup, then fail with proof."""
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must not be negative")
    if poll_seconds < 0:
        raise ValueError("poll_seconds must not be negative")

    deadline = time.monotonic() + timeout_seconds
    while install_dir.exists() and time.monotonic() < deadline:
        time.sleep(poll_seconds)

    if not install_dir.exists():
        return

    residue = _residue_inventory(install_dir)
    details = ", ".join(residue) if residue else "<empty directory>"
    raise ResidualInstallError(
        f"Install directory remains after uninstall: {install_dir}; residue: {details}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=60)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    wait_for_install_directory_removal(
        args.install_dir,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
    )
    print(f"Uninstall cleanup verified: {args.install_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
