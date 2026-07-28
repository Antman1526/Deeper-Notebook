"""Atomic local persistence for the knowledge workspace."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from deeper_notebook.workspace.contracts import (
    KnowledgeWorkspaceDocument,
    default_knowledge_workspace,
)
from desktop.data_root import active_data_root


class WorkspaceStateError(ValueError):
    """Raised when persisted workspace state cannot be decoded or validated."""


def knowledge_workspace_path() -> Path:
    """Return the canonical local workspace-state path."""

    return active_data_root() / "workspaces" / "knowledge-workspace-v1.json"


def load_knowledge_workspace(
    path: Path | None = None,
) -> KnowledgeWorkspaceDocument:
    """Load validated workspace state without modifying its source file."""

    target = path if path is not None else knowledge_workspace_path()
    if not target.exists():
        return default_knowledge_workspace()

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return KnowledgeWorkspaceDocument.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise WorkspaceStateError(f"invalid workspace state in {target}") from exc


def _fsync_parent_directory(parent: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        directory_fd = os.open(parent, flags)
    except OSError:
        return
    try:
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
    finally:
        os.close(directory_fd)


def save_knowledge_workspace(
    document: KnowledgeWorkspaceDocument,
    path: Path | None = None,
) -> None:
    """Atomically save a validated workspace document."""

    target = path if path is not None else knowledge_workspace_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    serialized = (
        json.dumps(
            document.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

    created_temporary = False
    try:
        with temporary.open("xb") as stream:
            created_temporary = True
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        created_temporary = False
        _fsync_parent_directory(target.parent)
    except BaseException:
        if created_temporary:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        raise
