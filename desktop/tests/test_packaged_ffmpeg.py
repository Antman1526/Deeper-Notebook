"""Contract for the package-managed FFmpeg runtime used by local video work."""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg


def test_imageio_ffmpeg_resolves_and_executes_version() -> None:
    executable = Path(imageio_ffmpeg.get_ffmpeg_exe())

    assert executable.is_file(), "imageio-ffmpeg did not provide an executable"
    completed = subprocess.run(
        [str(executable), "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert "ffmpeg version" in completed.stdout.lower()


def test_imageio_ffmpeg_encodes_and_decodes_tiny_local_fixture(tmp_path: Path) -> None:
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    output = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=160x90:r=12:d=1",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert output.stat().st_size > 0
    subprocess.run(
        [executable, "-v", "error", "-i", str(output), "-f", "null", "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
