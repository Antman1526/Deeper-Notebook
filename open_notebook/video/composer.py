"""Compose and verify local Video Overview media without external services."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg

from .captions import render_webvtt
from .contracts import VideoOverviewDocument, VideoOverviewOutput


class VideoOverviewError(ValueError):
    pass


def _safe_file(path: Path, suffixes: set[str]) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise VideoOverviewError(f"required local media is unavailable: {path}") from exc
    if path.is_symlink() or not resolved.is_file() or resolved.suffix.lower() not in suffixes:
        raise VideoOverviewError(f"unsupported local media input: {path}")
    return resolved


def _duration(document: VideoOverviewDocument) -> float:
    return document.narration_segments[-1].end_seconds


def _video_filter(slide_count: int) -> str:
    prepared = []
    for index in range(slide_count):
        prepared.append(
            f"[{index}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
            f"[slide{index}]"
        )
    concat_inputs = "".join(f"[slide{index}]" for index in range(slide_count))
    prepared.append(f"{concat_inputs}concat=n={slide_count}:v=1:a=0,format=yuv420p[v]")
    return ";".join(prepared)


def compose_video_overview(document: VideoOverviewDocument, output_dir: Path) -> VideoOverviewOutput:
    """Create MP4/VTT locally and promote only after an FFmpeg decode pass."""
    slides = [_safe_file(path, {".png", ".jpg", ".jpeg"}) for path in document.slide_image_paths]
    narration = _safe_file(document.narration_audio_path, {".aac", ".m4a", ".mp3", ".wav"})
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    total_duration = _duration(document)
    with tempfile.TemporaryDirectory(prefix="onp-video-") as temporary:
        temp = Path(temporary)
        vtt = temp / "captions.vtt"
        vtt.write_text(render_webvtt(document.narration_segments), encoding="utf-8")
        mp4 = temp / "overview.mp4"
        # Each slide has an equal share of the narration. This is deterministic
        # and avoids untrusted timing/filter strings from model output.
        share = total_duration / len(slides)
        command = [ffmpeg, "-y"]
        for slide in slides:
            command.extend(
                ["-loop", "1", "-framerate", "30", "-t", f"{share:.3f}", "-i", str(slide)]
            )
        command.extend(["-i", str(narration)])
        command.extend(
            [
                "-filter_complex",
                _video_filter(len(slides)),
                "-map",
                "[v]",
                "-map",
                f"{len(slides)}:a:0",
                "-t",
                f"{total_duration:.3f}",
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(mp4),
            ]
        )
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=max(60, int(total_duration * 10)))
            subprocess.run([ffmpeg, "-v", "error", "-i", str(mp4), "-f", "null", "-"], check=True, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise VideoOverviewError("local FFmpeg composition or validation failed") from exc
        stem = f"video-overview-{os.urandom(6).hex()}"
        final_mp4, final_vtt = output_dir / f"{stem}.mp4", output_dir / f"{stem}.vtt"
        os.replace(mp4, final_mp4)
        os.replace(vtt, final_vtt)
    return VideoOverviewOutput(mp4_path=final_mp4, vtt_path=final_vtt, duration_seconds=total_duration)
