"""v0.7.90 — tests for api/routers/exports.py.

Exercises the notebook-to-folder, notebook-to-zip, and single-note export
endpoints with stubbed domain objects (no real SurrealDB needed). Tests
real on-disk writes via tmp_path so any filesystem-layer regressions
(permissions, path normalization, zip layout) are caught.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import exports as exports_mod
from api.routers import filesystem as fs_mod


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(exports_mod.router, prefix="/api")
    app.include_router(fs_mod.router, prefix="/api")  # /fs/mkdir for parent dirs
    return TestClient(app)


# ----------------------------------------------------------------------------
# Stubs for the domain layer
# ----------------------------------------------------------------------------


class _FakeNote:
    def __init__(
        self, id: str, title: str, content: str, note_type: str = "ai",
        created: str = "2026-05-01T00:00:00Z",
        updated: str = "2026-05-01T00:00:00Z",
    ) -> None:
        self.id, self.title, self.content = id, title, content
        self.note_type = note_type
        self.created, self.updated = created, updated


class _FakeSource:
    def __init__(
        self, id: str, title: str, full_text: str,
        file_path: Optional[str] = None, url: Optional[str] = None,
    ) -> None:
        self.id, self.title, self.full_text = id, title, full_text
        self.asset = SimpleNamespace(file_path=file_path, url=url)


class _FakeNotebook:
    def __init__(
        self, id: str, name: str, notes: list[_FakeNote],
        sources: Optional[list[_FakeSource]] = None,
        description: str = "test notebook",
    ) -> None:
        self.id, self.name, self.description = id, name, description
        self.created = "2026-05-01T00:00:00Z"
        self.updated = "2026-05-01T00:00:00Z"
        self._notes, self._sources = notes, sources or []

    async def get_notes(self) -> list[_FakeNote]:
        return self._notes

    async def get_sources(self) -> list[_FakeSource]:
        return self._sources


@pytest.fixture()
def patched_domain(monkeypatch: pytest.MonkeyPatch):
    """Stub the Notebook/Note domain getters so tests don't need a database."""
    notebooks_by_id: dict[str, _FakeNotebook] = {}
    notes_by_id: dict[str, _FakeNote] = {}

    async def _get_notebook(notebook_id: str) -> Optional[_FakeNotebook]:
        return notebooks_by_id.get(notebook_id)

    async def _get_note(note_id: str) -> Optional[_FakeNote]:
        return notes_by_id.get(note_id)

    monkeypatch.setattr(exports_mod.Notebook, "get", staticmethod(_get_notebook))
    monkeypatch.setattr(exports_mod.Note, "get", staticmethod(_get_note))
    return {"notebooks": notebooks_by_id, "notes": notes_by_id}


# ----------------------------------------------------------------------------
# Slugify + helper unit tests
# ----------------------------------------------------------------------------


def test_slugify_strips_emoji_and_special_chars() -> None:
    # v0.7.90 — slugifier strips leading numeric prefixes so v0.7.89 page
    # titles ("📄 01 · Architecture") don't get double-prefixed downstream.
    assert exports_mod._slugify("📋 00 · Overview!") == "overview"
    assert exports_mod._slugify("📄 01 · Architecture") == "architecture"
    assert exports_mod._slugify("Hello / World — v2") == "hello-world-v2"
    assert exports_mod._slugify("") == "untitled"
    # Caps slug to 80 chars
    long_title = "a" * 200
    assert len(exports_mod._slugify(long_title)) == 80
    # Multi-segment numeric titles strip prefix-by-prefix; the final
    # bare-number segment survives so the filename is at least
    # distinguishable rather than collapsing to "untitled".
    assert exports_mod._slugify("01 02 03") == "03"
    # Pure-symbol titles (no surviving characters) fall back to "untitled"
    assert exports_mod._slugify("---") == "untitled"
    assert exports_mod._slugify("📋📋📋") == "untitled"


def test_build_overview_path_detects_v0_7_89_notes() -> None:
    n = _FakeNote("note:1", "📋 00 · My Project — Overview", "body")
    assert exports_mod._build_overview_path(n) == "00-overview.md"  # type: ignore[arg-type]
    n2 = _FakeNote("note:2", "📄 01 · Backend Internals", "body")
    assert exports_mod._build_overview_path(n2) is None  # type: ignore[arg-type]
    # Any note with "Overview" in the title is also caught
    n3 = _FakeNote("note:3", "Project Overview", "body")
    assert exports_mod._build_overview_path(n3) == "00-overview.md"  # type: ignore[arg-type]


