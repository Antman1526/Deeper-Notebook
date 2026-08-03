from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create test client after environment variables have been cleared by conftest."""
    from api.main import app

    return TestClient(app)


class TestSearchLimitValidation:
    """SearchRequest.limit must reject non-positive values (#863)."""

    @pytest.mark.parametrize("bad_limit", [0, -1, -100])
    def test_non_positive_limit_returns_422(self, bad_limit, client):
        response = client.post(
            "/api/search",
            json={"query": "x", "type": "text", "limit": bad_limit},
        )
        assert response.status_code == 422

    def test_limit_above_max_returns_422(self, client):
        response = client.post(
            "/api/search",
            json={"query": "x", "type": "text", "limit": 1001},
        )
        assert response.status_code == 422

    @patch("api.routers.search.text_search", new_callable=AsyncMock)
    def test_valid_limit_returns_200(self, mock_text_search, client):
        mock_text_search.return_value = []
        response = client.post(
            "/api/search",
            json={"query": "x", "type": "text", "limit": 10},
        )
        assert response.status_code == 200
        mock_text_search.assert_awaited_once()

    def test_bookmark_filters_are_not_silently_dropped(self, client):
        response = client.post(
            "/api/search",
            json={
                "query": "plan", "type": "text", "match_mode": "exact",
                "space_ids": ["knowledge_engine_space:research"],
                "authority_kinds": ["external_read_only"], "tags": ["plans"],
            },
        )

        assert response.status_code == 422
        assert "filters" in response.json()["detail"].lower()

    @patch("api.routers.search.text_search", new_callable=AsyncMock)
    def test_exact_mode_filters_text_results_to_exact_query_matches(self, mock_text_search, client):
        mock_text_search.return_value = [
            {"id": "note:exact", "title": "Plan", "matches": ["Plan"]},
            {"id": "note:partial", "title": "Planning", "matches": ["Planning"]},
        ]

        response = client.post(
            "/api/search",
            json={"query": "Plan", "type": "text", "match_mode": "exact"},
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["results"]] == ["note:exact"]


class TestTextSearchHighlightOverflowFallback:
    """text_search() must fall back to vector search on a highlight position overflow (#648)."""

    @pytest.mark.asyncio
    async def test_position_overflow_falls_back_to_vector_search(self):
        from deeper_notebook.domain import notebook as notebook_module

        overflow = RuntimeError(
            "A value can't be highlighted: position overflow: 2545 - len: 1965"
        )
        with (
            patch.object(
                notebook_module, "repo_query", new_callable=AsyncMock, side_effect=overflow
            ),
            patch.object(
                notebook_module,
                "vector_search",
                new_callable=AsyncMock,
                return_value=[{"id": "source:1"}],
            ) as mock_vector,
        ):
            result = await notebook_module.text_search("hello", 10)

        assert result == [{"id": "source:1"}]
        mock_vector.assert_awaited_once_with("hello", 10, True, True)

    @pytest.mark.asyncio
    async def test_position_overflow_raises_when_vector_also_fails(self):
        from deeper_notebook.domain import notebook as notebook_module
        from deeper_notebook.exceptions import DatabaseOperationError

        overflow = RuntimeError("position overflow: 1 - len: 0")
        with (
            patch.object(
                notebook_module, "repo_query", new_callable=AsyncMock, side_effect=overflow
            ),
            patch.object(
                notebook_module,
                "vector_search",
                new_callable=AsyncMock,
                side_effect=Exception("no embedding model"),
            ),
        ):
            # When both search paths fail, surface the error rather than masking it
            # as an empty result set.
            with pytest.raises(DatabaseOperationError):
                await notebook_module.text_search("hello", 10)

    @pytest.mark.asyncio
    async def test_other_runtime_errors_still_raise(self):
        from deeper_notebook.domain import notebook as notebook_module
        from deeper_notebook.exceptions import DatabaseOperationError

        with patch.object(
            notebook_module,
            "repo_query",
            new_callable=AsyncMock,
            side_effect=RuntimeError("some other db failure"),
        ):
            with pytest.raises(DatabaseOperationError):
                await notebook_module.text_search("hello", 10)


@pytest.mark.asyncio
@pytest.mark.parametrize("embedding_state", ["pending", "failed"])
async def test_vector_search_enriches_mounted_note_without_root_leak(embedding_state: str):
    from deeper_notebook.domain import notebook as notebook_module

    with (
        patch("deeper_notebook.utils.embedding.generate_embedding", new_callable=AsyncMock, return_value=[0.1]),
        patch.object(notebook_module, "repo_query", new_callable=AsyncMock, side_effect=[
            [{"id": "note:mounted", "title": "Mounted"}],
            [{"id": "note:mounted", "canonical_external": True, "vault_id": "vault_mount:brain", "relative_path": "wiki/note.md", "source_hash": "a" * 64, "embedding_state": embedding_state}],
        ]),
    ):
        result = await notebook_module.vector_search("mounted", 1)

    assert result[0]["vault_provenance"] == {"canonical_external": True, "vault_id": "vault_mount:brain", "relative_path": "wiki/note.md", "source_hash": "sha256:" + "a" * 64}
    assert "/Users/" not in str(result)


@pytest.mark.asyncio
async def test_normal_search_result_keeps_legacy_shape():
    from deeper_notebook.domain import notebook as notebook_module

    with patch.object(notebook_module, "repo_query", new_callable=AsyncMock, return_value=[{"id": "source:plain", "title": "Plain"}]):
        result = await notebook_module.text_search("plain", 1)

    assert result == [{"id": "source:plain", "title": "Plain"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("embedding_state", ["pending", "failed"])
async def test_text_search_enriches_mounted_note_with_portable_provenance(embedding_state: str):
    from deeper_notebook.domain import notebook as notebook_module

    with patch.object(
        notebook_module,
        "repo_query",
        new_callable=AsyncMock,
        side_effect=[
            [{"id": "note:mounted", "title": "Mounted"}],
            [{
                "id": "note:mounted",
                "canonical_external": True,
                "vault_id": "vault_mount:obsidian-brain",
                "relative_path": "wiki/concepts/local-llms.md",
                "source_hash": "d2d369166f8a794dbab96699aefd87ccc58763163dceb4221e61cc9c8833f071",
                "embedding_state": embedding_state,
            }],
        ],
    ) as query:
        result = await notebook_module.text_search("mounted", 1)

    assert result[0]["vault_provenance"] == {
        "canonical_external": True,
        "vault_id": "vault_mount:obsidian-brain",
        "relative_path": "wiki/concepts/local-llms.md",
        "source_hash": "sha256:d2d369166f8a794dbab96699aefd87ccc58763163dceb4221e61cc9c8833f071",
    }
    assert query.await_count == 2
    provenance_query = query.await_args_list[1].args[0]
    assert "vault_file_id.embedding_state" in provenance_query
    assert "vault_file_id.relative_path" in provenance_query
    assert "/Users/" not in str(result)
