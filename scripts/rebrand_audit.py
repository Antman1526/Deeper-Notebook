#!/usr/bin/env python3
"""Classify tracked legacy-name references during the Deeper Notebook rebrand."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = (
    "compatibility_alias",
    "upstream_reference",
    "historical_reference",
    "migration_documentation",
    "unexpected_active_identity",
)
PATTERNS = (
    "Open Notebook Plus",
    "Open Notebook",
    "Open notebook+",
    "OpenNotebook",
    "open-notebook-Plus",
    "open-notebook-plus",
    "open_notebook",
    "OPEN_NOTEBOOK_",
    "ONP_",
    "/onp/",
    "onpFetch",
    "--onp-",
    "components/onp",
    "/api/onp",
)

OccurrenceKey = tuple[str, str, str, int | None, int, str]


@dataclass(frozen=True)
class Approval:
    category: str
    reason: str


Allowlist = Mapping[OccurrenceKey, Approval]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OCCURRENCE_FIELDS = (
    "source",
    "line",
    "column",
    "context_sha256",
)
_AUDIT_METADATA_PATHS = frozenset({"scripts/rebrand-allowlist.json"})


def context_sha256(context: str) -> str:
    """Return the integrity digest used to pin an approval to exact context."""
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


def occurrence_anchor(
    path: str,
    source: str,
    line: int | None,
    column: int,
) -> str:
    """Return the human-readable anchor every approval reason must name."""
    line_label = "path" if line is None else str(line)
    return f"{path}@{source}:{line_label}:{column}"


def _occurrence_key(
    *,
    path: str,
    pattern: str,
    source: str,
    line: int | None,
    column: int,
    context: str,
) -> OccurrenceKey:
    return (
        path,
        pattern,
        source,
        line,
        column,
        context_sha256(context),
    )


def classify_match(key: OccurrenceKey, allowlist: Allowlist) -> str:
    """Return the exact occurrence's category or flag it as active identity."""
    approval = allowlist.get(key)
    return approval.category if approval else "unexpected_active_identity"


def patterns_for_path(path: str, allowlist: Allowlist) -> tuple[str, ...]:
    """Return global audit patterns plus custom allowlist patterns for this path."""
    custom_patterns = (
        key[1]
        for key in allowlist
        if key[0] == path and key[1] not in PATTERNS
    )
    return tuple(dict.fromkeys((*PATTERNS, *custom_patterns)))


