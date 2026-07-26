#!/usr/bin/env python3
"""Classify tracked legacy-name references during the Deeper Notebook rebrand."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Mapping
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

Allowlist = Mapping[tuple[str, str], str]
_GLOB_PREFIXES = (
    "docs/superpowers/specs/",
    "docs/superpowers/plans/",
)


def _path_matches(allowlisted_path: str, path: str) -> bool:
    if not allowlisted_path.endswith("/**"):
        return allowlisted_path == path
    prefix = allowlisted_path.removesuffix("**")
    return path.startswith(prefix)


def classify_match(path: str, pattern: str, allowlist: Allowlist) -> str:
    """Return the allowlisted category or flag the reference as active identity."""
    for (allowlisted_path, allowlisted_pattern), category in allowlist.items():
        if allowlisted_pattern == pattern and _path_matches(allowlisted_path, path):
            return category
    return "unexpected_active_identity"


def patterns_for_path(path: str, allowlist: Allowlist) -> tuple[str, ...]:
    """Return global audit patterns plus custom allowlist patterns for this path."""
    custom_patterns = (
        pattern
        for (allowlisted_path, pattern) in allowlist
        if pattern not in PATTERNS and _path_matches(allowlisted_path, path)
    )
    return tuple(dict.fromkeys((*PATTERNS, *custom_patterns)))


def load_allowlist(path: Path) -> dict[tuple[str, str], str]:
    """Load and validate exact path/pattern/category allowlist records."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("allowlist must contain an 'entries' list")

    allowlist: dict[tuple[str, str], str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each allowlist entry must be an object")
        allowlisted_path = entry.get("path")
        pattern = entry.get("pattern")
        category = entry.get("category")
        if not all(isinstance(value, str) for value in (allowlisted_path, pattern, category)):
            raise ValueError("allowlist path, pattern, and category must be strings")
        if category not in CATEGORIES[:-1]:
            raise ValueError(f"invalid allowlist category: {category}")
        if "*" in allowlisted_path:
            if not allowlisted_path.endswith("/**"):
                raise ValueError("allowlist paths may only use a trailing '/**'")
            prefix = allowlisted_path.removesuffix("**")
            if prefix not in _GLOB_PREFIXES:
                raise ValueError(f"disallowed allowlist wildcard path: {allowlisted_path}")
        key = (allowlisted_path, pattern)
        if key in allowlist:
            raise ValueError(f"duplicate allowlist entry: {key}")
        allowlist[key] = category
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


def audit_repository(root: Path, allowlist: Allowlist) -> dict[str, object]:
    """Scan tracked path names and UTF-8 text contents for legacy references."""
    categorized: dict[str, list[dict[str, object]]] = {
        category: [] for category in CATEGORIES
    }
    matched_allowlist: set[tuple[str, str]] = set()
    def record(path: str, pattern: str, source: str, line: int | None) -> None:
        category = classify_match(path, pattern, allowlist)
        entry: dict[str, object] = {
            "path": path,
            "pattern": pattern,
            "source": source,
        }
        if line is not None:
            entry["line"] = line
        categorized[category].append(entry)
        for key in allowlist:
            if key[1] == pattern and _path_matches(key[0], path):
                matched_allowlist.add(key)

    for relative_path in _tracked_paths(root):
        patterns = patterns_for_path(relative_path, allowlist)
        for pattern in patterns:
            if pattern in relative_path:
                record(relative_path, pattern, "path", None)

        absolute_path = root / relative_path
        if not absolute_path.is_file():
            continue
        lines = _text_lines(absolute_path)
        if lines is None:
            continue
        for line_number, line in enumerate(lines, start=1):
            for pattern in patterns:
                if pattern in line:
                    record(relative_path, pattern, "content", line_number)

    stale = [
        {"path": path, "pattern": pattern, "category": category}
        for (path, pattern), category in allowlist.items()
        if (path, pattern) not in matched_allowlist
    ]
    return {
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