def test_plan_filenames_overview_wins_zero_then_pages_indexed() -> None:
    notes: list = [
        _FakeNote("note:p1", "📄 01 · Architecture", "body"),
        _FakeNote("note:ov", "📋 00 · Title — Overview", "body"),
        _FakeNote("note:p2", "📄 02 · Backend", "body"),
    ]
    plan = exports_mod._plan_filenames(notes)
    filenames = [p[0] for p in plan]
    # Overview first; then pages indexed 01, 02 in their original order
    assert filenames[0] == "00-overview.md"
    assert filenames[1].startswith("01-")
    assert filenames[2].startswith("02-")


# ----------------------------------------------------------------------------
# /notebooks/{id}/export — folder format
# ----------------------------------------------------------------------------


def test_export_notebook_folder_writes_overview_and_pages(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    notes = [
        _FakeNote("note:ov", "📋 00 · Demo — Overview", "Overview body."),
        _FakeNote("note:p1", "📄 01 · Architecture", "Arch body."),
        _FakeNote("note:p2", "📄 02 · Backend", "Backend body."),
    ]
    nb = _FakeNotebook("notebook:1", "Demo", notes)
    patched_domain["notebooks"]["notebook:1"] = nb

    target = tmp_path / "demo-export"
    r = client.post(
        "/api/notebooks/notebook:1/export",
        json={"destination": str(target), "format": "folder"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == "folder"
    # 3 notes + 1 manifest = 4 files
    assert body["file_count"] == 4
    assert target.exists() and target.is_dir()
    assert (target / "00-overview.md").exists()
    # The 01-architecture / 02-backend files exist with slugified names
    assert (target / "01-architecture.md").exists()
    assert (target / "02-backend.md").exists()
    # Manifest is valid JSON and references all notes
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["notebook"]["name"] == "Demo"
    assert len(manifest["notes"]) == 3
    # Each note file starts with the frontmatter we wrote
    content = (target / "00-overview.md").read_text()
    assert content.startswith("---\n")
    assert "title: 📋 00 · Demo — Overview" in content
    assert "Overview body." in content


def test_export_notebook_folder_404_when_notebook_missing(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    r = client.post(
        "/api/notebooks/notebook:nope/export",
        json={"destination": str(tmp_path / "x"), "format": "folder"},
    )
    assert r.status_code == 404


def test_export_notebook_folder_400_when_empty_and_no_sources(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    nb = _FakeNotebook("notebook:empty", "Empty", notes=[])
    patched_domain["notebooks"]["notebook:empty"] = nb
    r = client.post(
        "/api/notebooks/notebook:empty/export",
        json={"destination": str(tmp_path / "x"), "format": "folder"},
    )
    assert r.status_code == 400
    assert "no notes to export" in r.json()["detail"]


def test_export_notebook_folder_409_on_existing_file_without_overwrite(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    """v0.7.90 — the pre-flight overwrite check must catch existing files
    BEFORE writing anything else, so a re-run doesn't half-clobber an
    earlier export."""
    notes = [_FakeNote("note:1", "Some Note", "body")]
    nb = _FakeNotebook("notebook:1", "Demo", notes)
    patched_domain["notebooks"]["notebook:1"] = nb
    target = tmp_path / "demo"
    target.mkdir()
    (target / "01-some-note.md").write_text("stale content")
    r = client.post(
        "/api/notebooks/notebook:1/export",
        json={"destination": str(target), "format": "folder", "overwrite": False},
    )
    assert r.status_code == 409
    # The stale file MUST be untouched
    assert (target / "01-some-note.md").read_text() == "stale content"


def test_export_notebook_folder_overwrite_replaces_files(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    notes = [_FakeNote("note:1", "Some Note", "fresh body")]
    nb = _FakeNotebook("notebook:1", "Demo", notes)
    patched_domain["notebooks"]["notebook:1"] = nb
    target = tmp_path / "demo"
    target.mkdir()
    (target / "01-some-note.md").write_text("stale")
    r = client.post(
        "/api/notebooks/notebook:1/export",
        json={"destination": str(target), "format": "folder", "overwrite": True},
    )
    assert r.status_code == 200, r.text
    content = (target / "01-some-note.md").read_text()
    assert "fresh body" in content
    assert "stale" not in content


def test_export_notebook_folder_with_sources(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    notes = [_FakeNote("note:1", "📋 00 · Overview", "body")]
    sources = [
        _FakeSource("source:1", "doc.pdf", "Extracted text.", file_path="/tmp/doc.pdf"),
        _FakeSource("source:2", "page.html", "Web text.", url="https://example.com"),
    ]
    nb = _FakeNotebook("notebook:1", "Demo", notes, sources=sources)
    patched_domain["notebooks"]["notebook:1"] = nb
    target = tmp_path / "demo-with-sources"
    r = client.post(
        "/api/notebooks/notebook:1/export",
        json={
            "destination": str(target),
            "format": "folder",
            "include_sources": True,
        },
    )
    assert r.status_code == 200, r.text
    # sources/ subfolder created with one file per source
    sources_dir = target / "sources"
    assert sources_dir.exists() and sources_dir.is_dir()
    source_files = sorted(p.name for p in sources_dir.iterdir())
    assert len(source_files) == 2
    # Each source file embeds its full_text
    s1_content = (sources_dir / "1.md").read_text()
    assert "Extracted text." in s1_content
    assert "original_file: /tmp/doc.pdf" in s1_content


# ----------------------------------------------------------------------------
# /notebooks/{id}/export — zip format
# ----------------------------------------------------------------------------


def test_export_notebook_zip_creates_archive(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    notes = [
        _FakeNote("note:ov", "📋 00 · Demo — Overview", "Overview body."),
        _FakeNote("note:p1", "📄 01 · Architecture", "Arch body."),
    ]
    nb = _FakeNotebook("notebook:1", "Demo", notes)
    patched_domain["notebooks"]["notebook:1"] = nb
    target = tmp_path / "demo.zip"
    r = client.post(
        "/api/notebooks/notebook:1/export",
        json={"destination": str(target), "format": "zip"},
    )
    assert r.status_code == 200, r.text
    assert target.exists()
    with zipfile.ZipFile(target) as zf:
        names = sorted(zf.namelist())
        assert "00-overview.md" in names
        assert "01-architecture.md" in names
        assert "manifest.json" in names


def test_export_notebook_zip_missing_parent_dir_400(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    notes = [_FakeNote("note:1", "T", "body")]
    nb = _FakeNotebook("notebook:1", "Demo", notes)
    patched_domain["notebooks"]["notebook:1"] = nb
    target = tmp_path / "missing-parent" / "demo.zip"
    r = client.post(
        "/api/notebooks/notebook:1/export",
        json={"destination": str(target), "format": "zip"},
    )
    assert r.status_code == 400
    assert "Parent directory does not exist" in r.json()["detail"]


# ----------------------------------------------------------------------------
# /notes/{id}/export
# ----------------------------------------------------------------------------


def test_export_note_writes_markdown_file(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    note = _FakeNote("note:1", "Single Note", "Body content.")
    patched_domain["notes"]["note:1"] = note
    target = tmp_path / "single.md"
    r = client.post(
        "/api/notes/note:1/export", json={"destination": str(target)},
    )
    assert r.status_code == 200, r.text
    assert target.exists()
    content = target.read_text()
    assert "title: Single Note" in content
    assert "Body content." in content


def test_export_note_404_when_missing(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    r = client.post(
        "/api/notes/note:nope/export",
        json={"destination": str(tmp_path / "x.md")},
    )
    assert r.status_code == 404


def test_export_note_forces_md_extension(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    note = _FakeNote("note:1", "Note", "body")
    patched_domain["notes"]["note:1"] = note
    target_without_ext = tmp_path / "untyped"
    r = client.post(
        "/api/notes/note:1/export",
        json={"destination": str(target_without_ext)},
    )
    assert r.status_code == 200, r.text
    # Should end up with .md appended
    assert (tmp_path / "untyped.md").exists()
    assert not target_without_ext.exists()


def test_export_note_refuses_directory_destination(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    note = _FakeNote("note:1", "Note", "body")
    patched_domain["notes"]["note:1"] = note
    r = client.post(
        "/api/notes/note:1/export", json={"destination": str(tmp_path)},
    )
    assert r.status_code == 400
    assert "directory" in r.json()["detail"].lower()


def test_export_note_409_when_target_exists_without_overwrite(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    note = _FakeNote("note:1", "Note", "fresh")
    patched_domain["notes"]["note:1"] = note
    target = tmp_path / "note.md"
    target.write_text("stale")
    r = client.post(
        "/api/notes/note:1/export",
        json={"destination": str(target), "overwrite": False},
    )
    assert r.status_code == 409
    assert target.read_text() == "stale"


def test_export_note_overwrite_replaces_file(
    client: TestClient, patched_domain, tmp_path: Path,
) -> None:
    note = _FakeNote("note:1", "Note", "fresh body content")
    patched_domain["notes"]["note:1"] = note
    target = tmp_path / "note.md"
    target.write_text("stale")
    r = client.post(
        "/api/notes/note:1/export",
        json={"destination": str(target), "overwrite": True},
    )
    assert r.status_code == 200, r.text
    assert "fresh body content" in target.read_text()


def test_export_refuses_system_destination(
    client: TestClient, patched_domain,
) -> None:
    note = _FakeNote("note:1", "Note", "body")
    patched_domain["notes"]["note:1"] = note
    r = client.post(
        "/api/notes/note:1/export",
        json={"destination": "/etc/onp-note.md"},
    )
    assert r.status_code == 403
