"""Canonical text normalization shared by projections and schema migrations."""

from __future__ import annotations

import unicodedata


def canonical_title_key(value: str) -> str:
    """Return the stable vault title key used for same-mount link resolution."""

    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split()).casefold()


__all__ = ["canonical_title_key"]
