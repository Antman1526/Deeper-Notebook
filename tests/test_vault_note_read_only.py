from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from deeper_notebook.domain import notebook as notebook_module
from deeper_notebook.domain.base import ObjectModel
from deeper_notebook.domain.notebook import (
    ExternalNoteReadOnlyError,
    Note,
    Notebook,
)
from deeper_notebook.vault import _projection_note_refresh


def _external_note(**updates) -> Note:
    data = {
        "id": "note:external",
        "title": "Canonical",
        "content": "Original",
        "note_type": "human",
        "vault_id": "vault_mount:brain",
        "vault_file_id": "vault_file:canonical",
        "source_format": "obsidian",
        "canonical_external": True,
        "source_hash": "a" * 64,
        "external_state": "parsed",
    }
    data.update(updates)
    return Note(**data)


@pytest.mark.asyncio
async def test_normal_note_save_membership_and_delete_are_unchanged(monkeypatch):
    note = Note(id="note:normal", title="Normal", content="Mutable")
    base_save = AsyncMock(return_value=None)
    base_delete = AsyncMock(return_value=True)
    relate = AsyncMock(return_value={"id": "artifact:1"})
    monkeypatch.setattr(ObjectModel, "save", base_save)
    monkeypatch.setattr(ObjectModel, "delete", base_delete)
    monkeypatch.setattr(notebook_module, "_is_command_registered", lambda _: False)
    monkeypatch.setattr(notebook_module, "repo_query", AsyncMock(return_value=[]))
    monkeypatch.setattr(ObjectModel, "relate", relate)

    await note.save()
    await note.add_to_notebook("notebook:normal")
    assert await note.delete() is True

    base_save.assert_awaited_once()
    relate.assert_awaited_once_with("artifact", "notebook:normal")
    base_delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_caller_cannot_save_mutated_external_note(monkeypatch):
    # Even stripping the in-memory marker cannot bypass the persisted-row
    # check at the domain boundary.
    note = _external_note(content="Caller mutation", canonical_external=False)
    persisted = _external_note().model_dump()
    base_save = AsyncMock(return_value=None)
    monkeypatch.setattr(ObjectModel, "save", base_save)
    monkeypatch.setattr(notebook_module, "repo_query", AsyncMock(return_value=[persisted]))

    with pytest.raises(ExternalNoteReadOnlyError, match="external_note_read_only"):
        await note.save()

    base_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_note_delete_and_membership_are_rejected(monkeypatch):
    note = _external_note()
    query = AsyncMock()
    monkeypatch.setattr(notebook_module, "repo_query", query)

    with pytest.raises(ExternalNoteReadOnlyError, match="external_note_read_only"):
        await note.add_to_notebook("notebook:target")
    with pytest.raises(ExternalNoteReadOnlyError, match="external_note_read_only"):
        await note.delete()

    query.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_projection_context_can_refresh_external_note(monkeypatch):
    note = _external_note(content="Projection refresh", source_hash="b" * 64)
    persisted = _external_note().model_dump()
    base_save = AsyncMock(return_value=None)
    monkeypatch.setattr(ObjectModel, "save", base_save)
    monkeypatch.setattr(notebook_module, "repo_query", AsyncMock(return_value=[persisted]))
    monkeypatch.setattr(notebook_module, "_is_command_registered", lambda _: False)

    with _projection_note_refresh():
        await note.save()

    base_save.assert_awaited_once()


@pytest.mark.asyncio
async def test_notebook_delete_preflights_external_notes_before_any_cascade(monkeypatch):
    notebook = Notebook(
        id="notebook:brain",
        name="Brain",
        description="Read-only projection",
    )
    external_notes = [_external_note(id=f"note:external-{index}") for index in range(30)]
    monkeypatch.setattr(
        Notebook,
        "get_notes",
        AsyncMock(return_value=external_notes),
    )
    query = AsyncMock()
    monkeypatch.setattr(notebook_module, "repo_query", query)

    with pytest.raises(ExternalNoteReadOnlyError, match="external_note_read_only"):
        await notebook.delete()

    query.assert_not_awaited()
