#!/usr/bin/env python3
"""Create the bounded, deterministic media fixtures used by Task 4 tests.

The script deliberately owns exactly three paths.  It is safe to rerun after a
fixture directory has been removed, but it refuses to operate when an
unexpected file is present so that a test fixture cannot silently overwrite
user data.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

import fitz
import imageio_ffmpeg
from PIL import Image, ImageDraw

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "source_visuals"
FIXTURE_PATHS = (
    FIXTURE_ROOT / "fixture.pdf",
    FIXTURE_ROOT / "fixture.mp4",
    FIXTURE_ROOT / "fixture-artwork.m4a",
)
MAX_FIXTURE_BYTES = 2 * 1024 * 1024


def _run_ffmpeg(*args: str) -> None:
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [executable, "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _image_bytes(*, width: int, height: int, background: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    # Fixed geometry and colors give the scoring tests a useful, non-uniform
    # image without embedding timestamps or machine-specific metadata.
    draw.rectangle((width // 8, height // 8, width * 7 // 8, height * 7 // 8), fill=(20, 70, 130))
    draw.line((0, 0, width - 1, height - 1), fill=(240, 210, 60), width=max(1, width // 80))
    draw.line((width - 1, 0, 0, height - 1), fill=(60, 210, 160), width=max(1, width // 80))
    from io import BytesIO

    stream = BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _write_pdf(path: Path) -> None:
    document = fitz.open()
    document.set_metadata(
        {
            "format": "PDF 1.7",
            "title": "Source visual fixture",
            "author": "Deeper Notebook",
            "subject": "Deterministic local visual extraction fixture",
            "keywords": "source-visual-v1",
            "creator": "source-visual-fixtures",
            "producer": "source-visual-fixtures",
            "creationDate": "D:20200102030405Z",
            "modDate": "D:20200102030405Z",
        }
    )
    images = (
        _image_bytes(width=320, height=180, background=(25, 45, 80)),
        _image_bytes(width=640, height=360, background=(35, 55, 90)),
        _image_bytes(width=640, height=360, background=(35, 55, 90)),
    )
    for index, image in enumerate(images, start=1):
        page = document.new_page(width=640, height=360)
        page.insert_image(fitz.Rect(0, 0, 640, 360), stream=image)
        page.insert_text(
            fitz.Point(24, 340),
            f"Fixture page {index}",
            fontsize=12,
            color=(0.9, 0.9, 0.9),
        )
    document.save(path, garbage=4, clean=True, deflate=True)
    document.close()
    payload = path.read_bytes()
    payload, replacements = re.subn(
        rb"/ID\[<[^>]+><[^>]+>\]",
        b"/ID[<0123456789abcdef0123456789abcdef><fedcba9876543210fedcba9876543210>]",
        payload,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError("PDF trailer ID was not found")
    path.write_bytes(payload)


def _write_video(path: Path) -> None:
    # A fixed-color source with fixed-duration geometric overlays avoids a
    # dependency on system codecs while giving frame extraction three stable
    # non-uniform samples.
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=c=0x183050:s=320x180:r=12:d=4",
        "-vf",
        "drawbox=x=32+40*t:y=36:w=96:h=72:color=0x2ad4a8:t=fill,drawbox=x=220-30*t:y=80:w=48:h=48:color=0xf0d23c:t=fill",
        "-t",
        "4",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-metadata",
        "creation_time=2020-01-02T03:04:05Z",
        str(path),
    )


def _write_audio_artwork(path: Path) -> None:
    _run_ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x321e50:s=480x270:r=1",
        "-map",
        "0:a:0",
        "-map",
        "1:v:0",
        "-t",
        "1",
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        "-c:v",
        "mjpeg",
        "-disposition:v:0",
        "attached_pic",
        "-metadata:s:v:0",
        "title=Cover",
        "-metadata:s:v:0",
        "comment=Cover (front)",
        "-metadata",
        "creation_time=2020-01-02T03:04:05Z",
        str(path),
    )


def _assert_fixture(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"fixture was not created: {path.name}")
    size = path.stat().st_size
    if size <= 0 or size > MAX_FIXTURE_BYTES:
        raise RuntimeError(f"fixture size outside bound: {path.name} ({size})")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(digest) != 64:
        raise RuntimeError(f"fixture hash failed: {path.name}")


def create_fixtures() -> None:
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    allowed = {path.name for path in FIXTURE_PATHS}
    unexpected = sorted(path.name for path in FIXTURE_ROOT.iterdir() if path.name not in allowed)
    if unexpected:
        raise RuntimeError("unexpected files in source visual fixture directory: " + ", ".join(unexpected))
    existing = [path for path in FIXTURE_PATHS if path.exists()]
    if existing:
        raise RuntimeError("fixture paths already exist; remove only the exact fixture files before regenerating")

    _write_pdf(FIXTURE_PATHS[0])
    _write_video(FIXTURE_PATHS[1])
    _write_audio_artwork(FIXTURE_PATHS[2])
    for path in FIXTURE_PATHS:
        _assert_fixture(path)


def main() -> int:
    try:
        create_fixtures()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"fixture generation failed: {exc}", file=sys.stderr)
        return 1
    for path in FIXTURE_PATHS:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{path.relative_to(FIXTURE_ROOT.parent.parent.parent)} {path.stat().st_size} {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
