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
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from deeper_notebook.identity import DATA_DIR_NAME
from desktop.data_root import (
    SecureDirectory,
    atomic_replace_json,
    open_owned_directory,
    unlink_owned_file,
)
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
    snapshot: "AppReplacementSnapshot | None" = None

    def as_payload(self) -> dict[str, object]:
        """Return the desktop-controller recovery-card contract."""
        return {
            "state": self.state,
            "applications_dir": str(self.applications_dir),
            "legacy_app": str(self.legacy_app),
            "canonical_app": str(self.canonical_app),
            "receipt_path": str(self.receipt_path),
            "show_recovery_card": self.show_recovery_card,
            "action": self.action,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class AppReplacementSnapshot:
    """Filesystem identity captured when the user-facing card is created."""

    applications_resolved: Path
    applications_device: int
    applications_inode: int
    legacy_device: int
    legacy_inode: int
    canonical_device: int
    canonical_inode: int
    legacy_bundle_identifier: str
    canonical_bundle_identifier: str


class AppReplacementRefused(RuntimeError):
    """Raised when an explicit replacement fails a safety precondition."""


class AppReplacementOutcomeError(AppReplacementRefused):
    """Raised with a user-safe statement of what happened around the move."""

    def __init__(
        self,
        message: str,
        *,
        move_outcome: Literal[
            "not-moved",
            "move-uncertain",
            "moved-receipt-uncertain",
        ],
    ) -> None:
        super().__init__(message)
        self.move_outcome = move_outcome
        self.user_message = message


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


def _safe_directory_identity(path: Path) -> tuple[Path, int, int] | None:
    """Return resolved path/device/inode for an exact non-symlink directory."""
    try:
        stat_result = path.lstat()
        if path.is_symlink() or not path.is_dir():
            return None
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    return resolved, stat_result.st_dev, stat_result.st_ino


def _safe_bundle_identity(
    app: Path, applications_resolved: Path
) -> tuple[int, int, str] | None:
    """Validate each exact bundle component and capture its stable identity."""
    contents = app / "Contents"
    plist_path = contents / "Info.plist"
    for component, expected_kind in (
        (app, "directory"),
        (contents, "directory"),
        (plist_path, "file"),
    ):
        try:
            component.lstat()
        except OSError:
            return None
        if component.is_symlink():
            return None
        if expected_kind == "directory" and not component.is_dir():
            return None
        if expected_kind == "file" and not component.is_file():
            return None
    try:
        if app.resolve(strict=True).parent != applications_resolved:
            return None
        stat_result = app.lstat()
    except OSError:
        return None
    bundle_id = _bundle_identifier(app)
    if bundle_id is None:
        return None
    return stat_result.st_dev, stat_result.st_ino, bundle_id


def _capture_snapshot(
    applications_dir: Path,
    legacy_app: Path,
    canonical_app: Path,
) -> AppReplacementSnapshot | None:
    root_identity = _safe_directory_identity(applications_dir)
    if root_identity is None:
        return None
    applications_resolved, applications_device, applications_inode = root_identity
    legacy_identity = _safe_bundle_identity(legacy_app, applications_resolved)
    canonical_identity = _safe_bundle_identity(canonical_app, applications_resolved)
    if legacy_identity is None or canonical_identity is None:
        return None
    legacy_device, legacy_inode, legacy_bundle_id = legacy_identity
    canonical_device, canonical_inode, canonical_bundle_id = canonical_identity
    return AppReplacementSnapshot(
        applications_resolved=applications_resolved,
        applications_device=applications_device,
        applications_inode=applications_inode,
        legacy_device=legacy_device,
        legacy_inode=legacy_inode,
        canonical_device=canonical_device,
        canonical_inode=canonical_inode,
        legacy_bundle_identifier=legacy_bundle_id,
        canonical_bundle_identifier=canonical_bundle_id,
    )


def _snapshot_matches(
    expected: AppReplacementSnapshot,
    current: AppReplacementSnapshot | None,
) -> bool:
    return current == expected


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

    if _safe_directory_identity(applications_dir) is None:
        return AppReplacementDecision(
            "refused",
            applications_dir,
            legacy_app,
            canonical_app,
            receipt_path,
            reason_code="unsafe-applications-root",
        )

    snapshot = _capture_snapshot(applications_dir, legacy_app, canonical_app)
    if snapshot is None:
        return AppReplacementDecision(
            "refused",
            applications_dir,
            legacy_app,
            canonical_app,
            receipt_path,
            reason_code="unsafe-bundle-path",
        )

    if (
        snapshot.legacy_bundle_identifier != COMPATIBLE_BUNDLE_ID
        or snapshot.canonical_bundle_identifier != COMPATIBLE_BUNDLE_ID
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
        snapshot=snapshot,
    )


def _write_receipt(
    directory: SecureDirectory,
    receipt_path: Path,
    receipt: dict[str, object],
) -> None:
    atomic_replace_json(directory, receipt_path.name, receipt)


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
    expected_decision: AppReplacementDecision | None = None,
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

    decision = expected_decision or detect_legacy_app_replacement(
        applications_dir, data_root
    )
    if decision.state != "recovery-available":
        raise AppReplacementRefused(
            "legacy app replacement is unavailable: "
            f"{decision.reason_code or decision.state}"
        )
    if (
        decision.applications_dir != applications_dir
        or decision.legacy_app != exact_legacy_app
        or decision.canonical_app != applications_dir / CANONICAL_APP_NAME
        or decision.receipt_path != receipt_path
        or decision.snapshot is None
    ):
        raise AppReplacementRefused("application paths changed after confirmation")

    def revalidate_confirmation() -> None:
        current = _capture_snapshot(
            applications_dir, exact_legacy_app, decision.canonical_app
        )
        if not _snapshot_matches(decision.snapshot, current):
            raise AppReplacementRefused(
                "application root or bundle changed after confirmation"
            )

    revalidate_confirmation()

    recycle = recycler or _native_macos_recycle
    move_completed = False
    try:
        with open_owned_directory(data_root) as receipt_directory:
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
            try:
                _write_receipt(receipt_directory, receipt_path, receipt)
            except Exception as error:
                current = _capture_snapshot(
                    applications_dir,
                    exact_legacy_app,
                    decision.canonical_app,
                )
                if _snapshot_matches(decision.snapshot, current):
                    raise AppReplacementOutcomeError(
                        "The old app was not moved because the recovery receipt "
                        "could not be started.",
                        move_outcome="not-moved",
                    ) from error
                raise AppReplacementOutcomeError(
                    "The Trash move was not started, but the application paths "
                    "changed. Review Applications before trying again.",
                    move_outcome="move-uncertain",
                ) from error

            # The bundle snapshot and receipt directory identity are both
            # checked at the final boundary immediately before invoking Trash.
            try:
                revalidate_confirmation()
                receipt_directory.verify_visible_identity()
            except Exception:
                unlink_owned_file(
                    receipt_directory,
                    receipt_path.name,
                    missing_ok=True,
                )
                raise

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
                try:
                    _write_receipt(
                        receipt_directory,
                        receipt_path,
                        receipt,
                    )
                except Exception:
                    pass
                current = _capture_snapshot(
                    applications_dir,
                    exact_legacy_app,
                    decision.canonical_app,
                )
                if _snapshot_matches(decision.snapshot, current):
                    raise AppReplacementOutcomeError(
                        "The old app was not moved. The macOS Trash operation failed.",
                        move_outcome="not-moved",
                    ) from error
                raise AppReplacementOutcomeError(
                    "The Trash operation returned an error after the app path "
                    "changed. Verify the macOS Trash and Applications before "
                    "trying again.",
                    move_outcome="move-uncertain",
                ) from error

            if _path_exists(exact_legacy_app):
                receipt.update(
                    {
                        "status": "failed",
                        "failed_at": datetime.now(UTC).isoformat(),
                        "reason_code": "legacy-bundle-remains",
                    }
                )
                _write_receipt(receipt_directory, receipt_path, receipt)
                raise AppReplacementRefused(
                    "recoverable move left the legacy bundle in place"
                )

            move_completed = True
            receipt.update(
                {
                    "status": "completed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "trash_destination": str(trash_destination),
                }
            )
            try:
                _write_receipt(receipt_directory, receipt_path, receipt)
            except Exception as error:
                raise AppReplacementOutcomeError(
                    "Open Notebook Plus.app was moved, but the completion "
                    "receipt could not be saved. Verify the macOS Trash before "
                    "taking any further action.",
                    move_outcome="moved-receipt-uncertain",
                ) from error
        return receipt_path
    except AppReplacementOutcomeError:
        raise
    except Exception as error:
        if move_completed:
            raise AppReplacementOutcomeError(
                "Open Notebook Plus.app was moved, but recovery metadata "
                "identity changed. Verify the macOS Trash before taking any "
                "further action.",
                move_outcome="moved-receipt-uncertain",
            ) from error
        raise


@dataclass
class AppRecoveryController:
    """Production controller for the packaged app's one-time recovery card."""

    decision: AppReplacementDecision
    recycler: Callable[[Path], Path] | None = None
    dismissed: bool = False

    @classmethod
    def detect(
        cls,
        *,
        applications_dir: Path = Path("/Applications"),
        data_root: Path | None = None,
        recycler: Callable[[Path], Path] | None = None,
    ) -> "AppRecoveryController":
        return cls(
            detect_legacy_app_replacement(applications_dir, data_root),
            recycler=recycler,
        )

    def card_payload(self) -> dict[str, object]:
        payload = self.decision.as_payload()
        payload.update(
            {
                "show_recovery_card": (
                    self.decision.show_recovery_card and not self.dismissed
                ),
                "title": "Two Deeper Notebook apps are installed",
                "message": (
                    "Open Notebook Plus.app and Deeper Notebook.app both exist. "
                    "Replace Old App moves only Open Notebook Plus.app to the "
                    "macOS Trash so it can be recovered later."
                ),
                "replace_label": "Replace Old App",
                "keep_label": "Keep Both",
            }
        )
        return payload

    def keep_both(self) -> dict[str, object]:
        """Hide this launch's card without touching either bundle or receipt."""
        self.dismissed = True
        return {"ok": True, "kept_both": True}

    dismiss = keep_both

    def replace_old_app(self, *, confirmed: bool) -> Path:
        if not confirmed:
            raise AppReplacementRefused("replacement requires explicit confirmation")
        receipt_path = replace_legacy_app(
            self.decision.legacy_app,
            applications_dir=self.decision.applications_dir,
            data_root=self.decision.receipt_path.parent,
            recycler=self.recycler,
            expected_decision=self.decision,
        )
        self.decision = detect_legacy_app_replacement(
            self.decision.applications_dir,
            self.decision.receipt_path.parent,
        )
        self.dismissed = False
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
        expected_decision=decision,
    )
    print(receipt_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
