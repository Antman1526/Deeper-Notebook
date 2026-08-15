from __future__ import annotations

import asyncio
import hashlib
import inspect
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "source_visuals"
PDF_FIXTURE = FIXTURES / "fixture.pdf"
VIDEO_FIXTURE = FIXTURES / "fixture.mp4"
AUDIO_FIXTURE = FIXTURES / "fixture-artwork.m4a"


def test_deterministic_fixture_hashes_and_sizes() -> None:
    expected = {
        "fixture.pdf": (10804, "70157b96704b56a375b08409113f0ec9fe4a3dea3f667fe3d9dda9c5baf35851"),
        "fixture.mp4": (2366, "138e8e58cb9b5897685ceb8bf0e4e65f8af38e1cbe783531b0a95be242388fa2"),
        "fixture-artwork.m4a": (2196, "be46e54decae40cecee1bf092681415dc75f34ddec689affbf962f756161119a"),
    }
    for name, (size, digest) in expected.items():
        path = FIXTURES / name
        assert path.stat().st_size == size
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_extract_pdf_candidates_is_bounded_and_deduplicated() -> None:
    from deeper_notebook.source_visuals.extractors import extract_pdf_candidates

    candidates = extract_pdf_candidates(PDF_FIXTURE)
    assert candidates
    assert len(candidates) <= 64
    assert all(candidate.origin == "embedded" for candidate in candidates)
    assert all(1 <= candidate.locator["page"] <= 24 for candidate in candidates)
    assert len({hashlib.sha256(candidate.encoded_bytes).hexdigest() for candidate in candidates}) == len(candidates)


def test_extract_pdf_stops_after_64_inspected_embedded_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeper_notebook.source_visuals.extractors as extractors

    class FakePage:
        def get_images(self, *, full: bool) -> list[tuple[int]]:
            assert full is True
            return [(index,) for index in range(100)]

    class FakeDocument:
        def __init__(self) -> None:
            self.page = FakePage()
            self.extracted: list[int] = []

        def __len__(self) -> int:
            return 1

        def __getitem__(self, index: int) -> FakePage:
            assert index == 0
            return self.page

        def extract_image(self, xref: int) -> dict[str, bytes]:
            self.extracted.append(xref)
            return {"image": b"not a supported image"}

        def close(self) -> None:
            return None

    document = FakeDocument()
    monkeypatch.setattr(extractors.fitz, "open", lambda *_args, **_kwargs: document)

    assert extractors.extract_pdf_candidates(b"%PDF-fake") == []
    assert document.extracted == list(range(64))


def test_extract_pdf_ranking_is_stable() -> None:
    from deeper_notebook.source_visuals.extractors import extract_pdf_candidates
    from deeper_notebook.source_visuals.media import select_candidate

    first = select_candidate(extract_pdf_candidates(PDF_FIXTURE))
    second = select_candidate(extract_pdf_candidates(PDF_FIXTURE))
    assert first is not None and second is not None
    assert first.stable_key == second.stable_key
    assert first.encoded_bytes == second.encoded_bytes


def test_video_timestamps_are_exactly_25_50_75_percent() -> None:
    from deeper_notebook.source_visuals.extractors import video_timestamps_ms

    assert video_timestamps_ms(4_000) == (1_000, 2_000, 3_000)
    assert video_timestamps_ms(1) == (0,)
    assert video_timestamps_ms(0) == ()


def test_video_duration_parser_accepts_only_bounded_hh_mm_ss_xx() -> None:
    from deeper_notebook.source_visuals.extractors import (
        SourceVisualMediaError,
        _duration_ms_from_text,
    )

    assert _duration_ms_from_text(b"Duration: 00:01:02.50, start: 0.0") == 62_500
    for value in (b"Duration: 00:01:02.5,", b"Duration: 00:01:02.500,", b"Duration: 0:01:02.50,"):
        with pytest.raises(SourceVisualMediaError, match="VIDEO_DURATION_INVALID"):
            _duration_ms_from_text(value)


