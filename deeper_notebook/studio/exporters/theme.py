"""Shared deterministic visual theme and Pillow text helpers."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import ImageDraw, ImageFont

INK = "#17202A"
MUTED = "#667085"
PAPER = "#F7F8FA"
WHITE = "#FFFFFF"
NAVY = "#17324D"
TEAL = "#168C84"
CORAL = "#E76F51"
GOLD = "#D6A53A"
SKY = "#4F86C6"
BORDER = "#D8DEE8"

PANEL_ACCENTS = {
    "text": NAVY,
    "metric": TEAL,
    "timeline": CORAL,
    "comparison": SKY,
    "process": GOLD,
    "chart": TEAL,
}

_FONT_CANDIDATES = (
    "Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
)

_BOLD_FONT_CANDIDATES = (
    "Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
)


def load_font(
    size: int, *, bold: bool = False
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = _BOLD_FONT_CANDIDATES if bold else _FONT_CANDIDATES
    for candidate in candidates:
        try:
            if "/" in candidate or ":" in candidate:
                if not Path(candidate).exists():
                    continue
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    paragraphs = text.replace("\r\n", "\n").split("\n")
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    max_width: int,
    max_height: int,
    max_size: int,
    min_size: int,
    fill: str = INK,
    bold: bool = False,
    spacing: int = 8,
    max_lines: int | None = None,
) -> tuple[int, int]:
    x, y = xy
    selected_font = load_font(min_size, bold=bold)
    selected_lines = wrap_text(draw, text, selected_font, max_width)
    for size in range(max_size, min_size - 1, -2):
        font = load_font(size, bold=bold)
        lines = wrap_text(draw, text, font, max_width)
        if max_lines is not None and len(lines) > max_lines:
            continue
        bbox = draw.multiline_textbbox(
            (0, 0), "\n".join(lines), font=font, spacing=spacing
        )
        if bbox[3] - bbox[1] <= max_height:
            selected_font = font
            selected_lines = lines
            break

    if max_lines is not None and len(selected_lines) > max_lines:
        selected_lines = selected_lines[:max_lines]
        last = selected_lines[-1].rstrip()
        while last and draw.textlength(f"{last}...", font=selected_font) > max_width:
            last = last[:-1].rstrip()
        selected_lines[-1] = f"{last}..." if last else "..."

    rendered = "\n".join(selected_lines)
    draw.multiline_text(
        (x, y),
        rendered,
        font=selected_font,
        fill=fill,
        spacing=spacing,
    )
    bbox = draw.multiline_textbbox(
        (x, y), rendered, font=selected_font, spacing=spacing
    )
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def unique_markers(groups: list[list[str]]) -> list[str]:
    markers: list[str] = []
    for group in groups:
        for marker in group:
            if marker not in markers:
                markers.append(marker)
    return markers


def safe_pdf_title(value: str) -> str:
    return re.sub(r"[\x00-\x1f]+", " ", value).strip()[:240]
