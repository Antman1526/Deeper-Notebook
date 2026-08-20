"""ONP v0.7.0 — Tests for the Studio router.

These tests exercise the orchestration logic without spinning up
SurrealDB, content_core, or an LLM. The strategy:
  - Mock save_uploaded_file → returns a fake on-disk path
  - Mock content_core.extract_content → returns a fake ProcessSourceState
  - Mock Notebook/Source/Note save methods
  - Mock provision_langchain_model for notebook mode
  - Mock PodcastService.submit_generation_job for podcast mode

We verify:
  * Input validation (mode, file types, missing podcast profiles)
  * Multi-file ingestion creates the right Source + Notebook records
  * Notebook mode invokes the LLM with the combined context
  * Podcast mode submits the job and returns job_id
  * Extraction failures are surfaced as warnings without aborting if at
    least one file extracted successfully
  * All-files-fail-extraction returns 400 with notebook_id
"""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import studio as studio_mod

# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


@pytest.fixture
def app():
    """Bare app with just the studio router so tests don't trigger the
    full FastAPI lifespan (which would try to run DB migrations)."""
    a = FastAPI()
    a.include_router(studio_mod.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def patched_pipeline(monkeypatch):
    """Replace every external dependency with a programmable mock."""
    # save_uploaded_file → return a fake path
    saved_paths: list[str] = []

    # v0.7.1 — accepts the new max_bytes kwarg from studio_generate
    async def _save(upload, max_bytes=None):  # noqa: ARG001
        path = f"/fake/uploads/{upload.filename}"
        saved_paths.append(path)
        return path

    monkeypatch.setattr(studio_mod, "save_uploaded_file", _save)

    # content_core.extract_content — return parsed text matching the filename
    async def _extract(state):
        source_ref = getattr(state, "file_path", None) or getattr(state, "url", None)
        fake_content = f"[parsed content of {source_ref}]"
        return SimpleNamespace(
            content=fake_content,
            title=None,
            url=getattr(state, "url", None),
            file_path=getattr(state, "file_path", None),
        )

    # Patch the LAZY import that happens inside studio_generate. Insert a
    # synthetic module so `from content_core import extract_content` resolves.
    import sys

    fake_cc = SimpleNamespace(extract_content=_extract)
    fake_cc_common = SimpleNamespace(
        ProcessSourceState=lambda **kw: SimpleNamespace(**kw),
    )
    monkeypatch.setitem(sys.modules, "content_core", fake_cc)
    monkeypatch.setitem(sys.modules, "content_core.common", fake_cc_common)

    # Notebook / Source / Note save + add_to_notebook
    created_notebooks: list[dict] = []
    created_sources: list[dict] = []
    created_notes: list[dict] = []

    class _NotebookMock:
        def __init__(self, *, name, description=None):
            self.name = name
            self.description = description
            self.id = f"notebook:{len(created_notebooks)}"

        async def save(self):
            created_notebooks.append({"id": self.id, "name": self.name})

    class _SourceMock:
        def __init__(
            self,
            *,
            title=None,
            asset=None,
            topics=None,
            provenance=None,
            source_type=None,
        ):
            self.title = title
            self.asset = asset
            self.topics = topics or []
            self.provenance = provenance or {}
            self.source_type = source_type
            self.full_text = None
            self.id = f"source:{len(created_sources)}"

        async def save(self):
            created_sources.append(
                {
                    "id": self.id,
                    "title": self.title,
                    "full_text": self.full_text,
                    "source_type": self.source_type,
                    "provenance": self.provenance,
                    "asset": self.asset,
                }
            )

        async def add_to_notebook(self, _id):
            pass

        async def vectorize(self):
            return f"command:{self.id}"

    class _NoteMock:
        def __init__(self, *, title=None, content=None, note_type=None):
            self.title = title
            self.content = content
            self.note_type = note_type
            self.id = f"note:{len(created_notes)}"

        async def save(self):
            created_notes.append(
                {"id": self.id, "title": self.title, "content": self.content}
            )

        async def add_to_notebook(self, _id):
            pass

    monkeypatch.setattr(studio_mod, "Notebook", _NotebookMock)
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(studio_mod, "Note", _NoteMock)
    monkeypatch.setattr(studio_mod, "Asset", lambda **kw: SimpleNamespace(**kw))

    return {
        "saved_paths": saved_paths,
        "notebooks": created_notebooks,
        "sources": created_sources,
        "notes": created_notes,
    }


# ----------------------------------------------------------------------------
# Validation tests
# ----------------------------------------------------------------------------


def test_rejects_invalid_mode(client, patched_pipeline):
    r = client.post(
        "/api/studio/generate",
        data={"mode": "encyclopedia"},
        files=[("files", ("a.txt", b"hi", "text/plain"))],
    )
    assert r.status_code == 400
    assert "mode must be" in r.json()["detail"]


def test_rejects_no_files(client, patched_pipeline):
    r = client.post("/api/studio/generate", data={"mode": "notebook"})
    assert r.status_code == 400
    assert "file or link" in r.json()["detail"]


def test_rejects_invalid_link(client, patched_pipeline):
    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "links": "ftp://example.com/video"},
    )
    assert r.status_code == 400
    assert "http(s)" in r.json()["detail"]


