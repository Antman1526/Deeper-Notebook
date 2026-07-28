from pathlib import Path

import pytest
from pydantic import ValidationError

from deeper_notebook.workspace.contracts import (
    KnowledgeWorkspaceDocument,
    default_knowledge_workspace,
)
from deeper_notebook.workspace.persistence import (
    load_knowledge_workspace,
    save_knowledge_workspace,
)


def populated() -> KnowledgeWorkspaceDocument:
    return KnowledgeWorkspaceDocument.model_validate(
        {
            "version": 1,
            "active_pane_id": "pane-1",
            "next_id": 2,
            "panes": {
                "pane-1": {
                    "id": "pane-1",
                    "active_tab_id": "tab:one",
                    "tabs": [
                        {
                            "id": "tab:one",
                            "vault_id": "vault:one",
                            "note_id": "note:one",
                            "title": "One",
                            "relative_path": "Projects/One.md",
                            "view_mode": "reading",
                        }
                    ],
                },
            },
            "layout": {"type": "pane", "pane_id": "pane-1"},
        }
    )


def test_missing_workspace_returns_default(tmp_path: Path):
    state = load_knowledge_workspace(path=tmp_path / "knowledge.json")
    assert state == default_knowledge_workspace()


def test_workspace_round_trips_through_atomic_file(tmp_path: Path):
    path = tmp_path / "workspaces" / "knowledge.json"
    save_knowledge_workspace(populated(), path=path)
    assert load_knowledge_workspace(path=path) == populated()
    assert not path.with_suffix(".json.tmp").exists()


def test_absolute_or_parent_relative_paths_are_rejected():
    payload = populated().model_dump()
    payload["panes"]["pane-1"]["tabs"][0]["relative_path"] = (
        "/Users/me/secret.md"
    )
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)
    payload["panes"]["pane-1"]["tabs"][0]["relative_path"] = "../secret.md"
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)


def test_inconsistent_layout_is_rejected():
    payload = populated().model_dump()
    payload["layout"] = {"type": "pane", "pane_id": "missing"}
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)


def test_failed_replace_preserves_previous_document(tmp_path: Path, monkeypatch):
    path = tmp_path / "knowledge.json"
    save_knowledge_workspace(populated(), path=path)
    original = path.read_bytes()
    monkeypatch.setattr(
        "deeper_notebook.workspace.persistence.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("injected")),
    )
    with pytest.raises(OSError, match="injected"):
        save_knowledge_workspace(default_knowledge_workspace(), path=path)
    assert path.read_bytes() == original
