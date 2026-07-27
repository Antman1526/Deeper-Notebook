"""Explicit, recoverable migration for the renamed macOS application bundle.

The bundle identifier intentionally remains stable for this release.  If the
legacy and canonical bundle names coexist, detection exposes a one-time
recovery action.  Only explicit approval may move the exact legacy bundle to
the macOS Trash; this module never permanently deletes an application.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from deeper_notebook.identity import DATA_DIR_NAME
from desktop.paths import user_home

COMPATIBLE_BUNDLE_ID = "com.antman1526.open-notebook-plus"
LEGACY_APP_NAME = "Open Notebook Plus.app"
CANONICAL_APP_NAME = "Deeper Notebook.app"
RECEIPT_NAME = "app-bundle-replacement.json"
RECOVERY_ACTION = "move-legacy-app-to-trash"

AppReplacementState = Literal[
    "not-needed",
    "recovery-available",
    "already-recovered",
    "refused",
]


@dataclass(frozen=True)
class AppReplacementDecision:
    state: AppReplacementState
    applications_dir: Path
    legacy_app: Path
    canonical_app: Path
    receipt_path: Path
    show_recovery_card: bool = False
    action: str | None = None
    reason_code: str | None = None

    def as_payload(self) -> dict[str, object]:
        """Return the desktop-controller recovery-card contract."""
        payload = asdict(self)
        for key in ("applications_dir", "legacy_app", "canonical_app", "receipt_path"):
            payload[key] = str(payload[key])
        return payload


class AppReplacementRefused(RuntimeError):
    """Raised when an explicit replacement fails a safety precondition."""


def _canonical_data_root() -> Path:
    """Resolve the receipt root without triggering data-root migration."""
    return user_home() / DATA_DIR_NAME


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _completed_receipt(receipt_path: Path) -> bool:
    if not receipt_path.is_file() or receipt_path.is_symlink():
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(receipt, dict) and receipt.get("status") == "completed"


def _bundle_identifier(app: Path) -> str | None:
    if app.is_symlink() or not app.is_dir():
        return None
    contents = app / "Contents"
    plist_path = contents / "Info.plist"
    if contents.is_symlink() or plist_path.is_symlink() or not plist_path.is_file():
        return None
    try:
        with plist_path.open("rb") as plist_file:
            plist = plistlib.load(plist_file)
    except (OSError, plistlib.InvalidFileException):
        return None
    bundle_id = plist.get("CFBundleIdentifier") if isinstance(plist, dict) else None
    return bundle_id if isinstance(bundle_id, str) else None


def detect_legacy_app_replacement(
    applications_dir: Path = Path("/Applications"),
    data_root: Path | None = None,
) -> AppReplacementDecision:
    """Purely classify exact legacy/canonical bundle coexistence."""
    if data_root is None:
        data_root = _canonical_data_root()
    applications_dir = _absolute(applications_dir)
    data_root = _absolute(data_root)
    legacy_app = applications_dir / LEGACY_APP_NAME
    canonical_app = applications_dir / CANONICAL_APP_NAME
    receipt_path = data_root / RECEIPT_NAME

    if _completed_receipt(receipt_path):
        return AppReplacementDecision(
            "already-recovered",
            applications_dir,
            legacy_app,
            canonical_app,
            receipt_path,
            reason_code="completed-receipt",
        )

    if not _path_exists(legacy_app) or not _path_exists(canonical_app):
        return AppReplacementDecision(
            "not-needed",
            applications_dir,
            legacy_app,
            canonical_app,
            receipt_path,
            reason_code="bundles-do-not-coexist",
        )

    legacy_bundle_id = _bundle_identifier(legacy_app)
    canonical_bundle_id = _bundle_identifier(canonical_app)
    if (
        legacy_bundle_id != COMPATIBLE_BUNDLE_ID
        or canonical_bundle_id != COMPATIBLE_BUNDLE_ID
    ):
        return AppReplacementDecision(
            "refused",
            applications_dir,
            legacy_app,
            canonical_app,
            receipt_path,
            reason_code="bundle-identifier-mismatch",
        )

    return AppReplacementDecision(
        "recovery-available",
        applications_dir,
        legacy_app,
        canonical_app,
        receipt_path,
        show_recovery_card=True,
        action=RECOVERY_ACTION,
    )


def _write_receipt(receipt_path: Path, receipt: dict[str, object]) -> None:
    receipt_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=receipt_path.parent,
            prefix=f".{receipt_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as receipt_file:
            temporary_path = Path(receipt_file.name)
            json.dump(receipt, receipt_file, indent=2)
            receipt_file.write("\n")
            receipt_file.flush()
            os.fsync(receipt_file.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, receipt_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _native_macos_recycle(source: Path) -> Path:
    """Move ``source`` with macOS's headless, recoverable Trash API."""
    if sys.platform != "darwin":
        raise AppReplacementRefused("native macOS Trash is unavailable")
    try:
        from Foundation import NSURL, NSFileManager
    except ImportError as error:
        raise AppReplacementRefused(
            "native macOS Trash framework is unavailable"
        ) from error

    source_url = NSURL.fileURLWithPath_(str(source))
    succeeded, resulting_url, error = (
        NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(
            source_url, None, None
        )
    )
    if not succeeded:
        raise AppReplacementRefused(f"native macOS Trash move failed: {error}")
    if resulting_url is None:
        raise AppReplacementRefused("native macOS Trash move returned no destination")
    destination = resulting_url.path()
    if not destination:
        raise AppReplacementRefused("native macOS Trash move returned an empty path")
    return Path(destination)