def test_rejects_unsupported_file_type(client, patched_pipeline):
    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},
        files=[("files", ("evil.exe", b"MZ\x00\x00", "application/octet-stream"))],
    )
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]


def test_podcast_mode_requires_profiles(client, patched_pipeline):
    r = client.post(
        "/api/studio/generate",
        data={"mode": "podcast"},
        files=[("files", ("a.txt", b"content", "text/plain"))],
    )
    assert r.status_code == 400
    assert "episode_profile_name" in r.json()["detail"]


# ----------------------------------------------------------------------------
# Notebook-mode happy path
# ----------------------------------------------------------------------------


def test_notebook_mode_generates_and_saves_note(client, patched_pipeline, monkeypatch):
    """v0.7.89 — notebook mode is now multi-page: one outline pass (JSON)
    then one ainvoke per page. We verify the overall shape (status 200,
    note_ids list populated, both sources mentioned in context, notes
    saved) without coupling tightly to call counts."""
    # First ainvoke must return outline JSON; subsequent ainvokes return
    # page Markdown. Use side_effect to feed them in order.
    outline_json = (
        '{"headline": "test headline", "summary": "test summary paragraph.", '
        '"pages": ['
        '  {"title": "Page A", "focus": "First topic", "key_questions": ["q1"]},'
        '  {"title": "Page B", "focus": "Second topic", "key_questions": ["q2"]}'
        '], "top_suggestions": ["do thing one", "do thing two"]}'
    )
    page_markdown = "# Page Body\n\n## Key concepts\n- foo\n\n## 💡 AI Suggestions for this page\n- Verify foo"

    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content=outline_json),
            MagicMock(content=page_markdown),
            MagicMock(content=page_markdown),
        ]
    )

    async def _provision(*args, **kwargs):
        return fake_chain

    monkeypatch.setattr(studio_mod, "provision_langchain_model", _provision)

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "title": "My Test"},
        files=[
            ("files", ("doc1.txt", b"first source content", "text/plain")),
            ("files", ("doc2.md", b"# second source\n\ncontent", "text/markdown")),
        ],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "notebook"
    assert body["notebook_id"].startswith("notebook:")
    assert body["note_id"].startswith("note:")  # overview note (back-compat)
    assert isinstance(body["note_ids"], list)
    # 1 overview + 2 pages = 3 notes
    assert len(body["note_ids"]) == 3
    assert body["note_ids"][0] == body["note_id"]  # overview is first
    assert len(body["source_ids"]) == 2
    assert body["title"] == "My Test"

    # The LLM was invoked at least three times (outline + 2 pages)
    assert fake_chain.ainvoke.call_count == 3
    # The first call carried the outline prompt; subsequent calls carried
    # page-generation prompts. We don't assert literal strings (prompts
    # may evolve); we DO confirm the source filenames reached the LLM.
    first_call_messages = fake_chain.ainvoke.call_args_list[0][0][0]
    combined = first_call_messages[1].content  # HumanMessage content
    assert "doc1.txt" in combined
    assert "doc2.md" in combined

    # Three notes saved (overview + 2 pages). The overview must contain
    # the headline; each page note must contain the page markdown body.
    assert len(patched_pipeline["notes"]) == 3
    overview_note = patched_pipeline["notes"][0]
    assert "test headline" in overview_note["content"]
    assert "Page A" in overview_note["content"]
    assert "Page B" in overview_note["content"]
    for page_note in patched_pipeline["notes"][1:]:
        assert "💡 AI Suggestions" in page_note["content"]


