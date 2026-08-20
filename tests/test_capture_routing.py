"""Focused safety and model-boundary coverage for private voice-note routing."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.routers.capture import _route_capture_media
from api.schemas.capture import CaptureRouteRequest
from deeper_notebook.capture.contracts import CaptureInboxItem
from deeper_notebook.capture.fingerprints import fingerprint_file
from deeper_notebook.capture.routing import (
    CaptureNotebook,
    CaptureRoutingService,
)


class _Transcript:
    text = "Plan the next local research milestone."


class _SpeechToTextModel:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    async def atranscribe(self, *, audio_file: Path) -> _Transcript:
        self.paths.append(audio_file)
        return _Transcript()


class _UnavailableSpeechToTextModel:
    async def atranscribe(self, *, audio_file: Path) -> _Transcript:
        raise RuntimeError("local STT is offline")


class _CaptureDatabase:
    def __init__(self, root: Path, item: CaptureInboxItem) -> None:
        self._root = root
        self._item = item

    async def list_roots(self) -> list[str]:
        return [str(self._root)]

    async def list_items(self, *, limit: int = 200) -> list[CaptureInboxItem]:
        assert limit >= 1
        return [self._item]


def _ready_item(root: Path, media: Path) -> CaptureInboxItem:
    fingerprint = fingerprint_file(media)
    return CaptureInboxItem(
        root_path=str(root),
        relative_path=media.relative_to(root).as_posix(),
        filename=media.name,
        extension=media.suffix,
        state="ready",
        sha256=fingerprint.sha256,
        byte_size=fingerprint.byte_size,
        modified_ns=media.stat().st_mtime_ns,
    )


@pytest.fixture
def stable_media(tmp_path: Path) -> tuple[Path, Path, CaptureInboxItem]:
    root = tmp_path / "inbox"
    root.mkdir()
    media = root / "voice-note.m4a"
    media.write_bytes(b"private local voice note")
    return root, media, _ready_item(root, media)


@pytest.mark.asyncio
async def test_routes_ready_media_with_context_and_approval_required(
    stable_media: tuple[Path, Path, CaptureInboxItem],
) -> None:
    root, media, item = stable_media
    model = _SpeechToTextModel()

    async def get_speech_to_text() -> _SpeechToTextModel:
        return model

    service = CaptureRoutingService(
        approved_roots=[root],
        capture_items=[item],
        notebooks=[
            CaptureNotebook(id="notebook:local", name="Local Research"),
            CaptureNotebook(id="notebook:plans", name="Plans"),
            CaptureNotebook(id="notebook:archive", name="Archive"),
            CaptureNotebook(id="notebook:extra", name="Extra"),
        ],
        get_speech_to_text=get_speech_to_text,
    )

    result = await service.route(media)

    assert result.state == "ready"
    assert result.transcript == "Plan the next local research milestone."
    assert result.source.sha256 == item.sha256
    assert result.source.path == str(media)
    assert result.approval_required is True
    assert len(result.notebook_suggestions) <= 3
    assert model.paths == [media]
    assert media.read_bytes() == b"private local voice note"


@pytest.mark.asyncio
async def test_prefers_injected_local_semantic_notebook_suggestions(
    stable_media: tuple[Path, Path, CaptureInboxItem],
) -> None:
    root, media, item = stable_media

    async def get_speech_to_text() -> _SpeechToTextModel:
        return _SpeechToTextModel()

    async def semantic_suggester(transcript, source, notebooks):
        assert transcript.startswith("Plan the next")
        assert source.path == str(media)
        assert [notebook.id for notebook in notebooks] == ["notebook:semantic"]
        return [
            CaptureNotebook(id="notebook:semantic", name="Unrelated title").model_copy(
                update={"score": 0.91, "reason": "Local semantic match"}
            )
        ]

    # The service contract accepts the stricter suggestion subtype, while this
    # fixture keeps the test independent of a running embedding provider.
    async def typed_semantic_suggester(transcript, source, notebooks):
        await semantic_suggester(transcript, source, notebooks)
        from deeper_notebook.capture.routing import CaptureNotebookSuggestion

        return [
            CaptureNotebookSuggestion(
                id="notebook:semantic",
                name="Unrelated title",
                score=0.91,
                reason="Local semantic match",
            )
        ]

    result = await CaptureRoutingService(
        approved_roots=[root],
        capture_items=[item],
        notebooks=[CaptureNotebook(id="notebook:semantic", name="Unrelated title")],
        get_speech_to_text=get_speech_to_text,
        semantic_suggester=typed_semantic_suggester,
    ).route(media)

    assert result.notebook_suggestions[0].reason == "Local semantic match"
    assert result.notebook_suggestions[0].score == 0.91


@pytest.mark.asyncio
async def test_returns_typed_no_model_state_without_fallback(
    stable_media: tuple[Path, Path, CaptureInboxItem],
) -> None:
    root, media, item = stable_media

    async def no_speech_to_text() -> None:
        return None

    result = await CaptureRoutingService(
        approved_roots=[root],
        capture_items=[item],
        notebooks=[],
        get_speech_to_text=no_speech_to_text,
    ).route(media)

    assert result.state == "no_model"
    assert result.transcript is None
    assert result.notebook_suggestions == []


@pytest.mark.asyncio
async def test_returns_typed_unavailable_state_without_cloud_fallback(
    stable_media: tuple[Path, Path, CaptureInboxItem],
) -> None:
    root, media, item = stable_media

    async def unavailable_speech_to_text() -> _UnavailableSpeechToTextModel:
        return _UnavailableSpeechToTextModel()

    result = await CaptureRoutingService(
        approved_roots=[root],
        capture_items=[item],
        notebooks=[],
        get_speech_to_text=unavailable_speech_to_text,
    ).route(media)

    assert result.state == "unavailable"
    assert result.transcript is None


@pytest.mark.asyncio
async def test_router_helper_uses_capture_database_stub_and_default_model_stub(
    stable_media: tuple[Path, Path, CaptureInboxItem],
) -> None:
    root, media, item = stable_media
    database = _CaptureDatabase(root, item)
    model = _SpeechToTextModel()

    async def get_speech_to_text() -> _SpeechToTextModel:
        return model

    async def load_notebooks() -> list[CaptureNotebook]:
        return [CaptureNotebook(id="notebook:local", name="Local Research")]

    response = await _route_capture_media(
        CaptureRouteRequest(path=str(media)),
        repository=database,
        get_speech_to_text=get_speech_to_text,
        load_notebooks=load_notebooks,
    )

    assert response.state == "ready"
    assert response.source.sha256 == item.sha256
    assert response.approval_required is True