def load_allowlist(path: Path) -> dict[OccurrenceKey, Approval]:
    """Load approvals pinned to exact path/content occurrences."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2:
        raise ValueError("allowlist schema_version must be 2")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("allowlist must contain an 'entries' list")

    allowlist: dict[OccurrenceKey, Approval] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each allowlist entry must be an object")
        allowlisted_path = entry.get("path")
        pattern = entry.get("pattern")
        source = entry.get("source")
        line = entry.get("line")
        column = entry.get("column")
        digest = entry.get("context_sha256")
        category = entry.get("category")
        reason = entry.get("reason")
        if not all(field in entry for field in _OCCURRENCE_FIELDS):
            raise ValueError(
                "allowlist entries require source, line, column, and context_sha256"
            )
        if not all(
            isinstance(value, str)
            for value in (
                allowlisted_path,
                pattern,
                source,
                digest,
                category,
                reason,
            )
        ):
            raise ValueError(
                "allowlist path, pattern, source, context_sha256, category, "
                "and reason must be strings; line and column must also be present"
            )
        if source not in {"path", "content"}:
            raise ValueError("allowlist source must be 'path' or 'content'")
        if source == "content" and (
            not isinstance(line, int) or isinstance(line, bool) or line < 1
        ):
            raise ValueError("content approvals require a positive line")
        if source == "path" and line is not None:
            raise ValueError("path approvals require line=null")
        if (
            not isinstance(column, int)
            or isinstance(column, bool)
            or column < 1
        ):
            raise ValueError("allowlist column must be a positive integer")
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("allowlist context_sha256 must be 64 lowercase hex chars")
        if not reason.strip():
            raise ValueError("allowlist reason must be nonempty")
        anchor = occurrence_anchor(
            allowlisted_path,
            source,
            line,
            column,
        )
        if anchor not in reason:
            raise ValueError(
                f"allowlist reason must name exact occurrence anchor {anchor}"
            )
        if category not in CATEGORIES[:-1]:
            raise ValueError(f"invalid allowlist category: {category}")
        if "*" in allowlisted_path:
            raise ValueError("allowlist paths must be exact; wildcards are disallowed")
        key: OccurrenceKey = (
            allowlisted_path,
            pattern,
            source,
            line,
            column,
            digest,
        )
        if key in allowlist:
            raise ValueError(f"duplicate allowlist entry: {key}")
        allowlist[key] = Approval(category=category, reason=reason)
    return allowlist


def _tracked_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [
        raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def _text_lines(path: Path) -> list[str] | None:
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None


def _pattern_occurrences(
    value: str,
    patterns: tuple[str, ...],
) -> list[tuple[str, int, int]]:
    occurrences: list[tuple[str, int, int]] = []
    for pattern in patterns:
        if not pattern:
            continue
        start = 0
        while (match_start := value.find(pattern, start)) != -1:
            match_end = match_start + len(pattern)
            occurrences.append((pattern, match_start, match_end))
            start = match_start + 1
    return sorted(
        occurrences,
        key=lambda occurrence: (
            occurrence[1],
            -(occurrence[2] - occurrence[1]),
            occurrence[0],
        ),
    )


def audit_repository(root: Path, allowlist: Allowlist) -> dict[str, object]:
    """Scan tracked path names and UTF-8 text contents for legacy references."""
    categorized: dict[str, list[dict[str, object]]] = {
        category: [] for category in CATEGORIES
    }
    matched_allowlist: set[OccurrenceKey] = set()

    def record(
        *,
        path: str,
        pattern: str,
        source: str,
        line: int | None,
        column: int,
        context: str,
    ) -> None:
        key = _occurrence_key(
            path=path,
            pattern=pattern,
            source=source,
            line=line,
            column=column,
            context=context,
        )
        category = classify_match(key, allowlist)
        entry: dict[str, object] = {
            "path": path,
            "pattern": pattern,
            "source": source,
            "column": column,
            "context_sha256": key[-1],
        }
        if line is not None:
            entry["line"] = line
        categorized[category].append(entry)
        if key in allowlist:
            matched_allowlist.add(key)

    for relative_path in _tracked_paths(root):
        # The allowlist contains hashes of audited source lines. Auditing its
        # own serialized entries would make those hashes self-referential and
        # impossible to stabilize. Its structure and every field are instead
        # validated by ``load_allowlist`` before repository scanning begins.
        if relative_path in _AUDIT_METADATA_PATHS:
            continue
        patterns = patterns_for_path(relative_path, allowlist)
        for pattern, start, _end in _pattern_occurrences(relative_path, patterns):
            record(
                path=relative_path,
                pattern=pattern,
                source="path",
                line=None,
                column=start + 1,
                context=relative_path,
            )

        absolute_path = root / relative_path
        if not absolute_path.is_file():
            continue
        lines = _text_lines(absolute_path)
        if lines is None:
            continue
        for line_number, line in enumerate(lines, start=1):
            occurrences = _pattern_occurrences(line, patterns)
            allowed_contexts = [
                (pattern, start, end)
                for pattern, start, end in occurrences
                if classify_match(
                    _occurrence_key(
                        path=relative_path,
                        pattern=pattern,
                        source="content",
                        line=line_number,
                        column=start + 1,
                        context=line,
                    ),
                    allowlist,
                )
                != "unexpected_active_identity"
            ]
            for pattern, start, end in occurrences:
                if any(
                    pattern != context_pattern
                    and context_start <= start
                    and end <= context_end
                    for context_pattern, context_start, context_end in allowed_contexts
                ):
                    continue
                record(
                    path=relative_path,
                    pattern=pattern,
                    source="content",
                    line=line_number,
                    column=start + 1,
                    context=line,
                )

    stale = [
        {
            "path": key[0],
            "pattern": key[1],
            "source": key[2],
            "line": key[3],
            "column": key[4],
            "context_sha256": key[5],
            "category": approval.category,
            "reason": approval.reason,
        }
        for key, approval in allowlist.items()
        if key not in matched_allowlist
    ]
    return {
        "schema_version": 2,
        "categories": categorized,
        "summary": {
            category: len(matches) for category, matches in categorized.items()
        },
        "stale_allowlist": stale,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the script's parent repository)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=Path(__file__).with_name("rebrand-allowlist.json"),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail for unexpected active identity or stale allowlist entries",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    allowlist = load_allowlist(args.allowlist)
    report = audit_repository(args.root.resolve(), allowlist)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.check:
        categories = report["categories"]
        assert isinstance(categories, dict)
        if categories["unexpected_active_identity"] or report["stale_allowlist"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
