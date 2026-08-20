"""Deterministic PNG and PDF exports for infographic documents."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from deeper_notebook.identity import PRODUCT_NAME
from deeper_notebook.studio.exporters.theme import (
    BORDER,
    INK,
    MUTED,
    NAVY,
    PANEL_ACCENTS,
    PAPER,
    TEAL,
    WHITE,
    draw_fitted_text,
    load_font,
    safe_pdf_title,
    unique_markers,
)
from deeper_notebook.studio.schemas import InfographicDocument, InfographicPanel

INFOGRAPHIC_SIZES = {
    "portrait": (1200, 1800),
    "landscape": (1800, 1200),
    "square": (1400, 1400),
}


def _panel_grid(
    document: InfographicDocument,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    if document.orientation == "square" and len(document.panels) <= 3:
        columns = 1
        rows = len(document.panels)
        gap = 28
        return columns, rows, width - 120, (height - 370 - gap * (rows - 1)) // rows

    gap = 28
    best: tuple[tuple[float, int, int], tuple[int, int, int, int]] | None = None
    for columns in range(1, min(6, len(document.panels)) + 1):
        rows = math.ceil(len(document.panels) / columns)
        panel_width = (width - 120 - gap * (columns - 1)) // columns
        panel_height = (height - 370 - gap * (rows - 1)) // rows
        if panel_width < 1 or panel_height < 1:
            continue
        score = (
            min(panel_width / 300, panel_height / 220),
            panel_width * panel_height,
            -columns,
        )
        candidate = (columns, rows, panel_width, panel_height)
        if best is None or score > best[0]:
            best = (score, candidate)

    if best is None:
        raise ValueError(
            "Infographic panels cannot fit within the selected orientation"
        )
    return best[1]


def _draw_compact_panel(
    draw: ImageDraw.ImageDraw,
    panel: InfographicPanel,
    box: tuple[int, int, int, int],
    index: int,
) -> None:
    left, top, right, bottom = box
    accent = PANEL_ACCENTS[panel.kind]
    draw.rounded_rectangle(box, radius=6, fill=WHITE, outline=BORDER, width=2)
    draw.rectangle((left, top, right, top + 9), fill=accent)
    draw.text(
        (left + 16, top + 20),
        panel.kind.upper(),
        font=load_font(11, bold=True),
        fill=accent,
    )
    draw.text(
        (right - 34, top + 20),
        f"{index:02d}",
        font=load_font(11, bold=True),
        fill=MUTED,
    )
    draw_fitted_text(
        draw,
        (left + 16, top + 45),
        panel.heading,
        max_width=right - left - 32,
        max_height=48,
        max_size=22,
        min_size=14,
        fill=INK,
        bold=True,
        spacing=3,
        max_lines=2,
    )

    content_top = top + 100
    if panel.value:
        draw_fitted_text(
            draw,
            (left + 16, content_top),
            panel.value,
            max_width=right - left - 32,
            max_height=34,
            max_size=28,
            min_size=16,
            fill=accent,
            bold=True,
            spacing=2,
            max_lines=1,
        )
        content_top += 38

    body_height = bottom - content_top - 30
    if panel.body and body_height >= 16:
        draw_fitted_text(
            draw,
            (left + 16, content_top),
            panel.body,
            max_width=right - left - 32,
            max_height=body_height,
            max_size=16,
            min_size=11,
            fill=INK,
            spacing=3,
            max_lines=max(1, body_height // 15),
        )
    if panel.citations:
        draw_fitted_text(
            draw,
            (left + 16, bottom - 23),
            "Sources  " + " ".join(panel.citations),
            max_width=right - left - 32,
            max_height=14,
            max_size=11,
            min_size=9,
            fill=MUTED,
            spacing=1,
            max_lines=1,
        )


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    panel: InfographicPanel,
    box: tuple[int, int, int, int],
    index: int,
) -> None:
    left, top, right, bottom = box
    if bottom - top < 300 or right - left < 280:
        _draw_compact_panel(draw, panel, box, index)
        return

    accent = PANEL_ACCENTS[panel.kind]
    draw.rounded_rectangle(box, radius=8, fill=WHITE, outline=BORDER, width=2)
    draw.rounded_rectangle(
        (left, top, right, top + 14),
        radius=7,
        fill=accent,
    )
    draw.text(
        (left + 30, top + 34),
        panel.kind.upper(),
        font=load_font(16, bold=True),
        fill=accent,
    )
    draw_fitted_text(
        draw,
        (left + 30, top + 72),
        panel.heading,
        max_width=right - left - 60,
        max_height=86,
        max_size=34,
        min_size=23,
        fill=INK,
        bold=True,
        max_lines=2,
    )
    content_top = top + 170
    if panel.kind == "metric" and panel.value:
        draw_fitted_text(
            draw,
            (left + 30, content_top),
            panel.value,
            max_width=right - left - 60,
            max_height=105,
            max_size=72,
            min_size=42,
            fill=accent,
            bold=True,
            max_lines=1,
        )
        content_top += 112
    elif panel.value:
        draw_fitted_text(
            draw,
            (left + 30, content_top),
            panel.value,
            max_width=right - left - 60,
            max_height=70,
            max_size=32,
            min_size=22,
            fill=accent,
            bold=True,
            max_lines=2,
        )
        content_top += 82

    if panel.kind in {"timeline", "process"}:
        draw.line(
            (
                left + 45,
                content_top + 12,
                left + 45,
                min(bottom - 74, content_top + 115),
            ),
            fill=accent,
            width=5,
        )
        for offset in (14, 62, 110):
            draw.ellipse(
                (
                    left + 34,
                    content_top + offset - 10,
                    left + 56,
                    content_top + offset + 12,
                ),
                fill=accent,
            )
        body_left = left + 78
        body_width = right - body_left - 30
    else:
        body_left = left + 30
        body_width = right - left - 60

    if panel.body:
        draw_fitted_text(
            draw,
            (body_left, content_top),
            panel.body,
            max_width=body_width,
            max_height=max(70, bottom - content_top - 85),
            max_size=25,
            min_size=17,
            fill=INK,
            max_lines=8,
        )
    if panel.kind == "chart":
        baseline = bottom - 38
        bar_width = max(18, (right - left - 100) // 7)
        for bar_index, ratio in enumerate((0.45, 0.72, 0.58, 0.88)):
            bar_left = left + 35 + bar_index * (bar_width + 18)
            bar_height = int(80 * ratio)
            draw.rounded_rectangle(
                (bar_left, baseline - bar_height, bar_left + bar_width, baseline),
                radius=4,
                fill=accent,
            )
    if panel.citations:
        draw.text(
            (left + 30, bottom - 44),
            "Sources  " + " ".join(panel.citations),
            font=load_font(16),
            fill=MUTED,
        )
    draw.text(
        (right - 52, top + 34),
        f"{index:02d}",
        font=load_font(15, bold=True),
        fill=MUTED,
    )


def _render_infographic(document: InfographicDocument) -> Image.Image:
    width, height = INFOGRAPHIC_SIZES[document.orientation]
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 18), fill=TEAL)
    draw_fitted_text(
        draw,
        (60, 60),
        document.title,
        max_width=width - 120,
        max_height=130,
        max_size=54 if width <= 1400 else 62,
        min_size=34,
        fill=NAVY,
        bold=True,
        max_lines=2,
    )
    draw.text(
        (62, 212),
        "EVIDENCE STUDIO  /  SOURCE-GROUNDED VISUAL",
        font=load_font(16, bold=True),
        fill=MUTED,
    )

    columns, _, panel_width, panel_height = _panel_grid(document, width, height)
    gap = 28
    start_y = 280
    for index, panel in enumerate(document.panels, start=1):
        row = (index - 1) // columns
        column = (index - 1) % columns
        left = 60 + column * (panel_width + gap)
        top = start_y + row * (panel_height + gap)
        _draw_panel(
            draw,
            panel,
            (left, top, left + panel_width, min(height - 90, top + panel_height)),
            index,
        )

    markers = unique_markers([panel.citations for panel in document.panels])
    footer = "Sources  " + " ".join(markers) if markers else PRODUCT_NAME
    draw.text((60, height - 54), footer, font=load_font(16), fill=MUTED)
    return image


def export_infographic(
    document: InfographicDocument,
    png_path: Path,
    pdf_path: Path,
) -> None:
    if not isinstance(document, InfographicDocument):
        raise TypeError("export_infographic requires InfographicDocument")
    image = _render_infographic(document)
    image.save(png_path, "PNG", optimize=True)
    image.save(
        pdf_path,
        "PDF",
        resolution=144.0,
        title=safe_pdf_title(document.title),
        author=PRODUCT_NAME,
        creator=PRODUCT_NAME,
        producer=PRODUCT_NAME,
        subject="Evidence Studio infographic",
    )
    image.close()


__all__ = ["INFOGRAPHIC_SIZES", "export_infographic"]