def test_notebook_mode_accepts_link_only_sources(client, patched_pipeline, monkeypatch):
    outline_json = (
        '{"headline": "link headline", "summary": "link summary.", '
        '"pages": ['
        '  {"title": "Link Page", "focus": "Web source", "key_questions": ["q1"]}'
        '], "top_suggestions": ["check source"]}'
    )
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content=outline_json),
            MagicMock(
                content="# Link Page\n\n## 💡 AI Suggestions for this page\n- act"
            ),
        ]
    )
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={
            "mode": "notebook",
            "title": "Link Training",
            "links": "https://example.com/training/video",
        },
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "notebook"
    assert len(body["source_ids"]) == 1
    assert body["title"] == "Link Training"
    last_source = patched_pipeline["sources"][-1]
    assert last_source["source_type"] == "link"
    assert last_source["asset"].url == "https://example.com/training/video"
    assert last_source["provenance"]["origin"] == "studio_generate"
    assert "https://example.com/training/video" in last_source["full_text"]

    first_call_messages = fake_chain.ainvoke.call_args_list[0][0][0]
    combined = first_call_messages[1].content
    assert "https://example.com/training/video" in combined


def test_notebook_mode_falls_back_to_single_note_when_outline_unparseable(
    client, patched_pipeline, monkeypatch
):
    """v0.7.89 — if the outline pass returns un-parseable JSON, the
    pipeline must NOT 502. It falls back to legacy single-note generation
    and surfaces a warning so the user knows what happened."""
    fake_chain = MagicMock()
    # First call (outline): not JSON. Second call (single-note fallback):
    # plain markdown. Subsequent ainvokes shouldn't happen.
    fake_chain.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content="Sorry, I cannot follow JSON instructions."),
            MagicMock(content="# Fallback Study Notes\n\nFallback content."),
        ]
    )
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "title": "Fallback Test"},
        files=[("files", ("a.txt", b"content", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "notebook"
    assert len(body["note_ids"]) == 1  # single fallback note
    assert any(
        "fell back" in w.lower() or "outline" in w.lower() for w in body["warnings"]
    )
    assert "Fallback Study Notes" in patched_pipeline["notes"][0]["content"]


def test_notebook_mode_single_note_when_multipage_disabled(
    client, patched_pipeline, monkeypatch
):
    """v0.7.89 — DEEPER_NOTEBOOK_STUDIO_NOTEBOOK_MULTIPAGE=false routes to the
    legacy single-note path immediately, no outline call."""
    monkeypatch.setattr(studio_mod, "_MULTIPAGE_ENABLED", False)
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        return_value=MagicMock(
            content="# Disabled-mode Notes\n\nbody",
        )
    )
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )
    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},
        files=[("files", ("a.txt", b"content", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["note_ids"]) == 1
    # Only one LLM call — the legacy single-note path
    assert fake_chain.ainvoke.call_count == 1
    assert "Disabled-mode Notes" in patched_pipeline["notes"][0]["content"]


def test_notebook_mode_title_auto_defaults_from_filename(
    client, patched_pipeline, monkeypatch
):
    """v0.7.89 — outline can return un-parseable text and we'll fall back
    to single-note (still 200). The title-from-filename behavior is what
    we're verifying here, not the LLM output shape."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content="not json"),  # outline → triggers fallback
            MagicMock(content="# Fallback notes"),  # single-note pass
        ]
    )
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},  # no title
        files=[
            (
                "files",
                ("Quantum Computing Primer.pdf", b"%PDF-1.4 ...", "application/pdf"),
            )
        ],
    )
    assert r.status_code == 200
    assert "Quantum Computing Primer" in r.json()["title"]


# ----------------------------------------------------------------------------
# Notebook-mode error handling
# ----------------------------------------------------------------------------


def test_notebook_mode_returns_400_when_no_text_extracted(
    client, patched_pipeline, monkeypatch
):
    # Patch extract_content to return empty content for every file
    import sys

    async def _empty_extract(_state):
        return SimpleNamespace(
            content="", title=None, url=None, file_path=_state.file_path
        )

    fake_cc = SimpleNamespace(extract_content=_empty_extract)
    monkeypatch.setitem(sys.modules, "content_core", fake_cc)

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},
        files=[("files", ("blank.pdf", b"%PDF-1.4 ...", "application/pdf"))],
    )
    assert r.status_code == 400
    assert "No usable text" in r.json()["detail"]


def test_notebook_mode_llm_failure_returns_502_with_notebook_id(
    client, patched_pipeline, monkeypatch
):
    """If the LLM call fails, the user's uploaded sources are STILL saved
    (visible in /notebooks). The error message must include notebook_id
    so the user can recover their content."""

    async def _provision_failing(*args, **kwargs):
        raise RuntimeError("simulated LLM provider down")

    monkeypatch.setattr(studio_mod, "provision_langchain_model", _provision_failing)

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},
        files=[("files", ("a.txt", b"content", "text/plain"))],
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "notebook:" in detail
    assert "simulated LLM provider down" in detail


# ----------------------------------------------------------------------------
# Podcast-mode happy path
# ----------------------------------------------------------------------------


def test_podcast_mode_submits_job_and_returns_job_id(
    client, patched_pipeline, monkeypatch
):
    submit_calls: list[dict] = []

    async def _submit(**kwargs):
        submit_calls.append(kwargs)
        return "command:podcast-123"

    monkeypatch.setattr(
        studio_mod.PodcastService,
        "submit_generation_job",
        _submit,
    )

    r = client.post(
        "/api/studio/generate",
        data={
            "mode": "podcast",
            "title": "Quantum Pod",
            "episode_profile_name": "Open Notebook Plus Local",
            "speaker_profile_name": "default",
        },
        files=[("files", ("paper.pdf", b"%PDF-1.4 content", "application/pdf"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "podcast"
    assert body["job_id"] == "command:podcast-123"
    assert body["notebook_id"].startswith("notebook:")

    # The job was submitted with the right args
    assert len(submit_calls) == 1
    call = submit_calls[0]
    assert call["episode_profile_name"] == "Open Notebook Plus Local"
    assert call["speaker_profile_name"] == "default"
    assert call["episode_name"] == "Quantum Pod"
    assert call["notebook_id"].startswith("notebook:")
    # The briefing suffix tells the LLM to stay grounded
    assert "grounded" in call["briefing_suffix"]


# ----------------------------------------------------------------------------
# Partial-failure: one file extracts, another doesn't
# ----------------------------------------------------------------------------


def test_partial_extraction_still_generates_with_warning(
    client, patched_pipeline, monkeypatch
):
    """One PDF parses, another fails — generation proceeds with what we
    have, and the warning surfaces in the response so the UI can show it."""

    import sys

    async def _extract_one_fails(state):
        if "bad" in state.file_path:
            raise ValueError("simulated parser failure")
        return SimpleNamespace(
            content=f"parsed: {state.file_path}",
            title=None,
            url=None,
            file_path=state.file_path,
        )

    fake_cc = SimpleNamespace(extract_content=_extract_one_fails)
    monkeypatch.setitem(sys.modules, "content_core", fake_cc)

    # v0.7.89 — outline first, then one page (we only need the *generation
    # path* to succeed; the warning under test is about file parsing).
    fake_chain = MagicMock()
    outline_json = (
        '{"headline": "h", "summary": "s.", '
        '"pages": [{"title": "P", "focus": "f", "key_questions": ["q"]}], '
        '"top_suggestions": ["x"]}'
    )
    fake_chain.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content=outline_json),
            MagicMock(content="# P\n\n## 💡 AI Suggestions for this page\n- act"),
        ]
    )
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},
        files=[
            ("files", ("good.txt", b"good", "text/plain")),
            ("files", ("bad.pdf", b"bad", "application/pdf")),
        ],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["note_id"] is not None  # generation succeeded (overview)
    # The bad file's failure shows up in warnings
    assert any("bad.pdf" in w for w in body["warnings"])
    # Both sources were created even though one failed parsing
    assert len(body["source_ids"]) == 2


# ----------------------------------------------------------------------------
# v0.7.1 — Regression tests for code-review fixes
# ----------------------------------------------------------------------------


def test_studio_passes_max_bytes_to_save_uploaded_file(client, monkeypatch):
    """v0.7.1 Issue #1 regression: chunked-transfer uploads bypass the
    UploadFile.size check. save_uploaded_file's new max_bytes kwarg must
    be passed by Studio so the cap is enforced mid-stream regardless of
    whether Content-Length was set."""
    import sys

    captured_kwargs: list[dict] = []

    async def _save_recording(upload, max_bytes=None):
        captured_kwargs.append({"max_bytes": max_bytes, "name": upload.filename})
        return f"/fake/uploads/{upload.filename}"

    monkeypatch.setattr(studio_mod, "save_uploaded_file", _save_recording)

    # Need to stub the rest of the pipeline too — re-use the same fakes
    # as patched_pipeline but inline (since we replace save_uploaded_file).
    async def _extract(state):
        return SimpleNamespace(
            content="text", title=None, url=None, file_path=state.file_path
        )

    fake_cc = SimpleNamespace(extract_content=_extract)
    fake_cc_common = SimpleNamespace(
        ProcessSourceState=lambda **kw: SimpleNamespace(**kw),
    )
    monkeypatch.setitem(sys.modules, "content_core", fake_cc)
    monkeypatch.setitem(sys.modules, "content_core.common", fake_cc_common)

    class _NotebookMock:
        def __init__(self, *, name, description=None):
            self.name, self.id = name, "notebook:0"

        async def save(self):
            pass

    class _SourceMock:
        def __init__(self, **_kw):
            self.id, self.full_text, self.title = "source:0", None, None

        async def save(self):
            pass

        async def add_to_notebook(self, _id):
            pass

        async def vectorize(self):
            pass

    class _NoteMock:
        def __init__(self, **kw):
            self.id, self.title, self.content = (
                "note:0",
                kw.get("title"),
                kw.get("content"),
            )

        async def save(self):
            pass

        async def add_to_notebook(self, _id):
            pass

    monkeypatch.setattr(studio_mod, "Notebook", _NotebookMock)
    monkeypatch.setattr(studio_mod, "Source", _SourceMock)
    monkeypatch.setattr(studio_mod, "Note", _NoteMock)
    monkeypatch.setattr(studio_mod, "Asset", lambda **kw: SimpleNamespace(**kw))

    # v0.7.89 — outline + at-least-one page in the multi-page flow.
    fake_chain = MagicMock()
    outline_json = (
        '{"headline": "h", "summary": "s.", '
        '"pages": [{"title": "P", "focus": "f", "key_questions": ["q"]}], '
        '"top_suggestions": ["x"]}'
    )
    fake_chain.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content=outline_json),
            MagicMock(content="# P body"),
        ]
    )
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    # The crucial assertion: max_bytes was passed, and it equals the
    # module constant. If a future refactor accidentally drops the kwarg,
    # the chunked-upload DoS is reopened — this test catches it.
    assert len(captured_kwargs) == 1
    assert captured_kwargs[0]["max_bytes"] == studio_mod._MAX_FILE_BYTES


def test_brief_truncates_long_exception_messages():
    """v0.7.1 Issue #4 regression: _brief() caps exception strings at
    _MAX_WARNING_LEN so a 10 KB parser error doesn't balloon the response
    payload or leak path info."""
    long_msg = "x" * 5000
    fake_exc = ValueError(long_msg)
    result = studio_mod._brief(fake_exc)
    assert len(result) <= studio_mod._MAX_WARNING_LEN
    assert result.endswith("…")  # ellipsis on truncation


def test_brief_passes_short_messages_through():
    """Short exception messages are not modified — no ellipsis tacked on."""
    short = ValueError("plain bug")
    result = studio_mod._brief(short)
    assert result == "plain bug"
    assert not result.endswith("…")


# ----------------------------------------------------------------------------
# v0.7.4 — Local-model-friendly default tests
# ----------------------------------------------------------------------------


def test_default_caps_are_local_model_friendly():
    """v0.7.4: defaults must be sized for 8k-32k context local models, not
    cloud frontier models. If anyone bumps the defaults back up to cloud
    sizes, this test catches it — local users would silently start
    hitting context-overflow errors."""
    # Per-file cap ≤ 20k chars (~5k tokens; leaves room for combined cap)
    assert studio_mod._MAX_EXTRACT_CHARS_PER_FILE <= 20_000, (
        f"_MAX_EXTRACT_CHARS_PER_FILE={studio_mod._MAX_EXTRACT_CHARS_PER_FILE} "
        "is too large for local 8k-context models"
    )
    # Combined cap ≤ 80k chars (~20k tokens; fits in a 32k-context model
    # alongside the system prompt + 8k output budget)
    assert studio_mod._MAX_COMBINED_CHARS <= 80_000, (
        f"_MAX_COMBINED_CHARS={studio_mod._MAX_COMBINED_CHARS} "
        "is too large for local 32k-context models"
    )


def test_env_overrides_lift_studio_caps_for_cloud_users(monkeypatch):
    """Cloud users who configure a large-context model (or use cloud APIs)
    must be able to lift the caps via env vars without code changes."""
    import importlib

    monkeypatch.setenv("DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS", "100000")
    monkeypatch.setenv("DEEPER_NOTEBOOK_STUDIO_MAX_COMBINED_CHARS", "500000")
    # Re-import to pick up the env values (module-level constants)
    importlib.reload(studio_mod)
    try:
        assert studio_mod._MAX_EXTRACT_CHARS_PER_FILE == 100_000
        assert studio_mod._MAX_COMBINED_CHARS == 500_000
    finally:
        # Restore module to default state for other tests
        monkeypatch.delenv("DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS", raising=False)
        monkeypatch.delenv("DEEPER_NOTEBOOK_STUDIO_MAX_COMBINED_CHARS", raising=False)
        importlib.reload(studio_mod)


def test_invalid_env_var_falls_back_to_default(monkeypatch):
    """Garbage in the env var must not crash startup. Module load must
    survive DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS=banana with a warning + fallback."""
    import importlib

    monkeypatch.setenv("DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS", "banana")
    importlib.reload(studio_mod)
    try:
        # Falls back to default (15_000)
        assert studio_mod._MAX_EXTRACT_CHARS_PER_FILE == 15_000
    finally:
        monkeypatch.delenv("DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS", raising=False)
        importlib.reload(studio_mod)


def test_negative_env_var_falls_back_to_default(monkeypatch):
    """A negative value (typo, miscalc) must not produce an invalid cap."""
    import importlib

    monkeypatch.setenv("DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS", "-1")
    importlib.reload(studio_mod)
    try:
        assert studio_mod._MAX_EXTRACT_CHARS_PER_FILE == 15_000
    finally:
        monkeypatch.delenv("DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS", raising=False)
        importlib.reload(studio_mod)


# ----------------------------------------------------------------------------
# Context-overflow error messaging
# ----------------------------------------------------------------------------


def test_context_overflow_error_includes_local_model_hint():
    """v0.7.4: when the LLM rejects the request because of context-window
    overflow, the error detail must point users at the new env vars so
    they can actually fix it. Otherwise local users see a confusing raw
    server error and just retry, hitting the same wall."""
    exc = ValueError("Error: prompt is too long for context length 8192")
    detail = studio_mod._studio_generation_error_detail(
        exc,
        notebook_id="notebook:abc",
        source_count=3,
    )
    assert "context window" in detail.lower()
    assert "DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS" in detail
    assert "DEEPER_NOTEBOOK_STUDIO_MAX_COMBINED_CHARS" in detail
    assert "notebook:abc" in detail  # user can still recover content


def test_generic_error_omits_local_model_hint():
    """A generic LLM error (auth failure, network) doesn't get the
    local-model hint — that'd be misleading."""
    exc = RuntimeError("HTTP 401 Unauthorized")
    detail = studio_mod._studio_generation_error_detail(
        exc,
        notebook_id="notebook:abc",
        source_count=1,
    )
    # No misleading local-model advice
    assert "DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS" not in detail
    # But still includes notebook_id for recovery
    assert "notebook:abc" in detail


def test_overflow_error_pattern_matching_is_case_insensitive():
    """Different LLM servers use different casings. Match should be
    case-insensitive."""
    variants = [
        "Context Length Exceeded",
        "MAX_TOKENS exceeded",
        "prompt is too long",
        "Exceeds the model's context size",
    ]
    for msg in variants:
        exc = ValueError(msg)
        detail = studio_mod._studio_generation_error_detail(
            exc,
            notebook_id="notebook:x",
            source_count=1,
        )
        assert "DEEPER_NOTEBOOK_STUDIO_MAX_FILE_CHARS" in detail, (
            f"pattern not matched for {msg!r}"
        )


# ----------------------------------------------------------------------------
# v0.7.92 / v0.7.93 — Parallel pages + per-page timeout
# ----------------------------------------------------------------------------


def test_page_timeout_becomes_warning_other_pages_ship(
    client,
    patched_pipeline,
    monkeypatch,
):
    """v0.7.93 — if one page times out, the rest must still ship and the
    timeout becomes a per-page warning (not a 504 that kills the whole
    notebook). Verifies the per-page timeout AND the warning text guides
    the user toward the env knob."""
    import asyncio

    # Shorten the timeout so the test runs fast
    monkeypatch.setattr(studio_mod, "_PAGE_TIMEOUT_SEC", 1)
    outline_json = (
        '{"headline": "h", "summary": "s.", '
        '"pages": ['
        ' {"title": "Fast Page", "focus": "f1", "key_questions": ["q1"]},'
        ' {"title": "Slow Page", "focus": "f2", "key_questions": ["q2"]}'
        '], "top_suggestions": ["x"]}'
    )

    call_order: list[str] = []

    async def _slow_invoke(messages):
        # First call (outline) returns immediately. Second call (Fast
        # Page) returns immediately. Third call (Slow Page) hangs past
        # the 1s timeout.
        idx = len(call_order)
        call_order.append(f"call-{idx}")
        if idx == 0:
            return MagicMock(content=outline_json)
        if idx == 1:
            return MagicMock(content="# Fast Page body\n\nfast")
        # Slow page — hang well past the 1s timeout
        await asyncio.sleep(10)
        return MagicMock(content="never returned")

    fake_chain = MagicMock()
    fake_chain.ainvoke = _slow_invoke
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "title": "Timeout Test"},
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Overview + Fast Page = 2 notes (Slow Page failed)
    assert len(body["note_ids"]) == 2
    # The Slow Page failure shows up as a warning naming the page AND
    # pointing at the timeout env knob (actionable, per v0.7.93 design)
    assert any(
        "Slow Page" in w and "DEEPER_NOTEBOOK_STUDIO_PAGE_TIMEOUT_SEC" in w
        for w in body["warnings"]
    ), body["warnings"]


def test_outline_timeout_returns_504_with_actionable_detail(
    client,
    patched_pipeline,
    monkeypatch,
):
    """v0.7.93 — outline-pass timeout returns 504 (Gateway Timeout) NOT 502.
    The detail message must include the env-knob name so users can recover
    rather than just see a wall of stack trace."""
    import asyncio

    monkeypatch.setattr(studio_mod, "_OUTLINE_TIMEOUT_SEC", 1)

    async def _hang_invoke(messages):
        await asyncio.sleep(10)
        return MagicMock(content="never returned")

    fake_chain = MagicMock()
    fake_chain.ainvoke = _hang_invoke
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook"},
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert r.status_code == 504, r.text
    detail = r.json()["detail"]
    assert "timed out" in detail.lower()
    assert "DEEPER_NOTEBOOK_STUDIO_OUTLINE_TIMEOUT_SEC" in detail
    # User can still recover their uploaded sources
    assert "notebook:" in detail


def test_parallel_pages_env_knob_changes_generation_strategy(
    client,
    patched_pipeline,
    monkeypatch,
):
    """v0.7.92 — with DEEPER_NOTEBOOK_STUDIO_NOTEBOOK_PARALLEL_PAGES=true, all pages
    are generated concurrently (asyncio.gather) instead of in a for-loop.
    Verifies the knob actually changes behavior — sequential calls happen
    one at a time (in_flight peaks at 1); parallel calls overlap
    (in_flight peaks > 1)."""
    import asyncio

    monkeypatch.setattr(studio_mod, "_PARALLEL_PAGES", True)

    outline_json = (
        '{"headline": "h", "summary": "s.", '
        '"pages": ['
        ' {"title": "P1", "focus": "f1", "key_questions": ["q1"]},'
        ' {"title": "P2", "focus": "f2", "key_questions": ["q2"]},'
        ' {"title": "P3", "focus": "f3", "key_questions": ["q3"]}'
        '], "top_suggestions": ["x"]}'
    )

    in_flight = 0
    peak_in_flight = 0
    lock = asyncio.Lock()
    call_idx = 0

    async def _track_invoke(messages):
        nonlocal in_flight, peak_in_flight, call_idx
        my_idx = call_idx
        call_idx += 1
        if my_idx == 0:
            # outline call — fast
            return MagicMock(content=outline_json)
        async with lock:
            in_flight += 1
            if in_flight > peak_in_flight:
                peak_in_flight = in_flight
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return MagicMock(content=f"# P{my_idx} body")

    fake_chain = MagicMock()
    fake_chain.ainvoke = _track_invoke
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "title": "Parallel Test"},
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    # All 3 pages + overview = 4 notes saved
    assert len(r.json()["note_ids"]) == 4
    # Peak in_flight should be > 1 since pages run in parallel.
    # Sequential mode (default) would have peaked at 1.
    assert peak_in_flight > 1, (
        f"Expected concurrent execution (peak > 1), got peak={peak_in_flight}"
    )


