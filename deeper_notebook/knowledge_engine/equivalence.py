"""Deterministic, redacted comparison of legacy and unified projections."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from deeper_notebook.knowledge_engine.adapters import adapter_for
from deeper_notebook.knowledge_engine.backfill import (
    CanonicalSource,
    CanonicalSourceCatalog,
)
from deeper_notebook.knowledge_engine.contracts import (
    EquivalenceDifference,
    EquivalenceReport,
    ProjectionDigest,
)


@dataclass(frozen=True, slots=True)
class _Dimension:
    name: str
    code: str
    render: Callable[[Any], str | int | None]


def _count(value: Any) -> str | int | None:
    return value if isinstance(value, int) else None


def _redacted(value: Any) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        rendered = ",".join(f"{key}={value[key]}" for key in sorted(value))
        return rendered or None
    if isinstance(value, list):
        rendered = ",".join(sorted(value))
        return rendered or None
    return str(value)


_DIMENSIONS = (
    _Dimension("document_count", "document_count_mismatch", _count),
    _Dimension("block_count", "block_count_mismatch", _count),
    _Dimension("relation_count", "relation_count_mismatch", _count),
    _Dimension("task_count", "task_count_mismatch", _count),
    _Dimension("property_count", "property_count_mismatch", _count),
    _Dimension("tag_count", "tag_count_mismatch", _count),
    _Dimension("asset_count", "asset_count_mismatch", _count),
    _Dimension("document_hashes", "document_hash_mismatch", _redacted),
    _Dimension("identity_pairs", "identity_pair_mismatch", _redacted),
    _Dimension("outgoing_membership", "outgoing_membership_mismatch", _redacted),
    _Dimension("backlink_membership", "backlink_membership_mismatch", _redacted),
    _Dimension("graph_edges", "graph_membership_mismatch", _redacted),
    _Dimension(
        "exact_search_membership", "exact_search_membership_mismatch", _redacted
    ),
    _Dimension("authority_kind", "authority_mismatch", _redacted),
    _Dimension("source_kind", "source_kind_mismatch", _redacted),
    _Dimension("format_mode", "format_mismatch", _redacted),
    _Dimension("provenance", "provenance_mismatch", _redacted),
    _Dimension("capabilities", "capabilities_mismatch", _redacted),
    _Dimension(
        "overlay_revision_mappings", "overlay_revision_mapping_mismatch", _redacted
    ),
)


def compare_projection_digests(
    legacy: ProjectionDigest,
    unified: ProjectionDigest,
) -> EquivalenceReport:
    """Compare every locked, redacted digest dimension in stable order."""
    differences = []
    if legacy.space_id != unified.space_id:
        differences.append(
            EquivalenceDifference(
                code="space_id_mismatch",
                legacy_value=legacy.space_id,
                unified_value=unified.space_id,
            )
        )
    for dimension in _DIMENSIONS:
        legacy_value = getattr(legacy, dimension.name)
        unified_value = getattr(unified, dimension.name)
        if legacy_value != unified_value:
            differences.append(
                EquivalenceDifference(
                    code=dimension.code,
                    legacy_value=dimension.render(legacy_value),
                    unified_value=dimension.render(unified_value),
                )
            )
    return EquivalenceReport(passed=not differences, differences=differences)


def digest_from_sources(
    sources: list[CanonicalSource], *, exact_queries: tuple[str, ...]
) -> ProjectionDigest:
    """Build a legacy digest while keeping source text inside this boundary."""
    if not sources:
        raise LookupError("knowledge_engine_space_not_found")
    snapshots = []
    for source in sources:
        envelope = {
            "space_id": source.space_id,
            "space_display_name": source.space_display_name,
            "source_ref": source.source_ref,
            "authority_kind": source.authority_kind,
            "source_kind": source.source_kind,
            "format_mode": source.format_mode,
            "relative_locator": source.relative_locator,
            "canonical_bytes": source.canonical_bytes,
            "byte_size": source.byte_size,
            "declared_encoding": source.declared_encoding,
            "declared_newline": source.declared_newline,
            "observed_content_hash": source.observed_content_hash,
            "observed_modified_ns": source.observed_modified_ns,
            "observed_at": source.observed_at,
            "prior_revision": source.prior_revision,
        }
        from deeper_notebook.knowledge_engine.contracts import SourceEnvelope

        snapshot = adapter_for(source.source_kind).project(SourceEnvelope(**envelope))
        snapshots.append((source, snapshot))
    space = snapshots[0][1].space
    document_by_id = {
        snapshot.document.id: snapshot.document.relative_locator
        for _, snapshot in snapshots
    }
    outgoing: dict[str, list[str]] = {}
    backlinks: dict[str, list[str]] = {}
    graph_edges: list[str] = []
    identities: dict[str, str] = {}
    overlay_revisions: dict[str, str] = {}
    for source, snapshot in snapshots:
        locator = snapshot.document.relative_locator
        for claim in source.legacy_identities:
            identities[f"{claim.legacy_kind}:{claim.legacy_id}"] = claim.engine_id
            if claim.legacy_kind == "overlay_note":
                overlay_revisions[claim.legacy_id] = claim.source_revision_id
        for relation in snapshot.relations:
            target = document_by_id.get(relation.target_document_id or "")
            if target is None:
                continue
            outgoing.setdefault(locator, []).append(target)
            backlinks.setdefault(target, []).append(locator)
            graph_edges.append(
                f"{relation.source_document_id}->{relation.target_document_id}:"
                f"{relation.relation_kind}"
            )
    documents = [snapshot.document for _, snapshot in snapshots]
    blocks = [block for _, snapshot in snapshots for block in snapshot.blocks]
    relations = [
        relation for _, snapshot in snapshots for relation in snapshot.relations
    ]
    tasks = [task for _, snapshot in snapshots for task in snapshot.tasks]
    assets = [asset for _, snapshot in snapshots for asset in snapshot.assets]
    return ProjectionDigest(
        space_id=space.id,
        document_count=len(documents),
        block_count=len(blocks),
        relation_count=len(relations),
        task_count=len(tasks),
        property_count=sum(
            len(item.properties) for item in [*documents, *blocks, *tasks]
        ),
        tag_count=sum(len(item.tags) for item in [*documents, *tasks]),
        asset_count=len(assets),
        document_hashes={
            item.relative_locator: item.content_hash for item in documents
        },
        identity_pairs=identities,
        outgoing_membership=outgoing,
        backlink_membership=backlinks,
        graph_edges=graph_edges,
        exact_search_membership={
            sha256(query.encode("utf-8")).hexdigest(): [
                item.relative_locator
                for item in documents
                if query in item.normalized_body
            ]
            for query in exact_queries
        },
        authority_kind=space.authority_kind,
        source_kind=space.source_kind,
        format_mode=space.format_mode,
        provenance=documents[0].provenance if documents else None,
        capabilities=space.capabilities,
        overlay_revision_mappings=overlay_revisions,
    )


async def legacy_projection_digest(
    catalog: CanonicalSourceCatalog,
    *,
    space_id: str,
    exact_queries: tuple[str, ...],
) -> ProjectionDigest:
    """Project current legacy sources without publishing their canonical bytes."""
    selected = [source async for source in catalog.iter_sources_for_space(space_id)]
    return digest_from_sources(selected, exact_queries=exact_queries)


__all__ = [
    "compare_projection_digests",
    "digest_from_sources",
    "legacy_projection_digest",
]
