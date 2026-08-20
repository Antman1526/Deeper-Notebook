from unittest.mock import AsyncMock, patch

import pytest

from deeper_notebook.domain.notebook import Note
from deeper_notebook.utils.context_builder import ContextBuilder


@pytest.mark.asyncio
@pytest.mark.parametrize("embedding_state", ["pending", "failed"])
async def test_mounted_note_context_keeps_grounded_v1_span_when_embedding_is_not_ready(
    embedding_state: str,
    caplog,
):
    caplog.set_level("DEBUG")
    note = Note(
        id="note:mounted",
        title="Mounted",
        content="selected block",
        canonical_external=True,
        vault_id="vault_mount:brain",
        vault_file_id="vault_file:mounted",
        source_hash="a" * 64,
    )
    with (
        patch.object(Note, "get", new_callable=AsyncMock, return_value=note),
        patch(
            "deeper_notebook.utils.context_builder.repo_query",
            new_callable=AsyncMock,
            return_value=[
                {
                    "relative_path": "wiki/selected.md",
                    "source_hash": "a" * 64,
                    "embedding_state": embedding_state,
                    "root_path": "/Users/Antman/private-vault",
                    "selected_block": {"source_start": 12, "source_end": 34},
                }
            ],
        ),
    ):
        builder = ContextBuilder()
        await builder._add_note_context("note:mounted")

    citation = builder.items[0].content["grounded_citation"]
    assert (
        citation
        == "[V1] wiki/selected.md | note note:mounted | sha256:"
        + "a" * 64
        + " | blocks 12-34"
    )
    assert "/Users/" not in str(builder.items[0].content)
    assert "/Users/" not in caplog.text


@pytest.mark.asyncio
async def test_ordinary_note_context_keeps_legacy_shape_without_vault_citation():
    note = Note(id="note:plain", title="Plain", content="ordinary")
    with patch.object(Note, "get", new_callable=AsyncMock, return_value=note):
        builder = ContextBuilder()
        await builder._add_note_context("note:plain")

    assert "grounded_citation" not in builder.items[0].content