def test_parallel_pages_off_by_default_runs_sequentially(
    client,
    patched_pipeline,
    monkeypatch,
):
    """v0.7.92 — Verify the default (sequential) path. Same instrumentation
    as the parallel test, but without flipping the knob, peak concurrency
    must stay at 1."""
    import asyncio

    # Explicitly assert the default — guards against accidental flip.
    monkeypatch.setattr(studio_mod, "_PARALLEL_PAGES", False)

    outline_json = (
        '{"headline": "h", "summary": "s.", '
        '"pages": ['
        ' {"title": "P1", "focus": "f1", "key_questions": ["q1"]},'
        ' {"title": "P2", "focus": "f2", "key_questions": ["q2"]}'
        '], "top_suggestions": ["x"]}'
    )

    in_flight = 0
    peak_in_flight = 0
    lock = asyncio.Lock()
    call_idx = 0

    async def _track_invoke(messages):
        nonlocal in_flight, peak_in_flight, call_idx
        my_idx = call_idx
        call_idx += 1
        if my_idx == 0:
            return MagicMock(content=outline_json)
        async with lock:
            in_flight += 1
            if in_flight > peak_in_flight:
                peak_in_flight = in_flight
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return MagicMock(content=f"# P{my_idx} body")

    fake_chain = MagicMock()
    fake_chain.ainvoke = _track_invoke
    monkeypatch.setattr(
        studio_mod,
        "provision_langchain_model",
        AsyncMock(return_value=fake_chain),
    )

    r = client.post(
        "/api/studio/generate",
        data={"mode": "notebook", "title": "Sequential Test"},
        files=[("files", ("a.txt", b"x", "text/plain"))],
    )
    assert r.status_code == 200, r.text
    # Default sequential mode → peak concurrency = 1
    assert peak_in_flight == 1, (
        f"Expected sequential execution (peak == 1), got peak={peak_in_flight}"
    )
