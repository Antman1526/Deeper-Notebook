"""Atomic local persistence for the knowledge workspace."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from deeper_notebook.workspace.contracts import (
    KnowledgeWorkspaceDocument,
    KnowledgeWorkspaceDocumentV2,
    default_knowledge_workspace,
    migrate_workspace_v1,
    parse_workspace_document,
)
from desktop.data_root import active_data_root

MAX_KNOWLEDGE_WORKSPACE_BYTES = 1024 * 1024


class WorkspaceStateError(ValueError):
    """Raised when persisted workspace state cannot be decoded or validated."""


def knowledge_workspace_path() -> Path:
    """Return the canonical local workspace-state path."""

    return active_data_root() / "workspaces" / "knowledge-workspace-v1.json"


def load_knowledge_workspace(
    path: Path | None = None,
) -> KnowledgeWorkspaceDocumentV2:
    """Load validated workspace state without modifying its source file."""

    target = path if path is not None else knowledge_workspace_path()
    if not target.exists():
        return migrate_workspace_v1(default_knowledge_workspace())

    try:
        with target.open("rb") as stream:
            encoded = stream.read(MAX_KNOWLEDGE_WORKSPACE_BYTES + 1)
        if len(encoded) > MAX_KNOWLEDGE_WORKSPACE_BYTES:
            raise WorkspaceStateError(
                f"invalid workspace state in {target}"
            )
        payload = json.loads(encoded.decode("utf-8"))
        document = parse_workspace_document(payload)
        return (
            migrate_workspace_v1(document)
            if isinstance(document, KnowledgeWorkspaceDocument)
            else document
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValidationError,
    ) as exc:
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
    document: KnowledgeWorkspaceDocument | KnowledgeWorkspaceDocumentV2,
    path: Path | None = None,
) -> KnowledgeWorkspaceDocumentV2:
    """Atomically save a validated workspace document."""

    parsed_document = parse_workspace_document(document.model_dump(warnings=False))
    validated_document = (
        migrate_workspace_v1(parsed_document)
        if isinstance(parsed_document, KnowledgeWorkspaceDocument)
        else parsed_document
    )
    target = path if path is not None else knowledge_workspace_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(
            validated_document.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if len(serialized) > MAX_KNOWLEDGE_WORKSPACE_BYTES:
        raise WorkspaceStateError(f"invalid workspace state in {target}")

    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        temporary = None
        _fsync_parent_directory(target.parent)
    except BaseException:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        raise
    return validated_document
