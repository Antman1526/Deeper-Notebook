import threading
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


def attempt_temporary_files(path: Path) -> list[Path]:
    return list(path.parent.glob(f".{path.name}.*.tmp"))


def test_missing_workspace_returns_default(tmp_path: Path):
    state = load_knowledge_workspace(path=tmp_path / "knowledge.json")
    assert state == default_knowledge_workspace()


def test_workspace_round_trips_through_atomic_file(tmp_path: Path):
    path = tmp_path / "workspaces" / "knowledge.json"
    save_knowledge_workspace(populated(), path=path)
    assert load_knowledge_workspace(path=path) == populated()
    assert not path.with_suffix(".json.tmp").exists()


def test_legacy_workspace_tabs_default_to_external_vault_authority():
    workspace = populated()

    assert workspace.panes["pane-1"].tabs[0].source_authority == "external-vault"
    assert (
        workspace.model_dump()["panes"]["pane-1"]["tabs"][0]["source_authority"]
        == "external-vault"
    )


def test_pre_navigation_current_session_loads_with_version_one_defaults():
    payload = populated().model_dump()
    payload.pop("navigation", None)
    payload["panes"]["pane-1"]["tabs"][0].pop("knowledge_document_id", None)
    payload["panes"]["pane-1"]["tabs"][0].pop("graph_viewport", None)

    workspace = KnowledgeWorkspaceDocument.model_validate(payload)

    assert workspace.version == 1
    assert workspace.navigation.utility_mode == "sources"
    assert workspace.navigation.sidebar_width == 320
    assert workspace.panes["pane-1"].tabs[0].knowledge_document_id is None
    assert workspace.panes["pane-1"].tabs[0].graph_viewport is None


def test_current_session_round_trips_a_bounded_search_mode():
    payload = populated().model_dump()
    payload["navigation"] = {"search_mode": "semantic"}

    workspace = KnowledgeWorkspaceDocument.model_validate(payload)

    assert workspace.navigation.search_mode == "semantic"
    assert KnowledgeWorkspaceDocument.model_validate(workspace.model_dump()) == workspace
    payload["navigation"] = {"search_mode": "unsupported"}
    with pytest.raises(ValidationError):
        KnowledgeWorkspaceDocument.model_validate(payload)


def test_split_first_size_defaults_without_storing_a_second_panel_size():
    split = SplitLayoutNode.model_validate(
        {
            "type": "split",
            "id": "split-one",
            "direction": "horizontal",
            "first": {"type": "pane", "pane_id": "pane-1"},
            "second": {"type": "pane", "pane_id": "pane-2"},
        }
    )

    assert split.first_size == 50.0
    assert "second_size" not in split.model_dump()


def test_stale_legacy_temporary_file_does_not_block_future_saves(
    tmp_path: Path,
):
    path = tmp_path / "knowledge.json"
    stale = path.with_suffix(".json.tmp")
    stale.write_bytes(b"interrupted older save")

    save_knowledge_workspace(populated(), path=path)

    assert load_knowledge_workspace(path=path) == populated()
    assert stale.read_bytes() == b"interrupted older save"
    assert attempt_temporary_files(path) == []


def test_overlapping_saves_use_distinct_temporary_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    path = tmp_path / "knowledge.json"
    first = populated()
    second = default_knowledge_workspace()
    replace_barrier = threading.Barrier(2)
    original_replace = __import__("os").replace
    replacement_sources: list[Path] = []

    def synchronized_replace(source: Path, destination: Path) -> None:
        replacement_sources.append(Path(source))
        replace_barrier.wait(timeout=5)
        original_replace(source, destination)

    monkeypatch.setattr(
        "deeper_notebook.workspace.persistence.os.replace",
        synchronized_replace,
    )
    errors: list[BaseException] = []

    def save(document: KnowledgeWorkspaceDocument) -> None:
        try:
            save_knowledge_workspace(document, path=path)
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=save, args=(first,)),
        threading.Thread(target=save, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(replacement_sources) == 2
    assert replacement_sources[0] != replacement_sources[1]
    assert all(source.parent == path.parent for source in replacement_sources)
    restored = load_knowledge_workspace(path=path)
    assert restored == first or restored == second
    assert attempt_temporary_files(path) == []


def test_absolute_or_parent_relative_paths_are_rejected():
    payload = populated().model_dump()
    payload["panes"]["pane-1"]["tabs"][0]["relative_path"] = "/Users/me/secret.md"
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
            KnowledgeTabState.model_validate(tab(index)) for index in range(2, 130)
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


def test_oversized_workspace_is_rejected_without_unbounded_text_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    path = tmp_path / "knowledge.json"
    path.write_bytes(b" " * (1024 * 1024 + 1))
    read_text_calls: list[Path] = []
    original_read_text = Path.read_text

    def tracked_read_text(target: Path, *args, **kwargs) -> str:
        read_text_calls.append(target)
        return original_read_text(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read_text)

    with pytest.raises(WorkspaceStateError, match="invalid workspace state"):
        load_knowledge_workspace(path=path)
    assert read_text_calls == []


def test_save_rejects_encoded_state_larger_than_persistence_limit(
    tmp_path: Path,
):
    path = tmp_path / "knowledge.json"
    payload = populated().model_dump()
    payload["panes"]["pane-1"]["active_tab_id"] = "tab-1"
    payload["panes"]["pane-1"]["tabs"] = [
        {
            **tab(index),
            "title": "🧠" * 512,
            "relative_path": f"Notes/{'🧠' * 4080}-{index}.md",
        }
        for index in range(1, 129)
    ]
    document = KnowledgeWorkspaceDocument.model_validate(payload)

    with pytest.raises(WorkspaceStateError, match="invalid workspace state"):
        save_knowledge_workspace(document, path=path)

    assert not path.exists()
    assert attempt_temporary_files(path) == []


def test_tab_limit_is_rejected_before_nested_tab_validation():
    payload = populated().model_dump()
    payload["panes"]["pane-1"]["active_tab_id"] = "tab-1"
    payload["panes"]["pane-1"]["tabs"] = [tab(index) for index in range(1, 130)]
    payload["panes"]["pane-1"]["tabs"][-1]["relative_path"] = (
        "/must-not-be-deeply-validated.md"
    )

    with pytest.raises(ValidationError) as error:
        KnowledgeWorkspaceDocument.model_validate(payload)

    assert "more than 128 tabs" in str(error.value)
    assert "relative to its vault" not in str(error.value)


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
