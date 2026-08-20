from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest
from PIL import Image
from pydantic import ValidationError

from deeper_notebook.video.captions import render_webvtt
from deeper_notebook.video.composer import VideoOverviewError, compose_video_overview
from deeper_notebook.video.contracts import VideoNarrationSegment, VideoOverviewDocument


def _audio(path: Path) -> None:
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=1",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _document(tmp_path: Path) -> VideoOverviewDocument:
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.new("RGB", (320, 180), "#154f6f").save(first)
    Image.new("RGB", (180, 320), "#4e8d59").save(second)
    narration = tmp_path / "narration.m4a"
    _audio(narration)
    return VideoOverviewDocument(
        slide_image_paths=[first, second],
        narration_audio_path=narration,
        narration_segments=[
            VideoNarrationSegment(
                start_seconds=0,
                end_seconds=0.4,
                text="A grounded opening --> with no injected cue.",
                citation_ids=["source-1"],
            ),
            VideoNarrationSegment(
                start_seconds=0.4,
                end_seconds=0.8,
                text="The closing finding remains local.",
                citation_ids=["source-2"],
            ),
        ],
        caption_language="en-US",
    )


def test_compose_video_overview_creates_decodable_mp4_and_safe_vtt(
    tmp_path: Path,
) -> None:
    output = compose_video_overview(_document(tmp_path), tmp_path / "outputs")

    assert output.mp4_path.is_file()
    assert output.mp4_path.stat().st_size > 1_000
    assert output.vtt_path.read_text(encoding="utf-8").startswith("WEBVTT\n")
    assert "--> with" not in output.vtt_path.read_text(encoding="utf-8")
    assert "00:00:00.000 --> 00:00:00.400" in output.vtt_path.read_text(
        encoding="utf-8"
    )
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-v",
            "error",
            "-i",
            str(output.mp4_path),
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def test_video_overview_contract_rejects_non_monotonic_or_oversized_documents(
    tmp_path: Path,
) -> None:
    document = _document(tmp_path)
    with pytest.raises(ValidationError, match="caption segments must be monotonic"):
        VideoOverviewDocument(
            slide_image_paths=document.slide_image_paths,
            narration_audio_path=document.narration_audio_path,
            narration_segments=[
                VideoNarrationSegment(start_seconds=0, end_seconds=1, text="One"),
                VideoNarrationSegment(start_seconds=0.5, end_seconds=2, text="Two"),
            ],
            caption_language="en",
        )

    with pytest.raises(ValidationError, match="may not exceed one hour"):
        VideoOverviewDocument(
            slide_image_paths=document.slide_image_paths,
            narration_audio_path=document.narration_audio_path,
            narration_segments=[
                VideoNarrationSegment(
                    start_seconds=0, end_seconds=3_601, text="Too long"
                )
            ],
            caption_language="en",
        )


def test_compose_video_overview_rejects_a_symlinked_input(tmp_path: Path) -> None:
    document = _document(tmp_path)
    symlink = tmp_path / "linked.png"
    symlink.symlink_to(document.slide_image_paths[0])
    unsafe = document.model_copy(update={"slide_image_paths": [symlink]})

    with pytest.raises(VideoOverviewError, match="unsupported local media input"):
        compose_video_overview(unsafe, tmp_path / "outputs")


def test_render_webvtt_renders_stable_timestamps() -> None:
    vtt = render_webvtt(
        [VideoNarrationSegment(start_seconds=65.2, end_seconds=65.25, text="Measured")]
    )
    assert "00:01:05.200 --> 00:01:05.250" in vtt