@pytest.mark.asyncio
async def test_extract_video_candidates_uses_three_bounded_timestamps() -> None:
    from deeper_notebook.source_visuals.extractors import extract_video_candidates

    candidates = await extract_video_candidates(VIDEO_FIXTURE)
    assert len(candidates) == 3
    assert [candidate.locator["timestamp_ms"] for candidate in candidates] == [1_000, 2_000, 3_000]
    assert all(candidate.origin == "video_frame" for candidate in candidates)


@pytest.mark.asyncio
async def test_video_attempt_timeout_is_15_seconds_and_total_timeout_is_60(monkeypatch: pytest.MonkeyPatch) -> None:
    import deeper_notebook.source_visuals.extractors as extractors

    monkeypatch.setattr(extractors, "VIDEO_FRAME_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(extractors, "VIDEO_JOB_TIMEOUT_SECONDS", 0.03)

    async def duration(_path: Path) -> int:
        return 4_000

    async def frame(_path: Path, _timestamp_ms: int) -> bytes:
        await asyncio.sleep(0.2)
        return b"never"

    monkeypatch.setattr(extractors, "_probe_video_duration", duration)
    monkeypatch.setattr(extractors, "_extract_video_frame", frame)
    with pytest.raises(extractors.SourceVisualMediaError, match="TIMEOUT"):
        await extractors.extract_video_candidates(VIDEO_FIXTURE)


@pytest.mark.asyncio
async def test_extract_video_subprocess_contract_is_async_bounded_and_no_shell() -> None:
    import deeper_notebook.source_visuals.extractors as extractors

    source = inspect.getsource(extractors)
    assert "asyncio.create_subprocess_exec" in source
    assert "create_subprocess_shell" not in source
    assert "shell=True" not in source
    assert "-nostdin" in source
    assert "terminate" in source and "kill" in source


@pytest.mark.asyncio
async def test_extract_audio_returns_embedded_artwork_only() -> None:
    from deeper_notebook.source_visuals.extractors import extract_audio_artwork

    candidate = await extract_audio_artwork(AUDIO_FIXTURE)
    assert candidate is not None
    assert candidate.origin == "audio_artwork"
    assert candidate.locator["resource_id"] == "attached-picture-0"


@pytest.mark.asyncio
async def test_audio_command_maps_one_picture_frame_not_the_audio_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeper_notebook.source_visuals.extractors as extractors

    calls: list[tuple[str, ...]] = []

    async def fake_run(*args: str, **_kwargs: object) -> tuple[bytes, bytes]:
        calls.append(args)
        return b"image-bytes", b"Stream #0:1: Video: mjpeg (attached pic)"

    monkeypatch.setattr(extractors, "_run_ffmpeg", fake_run)
    monkeypatch.setattr(extractors, "prepare_webp", lambda value: value)
    await extractors.extract_audio_artwork(AUDIO_FIXTURE)
    command = calls[0]
    assert "-map" in command and command[command.index("-map") + 1] == "0:v:0?"
    assert "-frames:v" in command and command[command.index("-frames:v") + 1] == "1"
    assert "0:a:0" not in command


@pytest.mark.asyncio
async def test_audio_without_attached_picture_falls_back_without_decoding_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeper_notebook.source_visuals.extractors as extractors

    async def fake_run(*_args: str, **_kwargs: object) -> tuple[bytes, bytes]:
        return b"", b"Stream #0:0: Audio: aac"

    monkeypatch.setattr(extractors, "_run_ffmpeg", fake_run)
    assert await extractors.extract_audio_artwork(AUDIO_FIXTURE) is None


@pytest.mark.asyncio
async def test_audio_missing_attached_stream_falls_back_without_audio_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import deeper_notebook.source_visuals.extractors as extractors

    async def missing_picture(*_args: str, **_kwargs: object) -> tuple[bytes, bytes]:
        raise extractors.SourceVisualMediaError("FFMPEG_FAILED")

    monkeypatch.setattr(extractors, "_run_ffmpeg", missing_picture)
    assert await extractors.extract_audio_artwork(AUDIO_FIXTURE) is None
