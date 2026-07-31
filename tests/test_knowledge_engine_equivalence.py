from hashlib import sha256

import pytest

from deeper_notebook.knowledge_engine.contracts import ProjectionDigest
from deeper_notebook.knowledge_engine.equivalence import compare_projection_digests


def _digest(**changes: object) -> ProjectionDigest:
    values: dict[str, object] = {
        "space_id": "knowledge_engine_space:test",
        "document_count": 2,
        "block_count": 4,
        "relation_count": 3,
        "task_count": 1,
        "property_count": 2,
        "tag_count": 3,
        "asset_count": 0,
        "document_hashes": {"Pages/B.md": "b" * 64, "Pages/A.md": "a" * 64},
        "identity_pairs": {
            "note:b": "knowledge_engine_document:b",
            "note:a": "knowledge_engine_document:a",
        },
        "outgoing_membership": {
            "Pages/A.md": ["Pages/B.md"],
        },
        "backlink_membership": {
            "Pages/B.md": ["Pages/A.md"],
        },
        "graph_edges": ["note:a->note:b:wikilink"],
        "exact_search_membership": {
            sha256(b"research").hexdigest(): ["Pages/A.md"]
        },
        "authority_kind": "external_read_only",
        "source_kind": "obsidian",
        "format_mode": "obsidian",
        "provenance": "obsidian",
        "capabilities": ["read", "cite"],
        "overlay_revision_mappings": {},
    }
    values.update(changes)
    return ProjectionDigest(**values)


def test_equal_digests_pass_without_differences_after_order_normalization() -> None:
    legacy = _digest()
    unified = _digest(
        document_hashes={"Pages/A.md": "a" * 64, "Pages/B.md": "b" * 64},
        identity_pairs={
            "note:a": "knowledge_engine_document:a",
            "note:b": "knowledge_engine_document:b",
        },
        capabilities=["cite", "read"],
    )

    report = compare_projection_digests(legacy, unified)

    assert report.passed is True
    assert report.differences == []


def test_every_locked_dimension_has_a_stable_mismatch_code() -> None:
    legacy = _digest()
    unified = _digest(
        document_count=1,
        block_count=1,
        relation_count=1,
        task_count=0,
        property_count=0,
        tag_count=0,
        asset_count=1,
        document_hashes={"Pages/A.md": "c" * 64},
        identity_pairs={"note:a": "knowledge_engine_document:c"},
        outgoing_membership={},
        backlink_membership={},
        graph_edges=[],
        exact_search_membership={sha256(b"research").hexdigest(): []},
        authority_kind="app_owned",
        source_kind="overlay",
        format_mode="markdown",
        provenance="overlay",
        capabilities=["read"],
        overlay_revision_mappings={
            "overlay_note:one": "knowledge_engine_revision:c"
        },
    )

    report = compare_projection_digests(legacy, unified)

    assert report.passed is False
    assert {item.code for item in report.differences} == {
        "document_count_mismatch",
        "block_count_mismatch",
        "relation_count_mismatch",
        "task_count_mismatch",
        "property_count_mismatch",
        "tag_count_mismatch",
        "asset_count_mismatch",
        "document_hash_mismatch",
        "identity_pair_mismatch",
        "outgoing_membership_mismatch",
        "backlink_membership_mismatch",
        "graph_membership_mismatch",
        "exact_search_membership_mismatch",
        "authority_mismatch",
        "source_kind_mismatch",
        "format_mismatch",
        "provenance_mismatch",
        "capabilities_mismatch",
        "overlay_revision_mapping_mismatch",
    }
    assert "Pages/B.md" in str(report.model_dump())
    assert "/Users/" not in report.model_dump_json()


def test_exact_query_text_is_hashed_before_it_can_reach_a_report() -> None:
    report = compare_projection_digests(
        _digest(
            exact_search_membership={
                sha256(b"test-only-token").hexdigest(): ["Pages/A.md"]
            }
        ),
        _digest(
            exact_search_membership={sha256(b"test-only-token").hexdigest(): []}
        ),
    )

    assert "test-only-token" not in report.model_dump_json()


@pytest.mark.asyncio
async def test_legacy_builder_requests_only_the_selected_space() -> None:
    class Catalog:
        def __init__(self) -> None:
            self.requested_space: str | None = None

        async def iter_sources_for_space(self, space_id: str):
            self.requested_space = space_id
            if False:
                yield None

        async def iter_sources(self):
            raise AssertionError("equivalence must not scan every source space")
            if False:
                yield None

    from deeper_notebook.knowledge_engine.equivalence import legacy_projection_digest

    catalog = Catalog()
    with pytest.raises(LookupError):
        await legacy_projection_digest(
            catalog,
            space_id="knowledge_engine_space:test",
            exact_queries=("research",),
        )

    assert catalog.requested_space == "knowledge_engine_space:test"
