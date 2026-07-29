"""Canonical paths and Markdown serialization for app-owned overlay notes."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable

import yaml

from deeper_notebook.overlay.contracts import OverlayNote
from desktop.data_root import active_data_root

MAX_FILENAME_BYTES = 240
MAX_FILENAME_UTF16_CODE_UNITS = 240
_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNSAFE_TITLE = re.compile(r"[\x00-\x1f/\\\\:*?\"<>|]+")
_FILENAME_PREFIX = "20260729-1542 "
_FILENAME_EXTENSION = ".md"
_WORST_CASE_COLLISION_SUFFIX = "-10000"


class OverlayPathError(ValueError):
    """Raised when a requested overlay path cannot be canonicalized safely."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("Overlay path is invalid.")


@dataclass(frozen=True, slots=True)
class OverlayLayout:
    """Roots owned by the overlay beneath one explicit application data root."""

    canonical_root: Path
    daily_root: Path
    unique_root: Path
    templates_root: Path
    state_root: Path
    revisions_root: Path
    receipts_root: Path
    recovery_root: Path

    @classmethod
    def from_data_root(cls, data_root: Path) -> OverlayLayout:
        canonical = data_root / "overlay" / "v1"
        state = data_root / "overlay-state"
        return cls(
            canonical_root=canonical,
            daily_root=canonical / "Daily",
            unique_root=canonical / "Notes",
            templates_root=canonical / "Templates",
            state_root=state,
            revisions_root=state / "revisions",
            receipts_root=state / "receipts",
            recovery_root=state / "recovery",
        )

    @classmethod
    def active(cls) -> OverlayLayout:
        """Resolve the app data root only at this outer integration boundary."""
        return cls.from_data_root(active_data_root())


def validate_relative_path(value: str) -> str:
    """Return one canonical POSIX-relative overlay path or raise a stable error."""
    if not isinstance(value, str):
        raise OverlayPathError("invalid_relative_path")
    parts = value.split("/")
    pure = PurePosixPath(value)
    if (
        not value
        or pure.is_absolute()
        or "\\" in value
        or "\x00" in value
        or re.match(r"^[A-Za-z]:", value)
        or any(not part or part in {".", ".."} or part.strip() != part for part in parts)
    ):
        raise OverlayPathError("invalid_relative_path")
    return value


def daily_relative_path(date_key: str) -> str:
    """Produce the sole canonical persisted path for a daily note."""
    if not isinstance(date_key, str) or not _DATE_KEY.fullmatch(date_key):
        raise OverlayPathError("invalid_date_key")
    try:
        datetime.strptime(date_key, "%Y-%m-%d")
    except ValueError as error:
        raise OverlayPathError("invalid_date_key") from error
    return f"Daily/{date_key}.md"


def _safe_title(title: str) -> str:
    value = unicodedata.normalize("NFC", title).strip()
    value = "".join(char if not 0xD800 <= ord(char) <= 0xDFFF else " " for char in value)
    value = _UNSAFE_TITLE.sub(" ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value or "Untitled"
    fixed_name = f"{_FILENAME_PREFIX}{_WORST_CASE_COLLISION_SUFFIX}{_FILENAME_EXTENSION}"
    remaining_utf8_bytes = MAX_FILENAME_BYTES - len(fixed_name.encode("utf-8"))
    remaining_utf16_code_units = (
        MAX_FILENAME_UTF16_CODE_UNITS - len(fixed_name.encode("utf-16-le")) // 2
    )
    safe_characters: list[str] = []
    for char in value:
        char_utf8_bytes = len(char.encode("utf-8"))
        char_utf16_code_units = len(char.encode("utf-16-le")) // 2
        if (
            char_utf8_bytes > remaining_utf8_bytes
            or char_utf16_code_units > remaining_utf16_code_units
        ):
            break
        safe_characters.append(char)
        remaining_utf8_bytes -= char_utf8_bytes
        remaining_utf16_code_units -= char_utf16_code_units
    return "".join(safe_characters).rstrip(" .") or "Untitled"


def unique_relative_path(
    local_time: datetime,
    title: str,
    *,
    exists: Callable[[str], bool],
) -> str:
    """Produce a timestamped unique path, deterministically suffixing collisions."""
    stem = f"{local_time:%Y%m%d-%H%M} {_safe_title(title)}"
    candidate = f"Notes/{stem}.md"
    suffix = 2
    while exists(candidate):
        candidate = f"Notes/{stem}-{suffix}.md"
        suffix += 1
        if suffix > 10_000:
            raise OverlayPathError("unique_name_exhausted")
    return validate_relative_path(candidate)


def overlay_frontmatter(note: OverlayNote, body: str) -> str:
    """Prepend canonical, app-owned metadata without changing the Markdown body."""
    metadata = {
        "deeper_notebook": {
            "id": note.id,
            "kind": note.kind,
            "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat(),
            "date_key": note.date_key,
        }
    }
    frontmatter = yaml.safe_dump(
        metadata,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"---\n{frontmatter}---\n{body}"
