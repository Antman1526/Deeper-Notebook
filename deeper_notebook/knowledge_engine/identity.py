"""Deterministic, relative identities for knowledge-engine records."""

from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath

_KINDS = frozenset(
    {
        "space",
        "document",
        "block",
        "relation",
        "task",
        "asset",
        "view",
        "revision",
        "identity",
        "receipt",
    }
)


def canonical_locator(value: str) -> str:
    """Return a normalized locator that cannot name a local filesystem root."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or value.strip() != value
        or value.startswith(("/", "\\"))
        or "\\" in value
        or "\x00" in value
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise ValueError("canonical locator must be relative")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("canonical locator must not escape its space")
    canonical = PurePosixPath(*parts).as_posix()
    if canonical != value:
        raise ValueError("canonical locator must be normalized")
    return canonical


def engine_record_id(kind: str, space_id: str, source_key: str) -> str:
    """Build a stable record ID scoped to one knowledge space."""
    if kind not in _KINDS:
        raise ValueError("invalid knowledge engine record kind")
    if not space_id or len(space_id) > 128:
        raise ValueError("invalid knowledge space identity")
    key = canonical_locator(source_key) if kind != "space" else source_key
    digest = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"deeper-notebook:knowledge-engine:v1:{kind}:{space_id}:{key}",
    ).hex
    return f"knowledge_engine_{kind}:{digest}"
