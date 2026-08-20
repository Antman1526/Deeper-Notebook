"""Shared constants for the v0.4 memory layer.

These were duplicated across surreal_store.py and memory_shim.py;
promoted here so adding a new memory kind = one edit.
"""

from __future__ import annotations

# Memory `kind` (in mem0 payloads + dashboard URL paths) → SurrealDB table name.
KIND_TO_TABLE: dict[str, str] = {
    "fact": "memory_fact",
    "preference": "memory_preference",
    "episode": "memory_episode",
}

# Valid `kind` values, useful for HTTP validation and assignment routing.
VALID_KINDS: frozenset[str] = frozenset(KIND_TO_TABLE.keys())

# Reverse: SurrealDB table → kind (for downstream code that needs to inspect
# memory_fact:xxx record IDs and recover the kind).
TABLE_TO_KIND: dict[str, str] = {v: k for k, v in KIND_TO_TABLE.items()}

# Convenience: the three table names in registration order. Used by
# surreal_store's reset() / list_cols() / col_info() implementations.
ALL_MEMORY_TABLES: list[str] = list(KIND_TO_TABLE.values())
