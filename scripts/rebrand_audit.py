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
ALLOWLIST_SCHEMA_VERSION = 3
LEGACY_PATTERNS = (
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
_SAFE_NESTED_APPROVALS = frozenset(
    {
        ("Open Notebook Plus", "Open Notebook"),
    }
)

OccurrenceKey = tuple[str, str, str, int | None, int, str]


@dataclass(frozen=True)
class Rationale:
    path: str
    source: str
    line: int | None
    column: int
    context_sha256: str
    explanation: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "source": self.source,
            "line": self.line,
            "column": self.column,
            "context_sha256": self.context_sha256,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class Approval:
    category: str
    rationale: Rationale


Allowlist = Mapping[OccurrenceKey, Approval]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "persisted_queue_identifiers",
        "entries",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "path",
        "pattern",
        "source",
        "line",
        "column",
        "context_sha256",
        "category",
        "rationale",
    }
)
_RATIONALE_FIELDS = frozenset(
    {
        "path",
        "source",
        "line",
        "column",
        "context_sha256",
        "explanation",
    }
)
_AUDIT_METADATA_PATHS = frozenset({"scripts/rebrand-allowlist.json"})
_MIN_EXPLANATION_CHARS = 48
_MIN_EXPLANATION_WORDS = 8
_GENERIC_EXPLANATIONS = frozenset(
    {
        "compatibility behavior is intentionally preserved.",
        "historical product name retained for accuracy.",
        (
            "historical reference retained for accuracy and migration "
            "compatibility."
        ),
        "this legacy reference is retained for compatibility.",
    }
)


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
    """Return the scanner's immutable, built-in legacy-pattern policy."""
    del path, allowlist
    return LEGACY_PATTERNS


def load_allowlist(path: Path) -> dict[OccurrenceKey, Approval]:
    """Load approvals pinned to exact path/content occurrences."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("allowlist must be an object")
    if frozenset(payload) != _TOP_LEVEL_FIELDS:
        raise ValueError(
            "allowlist must contain exactly the schema_version, "
            "persisted_queue_identifiers, and entries fields"
        )
    if payload.get("schema_version") != ALLOWLIST_SCHEMA_VERSION:
        raise ValueError(
            f"allowlist schema_version must be {ALLOWLIST_SCHEMA_VERSION}"
        )
    persisted_identifiers = payload.get("persisted_queue_identifiers")
    if not isinstance(persisted_identifiers, list):
        raise ValueError(
            "allowlist persisted_queue_identifiers must be a list"
        )
    queue_identifier_fields = {
        "registration": frozenset(
            {"kind", "path", "symbol", "callee", "app", "command"}
        ),
        "submission": frozenset(
            {
                "kind",
                "path",
                "symbol",
                "callee",
                "app",
                "command",
                "invocation",
            }
        ),
    }
    for identifier in persisted_identifiers:
        if not isinstance(identifier, dict):
            raise ValueError(
                "each persisted queue identifier must be an object"
            )
        expected_fields = queue_identifier_fields.get(identifier.get("kind"))
        if (
            expected_fields is None
            or frozenset(identifier) != expected_fields
            or not all(
                isinstance(value, str) and value
                for value in identifier.values()
            )
        ):
            raise ValueError(
                "persisted queue identifiers must use the exact registration "
                "or submission field schema"
            )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("allowlist must contain an 'entries' list")

    allowlist: dict[OccurrenceKey, Approval] = {}
    explanations: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("each allowlist entry must be an object")
        if frozenset(entry) != _ENTRY_FIELDS:
            raise ValueError(
                "allowlist entries must contain exactly the documented fields"
            )
        allowlisted_path = entry.get("path")
        pattern = entry.get("pattern")
        source = entry.get("source")
        line = entry.get("line")
        column = entry.get("column")
        digest = entry.get("context_sha256")
        category = entry.get("category")
        rationale = entry.get("rationale")
        if not all(
            isinstance(value, str)
            for value in (
                allowlisted_path,
                pattern,
                source,
                digest,
                category,
            )
        ):
            raise ValueError(
                "allowlist path, pattern, source, context_sha256, and category "
                "must be strings"
            )
        if pattern not in LEGACY_PATTERNS:
            raise ValueError(
                "allowlist pattern must be one of the scanner's built-in "
                "legacy patterns"
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
        if not isinstance(rationale, dict):
            raise ValueError("allowlist rationale must be an object")
        if frozenset(rationale) != _RATIONALE_FIELDS:
            raise ValueError(
                "allowlist rationale must contain exactly path, source, line, "
                "column, context_sha256, and explanation"
            )
        rationale_location = (
            rationale.get("path"),
            rationale.get("source"),
            rationale.get("line"),
            rationale.get("column"),
            rationale.get("context_sha256"),
        )
        if rationale_location != (
            allowlisted_path,
            source,
            line,
            column,
            digest,
        ):
            raise ValueError(
                "allowlist rationale location and context hash must exactly "
                "match its occurrence"
            )
        explanation = rationale.get("explanation")
        if not isinstance(explanation, str):
            raise ValueError("allowlist rationale explanation must be a string")
        normalized_explanation = " ".join(explanation.split())
        if (
            len(normalized_explanation) < _MIN_EXPLANATION_CHARS
            or len(normalized_explanation.split()) < _MIN_EXPLANATION_WORDS
            or normalized_explanation.casefold() in _GENERIC_EXPLANATIONS
        ):
            raise ValueError(
                "allowlist rationale requires a meaningful explanation of at "
                f"least {_MIN_EXPLANATION_CHARS} characters and "
                f"{_MIN_EXPLANATION_WORDS} words"
            )
        duplicate_key = normalized_explanation.casefold()
        if duplicate_key in explanations:
            raise ValueError(
                "allowlist rationale contains a duplicate explanation"
            )
        explanations.add(duplicate_key)
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
        allowlist[key] = Approval(
            category=category,
            rationale=Rationale(
                path=allowlisted_path,
                source=source,
                line=line,
                column=column,
                context_sha256=digest,
                explanation=normalized_explanation,
            ),
        )
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
                    (context_pattern, pattern) in _SAFE_NESTED_APPROVALS
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
            "rationale": approval.rationale.as_dict(),
        }
        for key, approval in allowlist.items()
        if key not in matched_allowlist
    ]
    return {
        "schema_version": ALLOWLIST_SCHEMA_VERSION,
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
