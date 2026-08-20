"""v0.7.119 — Studio multi-page end-to-end happy-path test.

Existing `tests/test_studio_router.py` mocks individual LLM calls at
the chain level. This file goes one step higher and tests the full
multi-page pipeline by stubbing only at the LLM-provision boundary —
catching state-shape regressions in:

  1. _generate_outline (JSON outline pass)
  2. _generate_all_pages (sequential per-page generation)
  3. _save_notebook_notes (overview + N pages persisted)
  4. _render_overview_note (headline + summary + TOC + suggestions)

Verifies the full v0.7.89 contract: one Studio request → N+1 Notes
saved to the Notebook in render order, with the right titles + bodies.

Companion to `test_studio_router.py` which covers the lower-level
unit slices. Does NOT need a real SurrealDB or LangGraph runtime.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import studio as studio_mod


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """Build a Studio-only app with the full pipeline mocked at the
    LLM-provision + content-extract + save boundaries."""

    # --- Mock the upload-save path
    async def _save_recording(upload, max_bytes=None):
        return f"{tmp_path}/{upload.filename}"

    monkeypatch.setattr(studio_mod, "save_uploaded_file", _save_recording)

    # --- Mock content_core
    import sys

    async def _extract(state):
        return SimpleNamespace(
            content=f"# {state.file_path}\n\nFull text of {state.file_path}",
            title=None,
            url=None,
            file_path=state.file_path,
        )

    fake_cc = SimpleNamespace(extract_content=_extract)
    fake_cc_common = SimpleNamespace(
        ProcessSourceState=lambda **kw: SimpleNamespace(**kw),
    )
    monkeypatch.setitem(sys.modules, "content_core", fake_cc)
    monkeypatch.setitem(sys.modules, "content_core.common", fake_cc_common)

    # --- Capture every note save so the test can assert on the full plan
    notes_saved: list = []

    class _NotebookMock:
        def __init__(self, *, name, description=None):
            self.name, self.description = name, description
            self.id = "notebook:e2e-test"

        async def save(self):
            pass

    class _SourceMock:
        def __init__(self, **kw):
            self.id = f"source:{len(notes_saved)}"
            self.full_text = None
            self.title = kw.get("title")
            self.asset = kw.get("asset")

        async def save(self):
            pass

        async def add_to_notebook(self, _id):
            pass

        async def vectorize(self):
            pass

    class _NoteMock:
        def __init__(self, *, title=None, content=None, note_type=None):
            self.id = f"note:e2e-{len(notes_saved)}"
            self.title, self.content = title, content
            self.note_type = note_type

        async def save(self):
            notes_saved.append(
                {
                    "id": self.id,
                    "title": self.title,
                    "content": self.content,
                    "type": self.note_type,
                }
            )

        async def add_to_notebook(self, _id):
            pass

    monkeypatch.setattr(studio_mod, "Notebook", _NotebookMock)
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(studio_mod, "Note", _NoteMock)
    monkeypatch.setattr(studio_mod, "Asset", lambda **kw: SimpleNamespace(**kw))

    # --- Mock the LLM chain — provision returns a chain whose ainvoke
    # produces the outline JSON first, then per-page markdown.
    page_outputs = iter(
        [
            # First call: outline JSON
            MagicMock(
                content=(
                    '{"headline": "Demo project headline",'
                    ' "summary": "First summary paragraph about the project.\\n\\n'
                    'Second paragraph with details.",'
                    ' "pages": ['
                    '  {"title": "Architecture",'
                    '   "focus": "How the components fit together",'
                    '   "key_questions": ["What\'s the data flow?"]},'
                    '  {"title": "Backend Internals",'
                    '   "focus": "How the API layer works",'
                    '   "key_questions": ["How are requests handled?"]},'
                    '  {"title": "Risks",'
                    '   "focus": "Known issues and gaps",'
                    '   "key_questions": ["What could break?"]}'
                    " ],"
                    ' "top_suggestions": ["Verify X", "Audit Y", "Document Z"]'
                    "}"
                )
            ),
            # Page 1 — Architecture
            MagicMock(
                content=(
                    "# Architecture\n\nIntro about how it fits together.\n\n"
                    "## Key concepts\n- **Component A** — does X\n\n"
                    "## Details\nMore body text.\n\n"
                    "## 💡 AI Suggestions for this page\n- Verify X\n"
                )
            ),
            # Page 2 — Backend Internals
            MagicMock(
                content=(
                    "# Backend Internals\n\nFastAPI layer details.\n\n"
                    "## 💡 AI Suggestions for this page\n- Document the request flow\n"
                )
            ),
            # Page 3 — Risks
            MagicMock(
                content=(
                    "# Risks\n\nThings to watch.\n\n"
                    "## 💡 AI Suggestions for this page\n- Add monitoring\n"
                )
            ),
        ]
    )

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(side_effect=lambda msgs: next(page_outputs))
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    # --- Build the test client
    app = FastAPI()
    app.include_router(studio_mod.router, prefix="/api")
    test_client = TestClient(app)
    test_client.notes_saved = notes_saved  # type: ignore[attr-defined]
    return test_client


def test_studio_e2e_multipage_produces_overview_plus_pages_in_render_order(client):
    """v0.7.119 E2E — A Studio request with the multi-page outline JSON
    must produce: 1 Overview note + N page notes, in render order,
    with the right titles and bodies."""
    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "title": "E2E Demo"},
        files=[
            ("files", ("a.txt", b"a content", "text/plain")),
            ("files", ("b.md", b"b content", "text/markdown")),
        ],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "notebook"
    assert body["notebook_id"] == "notebook:e2e-test"

    # 4 notes total: 1 overview + 3 pages
    assert len(body["note_ids"]) == 4

    # Overview note (first) carries headline + summary + TOC + top suggestions
    overview = client.notes_saved[0]
    assert overview["type"] == "ai"
    assert overview["title"].startswith("📋 00 · ") and "Overview" in overview["title"]
    assert "Demo project headline" in overview["content"]
    assert "First summary paragraph" in overview["content"]
    # TOC enumerates every page title
    assert "Architecture" in overview["content"]
    assert "Backend Internals" in overview["content"]
    assert "Risks" in overview["content"]
    # Top suggestions present
    assert "Verify X" in overview["content"]
    assert "Audit Y" in overview["content"]

    # Page 1: 📄 01 · Architecture
    p1 = client.notes_saved[1]
    assert p1["title"] == "📄 01 · Architecture"
    assert "Key concepts" in p1["content"]
    assert "💡 AI Suggestions" in p1["content"]

    # Page 2: 📄 02 · Backend Internals
    p2 = client.notes_saved[2]
    assert p2["title"] == "📄 02 · Backend Internals"

    # Page 3: 📄 03 · Risks
    p3 = client.notes_saved[3]
    assert p3["title"] == "📄 03 · Risks"

    # Render-order invariant: note_ids ordered Overview → Page 1 → ... → Page 3
    saved_ids_in_order = [n["id"] for n in client.notes_saved]
    assert body["note_ids"] == saved_ids_in_order


def test_studio_e2e_multipage_returns_overview_as_back_compat_note_id(client):
    """v0.7.119 E2E — `note_id` (single) must point at the Overview
    note for backward compatibility with the v0.7.88 frontend; `note_ids`
    is the full list. Without this back-compat the v0.7.105 Export UI
    would deep-link to a random page."""
    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "title": "E2E Demo"},
        files=[("files", ("a.txt", b"a content", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["note_id"] == body["note_ids"][0]
    overview = client.notes_saved[0]
    assert body["note_id"] == overview["id"]
