from pathlib import Path

import pytest
from pydantic import ValidationError

from deeper_notebook.workspace.contracts import (
    KnowledgeTabState,
    KnowledgeWorkspaceDocument,
    PaneLayoutNode,
    SplitLayoutNode,
    default_knowledge_workspace,
)
from deeper_notebook.workspace.persistence import (
    WorkspaceStateError,
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


def split_layout_payload(depth: int) -> dict:
    node: dict = {"type": "pane", "pane_id": "pane-1"}
    for level in range(2, depth + 1):
        node = {
            "type": "split",
            "id": f"split-{level}",
            "direction": "horizontal",
            "first": node,
            "second": {
                "type": "pane",
                "pane_id": f"pane-{level}",
            },
        }
    return node


def workspace_payload_with_panes(pane_count: int) -> dict:
    return {
        "version": 1,
        "active_pane_id": "pane-1",
        "next_id": pane_count + 1,
        "panes": {
            f"pane-{index}": {
                "id": f"pane-{index}",
                "active_tab_id": None,
                "tabs": [],
            }
            for index in range(1, pane_count + 1)
        },
        "layout": split_layout_payload(pane_count),
    }


def tab(index: int) -> dict:
    return {
        "id": f"tab-{index}",
        "vault_id": "vault-1",
        "note_id": f"note-{index}",
        "title": f"Note {index}",
        "relative_path": f"Notes/{index}.md",
        "view_mode": "reading",
    }


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
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize(
    "mutation",
    ["absolute-path", "wrong-version", "over-limit-tabs", "missing-layout-pane"],
)
def test_save_revalidates_mutated_documents_before_writing(
    tmp_path: Path,
    mutation: str,
):
    path = tmp_path / "knowledge.json"
    document = populated()
    save_knowledge_workspace(document, path=path)
    original = path.read_bytes()

    if mutation == "absolute-path":
        document.panes["pane-1"].tabs[0].relative_path = "/Users/me/secret.md"
    elif mutation == "wrong-version":
        document.version = 2
    elif mutation == "over-limit-tabs":
        document.panes["pane-1"].tabs.extend(
            KnowledgeTabState.model_validate(tab(index))
            for index in range(2, 130)
        )
    else:
        document.layout = PaneLayoutNode(pane_id="missing")

    with pytest.raises(ValidationError):
        save_knowledge_workspace(document, path=path)
    assert path.read_bytes() == original
    assert not path.with_suffix(".json.tmp").exists()


def test_malformed_utf8_raises_workspace_state_error_without_rewriting(
    tmp_path: Path,
):
    path = tmp_path / "knowledge.json"
    path.write_bytes(b"\xff\xfe\x00")
    original = path.read_bytes()

    with pytest.raises(WorkspaceStateError):
        load_knowledge_workspace(path=path)
    assert path.read_bytes() == original


def test_recursive_split_depth_boundary():
    SplitLayoutNode.model_validate(split_layout_payload(64))
    with pytest.raises(ValidationError):
        SplitLayoutNode.model_validate(split_layout_payload(65))


def test_pane_count_boundary():
    KnowledgeWorkspaceDocument.model_validate(workspace_payload_with_panes(32))
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(workspace_payload_with_panes(33))


def test_total_tab_count_boundary():
    payload = populated().model_dump()
    payload["panes"]["pane-1"]["active_tab_id"] = "tab-1"
    payload["panes"]["pane-1"]["tabs"] = [tab(index) for index in range(1, 129)]
    KnowledgeWorkspaceDocument.model_validate(payload)

    payload["panes"]["pane-1"]["tabs"].append(tab(129))
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)