def replace_legacy_app(
    legacy_app: Path,
    *,
    applications_dir: Path = Path("/Applications"),
    data_root: Path | None = None,
    recycler: Callable[[Path], Path] | None = None,
) -> Path:
    """Execute the explicitly approved, recoverable legacy-bundle replacement."""
    if data_root is None:
        data_root = _canonical_data_root()
    applications_dir = _absolute(applications_dir)
    data_root = _absolute(data_root)
    legacy_app = _absolute(legacy_app)
    exact_legacy_app = applications_dir / LEGACY_APP_NAME
    receipt_path = data_root / RECEIPT_NAME

    if legacy_app != exact_legacy_app:
        raise AppReplacementRefused("only the exact legacy bundle may be replaced")
    if legacy_app.is_symlink():
        raise AppReplacementRefused("the exact legacy bundle must not be a symlink")
    if _completed_receipt(receipt_path):
        raise AppReplacementRefused("legacy app replacement already completed")

    decision = detect_legacy_app_replacement(applications_dir, data_root)
    if decision.state != "recovery-available":
        raise AppReplacementRefused(
            "legacy app replacement is unavailable: "
            f"{decision.reason_code or decision.state}"
        )

    # Revalidate immediately before the action, rather than trusting an older
    # recovery-card decision.
    if (
        _bundle_identifier(exact_legacy_app) != COMPATIBLE_BUNDLE_ID
        or _bundle_identifier(decision.canonical_app) != COMPATIBLE_BUNDLE_ID
    ):
        raise AppReplacementRefused("bundle identifier changed before replacement")

    now = datetime.now(UTC).isoformat()
    receipt: dict[str, object] = {
        "schema_version": 1,
        "status": "started",
        "action": RECOVERY_ACTION,
        "bundle_identifier": COMPATIBLE_BUNDLE_ID,
        "legacy_app": str(exact_legacy_app),
        "canonical_app": str(decision.canonical_app),
        "started_at": now,
    }
    _write_receipt(receipt_path, receipt)

    recycle = recycler or _native_macos_recycle
    try:
        trash_destination = _absolute(recycle(exact_legacy_app))
    except Exception as error:
        receipt.update(
            {
                "status": "failed",
                "failed_at": datetime.now(UTC).isoformat(),
                "reason_code": "trash-move-failed",
                "error_type": type(error).__name__,
            }
        )
        _write_receipt(receipt_path, receipt)
        raise

    if _path_exists(exact_legacy_app):
        receipt.update(
            {
                "status": "failed",
                "failed_at": datetime.now(UTC).isoformat(),
                "reason_code": "legacy-bundle-remains",
            }
        )
        _write_receipt(receipt_path, receipt)
        raise AppReplacementRefused("recoverable move left the legacy bundle in place")

    receipt.update(
        {
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "trash_destination": str(trash_destination),
        }
    )
    _write_receipt(receipt_path, receipt)
    return receipt_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("detect", "replace"),
        help="detect is read-only; replace requires --approve",
    )
    parser.add_argument("--applications-dir", type=Path, default=Path("/Applications"))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument(
        "--approve",
        action="store_true",
        help="confirm the explicit recoverable move to macOS Trash",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    decision = detect_legacy_app_replacement(args.applications_dir, args.data_root)
    if args.command == "detect":
        print(json.dumps(decision.as_payload(), indent=2))
        return 0
    if not args.approve:
        raise SystemExit("replace requires explicit --approve")
    receipt_path = replace_legacy_app(
        decision.legacy_app,
        applications_dir=args.applications_dir,
        data_root=args.data_root,
    )
    print(receipt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
