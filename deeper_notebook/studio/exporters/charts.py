"""Trusted SVG chart rendering from bounded, typed Studio chart data."""

from __future__ import annotations

import html
import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ChartKind = Literal["bar", "line", "scatter"]

_MAX_SERIES = 12
_MAX_POINTS = 500
_FORBIDDEN_TEXT = re.compile(
    r"(?:<\s*/?\s*(?:script|foreignobject)\b|\bon\w+\s*=|\b(?:https?|data|javascript)\s*:)",
    re.IGNORECASE,
)
_COLORS = (
    "#0F766E",
    "#2563EB",
    "#BE123C",
    "#7C3AED",
    "#B45309",
    "#047857",
    "#4F46E5",
    "#9F1239",
    "#0369A1",
    "#A16207",
    "#6D28D9",
    "#166534",
)


def _safe_text(value: str, *, field_name: str) -> str:
    if _FORBIDDEN_TEXT.search(value):
        raise ValueError(f"{field_name} contains forbidden SVG content")
    return value


class ChartPoint(BaseModel):
    """One bounded numeric data point; labels are escaped before SVG output."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=-1_000_000_000, le=1_000_000_000)
    y: float = Field(ge=-1_000_000_000, le=1_000_000_000)
    label: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_finite_values(self) -> "ChartPoint":
        if not math.isfinite(self.x) or not math.isfinite(self.y):
            raise ValueError("chart points must be finite")
        if self.label is not None:
            _safe_text(self.label, field_name="point label")
        return self


class ChartSeries(BaseModel):
    """One named data series. Colors are selected internally, never supplied."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    points: list[ChartPoint] = Field(min_length=1, max_length=_MAX_POINTS)

    @model_validator(mode="after")
    def validate_name(self) -> "ChartSeries":
        _safe_text(self.name, field_name="series name")
        return self


class ChartDocument(BaseModel):
    """The only accepted chart schema for SVG exports."""

    model_config = ConfigDict(extra="forbid")

    chart_type: ChartKind
    title: str = Field(min_length=1, max_length=200)
    x_label: str = Field(default="", max_length=120)
    y_label: str = Field(default="", max_length=120)
    series: list[ChartSeries] = Field(min_length=1, max_length=_MAX_SERIES)

    @model_validator(mode="after")
    def validate_document(self) -> "ChartDocument":
        for value, field_name in (
            (self.title, "chart title"),
            (self.x_label, "x label"),
            (self.y_label, "y label"),
        ):
            _safe_text(value, field_name=field_name)
        if sum(len(series.points) for series in self.series) > _MAX_POINTS:
            raise ValueError(f"charts may contain at most {_MAX_POINTS} total points")
        return self


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _scale(
    value: float,
    source_min: float,
    source_max: float,
    target_min: float,
    target_max: float,
) -> float:
    if source_max == source_min:
        return (target_min + target_max) / 2
    return target_min + ((value - source_min) / (source_max - source_min)) * (
        target_max - target_min
    )


def render_svg_chart(document: ChartDocument) -> str:
    """Render a chart using only fixed SVG primitives and escaped text.

    Input cannot select element names, attributes, colors, URLs, or raw XML.
    This is deliberately a small renderer instead of a general SVG templater.
    """
    if not isinstance(document, ChartDocument):
        raise TypeError("render_svg_chart requires ChartDocument")

    width, height = 960, 560
    left, top, right, bottom = 80, 66, 42, 78
    plot_width, plot_height = width - left - right, height - top - bottom
    points = [point for series in document.series for point in series.points]
    x_values = [point.x for point in points]
    y_values = [point.y for point in points]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    if document.chart_type == "bar":
        y_min = min(0.0, y_min)
        y_max = max(0.0, y_max)

    def x_coord(value: float) -> float:
        return _scale(value, x_min, x_max, left, left + plot_width)

    def y_coord(value: float) -> float:
        return _scale(value, y_min, y_max, top + plot_height, top)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="chart-title chart-description">',
        f'  <title id="chart-title">{_escape(document.title)}</title>',
        f'  <desc id="chart-description">{_escape(document.chart_type)} chart with {len(document.series)} series.</desc>',
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#FFFFFF"/>',
        f'  <text x="{left}" y="34" fill="#111827" font-family="Arial, sans-serif" font-size="22" font-weight="700">{_escape(document.title)}</text>',
    ]
    for index in range(5):
        y = top + (plot_height / 4) * index
        value = _scale(y, top + plot_height, top, y_min, y_max)
        lines.extend(
            (
                f'  <line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" stroke="#D1D5DB" stroke-width="1"/>',
                f'  <text x="{left - 10}" y="{y + 4:.2f}" fill="#4B5563" font-family="Arial, sans-serif" font-size="11" text-anchor="end">{value:.2g}</text>',
            )
        )
    lines.extend(
        (
            f'  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#374151" stroke-width="1.5"/>',
            f'  <line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#374151" stroke-width="1.5"/>',
            f'  <text x="{left + plot_width / 2:.2f}" y="{height - 26}" fill="#374151" font-family="Arial, sans-serif" font-size="13" text-anchor="middle">{_escape(document.x_label)}</text>',
            f'  <text x="22" y="{top + plot_height / 2:.2f}" fill="#374151" font-family="Arial, sans-serif" font-size="13" text-anchor="middle" transform="rotate(-90 22 {top + plot_height / 2:.2f})">{_escape(document.y_label)}</text>',
        )
    )
    if document.chart_type == "bar":
        group_width = plot_width / max(len(x_values), 1)
        bar_width = max(2.0, group_width / (len(document.series) + 1))
        zero_y = y_coord(0.0)
        for series_index, series in enumerate(document.series):
            color = _COLORS[series_index]
            for point_index, point in enumerate(series.points):
                x = left + point_index * group_width + (series_index + 0.5) * bar_width
                y = y_coord(point.y)
                lines.append(
                    f'  <rect x="{x:.2f}" y="{min(y, zero_y):.2f}" width="{bar_width:.2f}" height="{abs(zero_y - y):.2f}" fill="{color}"/>'
                )
    else:
        for series_index, series in enumerate(document.series):
            color = _COLORS[series_index]
            coordinates = " ".join(
                f"{x_coord(point.x):.2f},{y_coord(point.y):.2f}"
                for point in series.points
            )
            if document.chart_type == "line":
                lines.append(
                    f'  <polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
                )
            for point in series.points:
                lines.append(
                    f'  <circle cx="{x_coord(point.x):.2f}" cy="{y_coord(point.y):.2f}" r="4" fill="{color}"/>'
                )
    for index, series in enumerate(document.series):
        x = left + index * 145
        color = _COLORS[index]
        lines.extend(
            (
                f'  <rect x="{x}" y="{height - 54}" width="12" height="12" fill="{color}"/>',
                f'  <text x="{x + 18}" y="{height - 43}" fill="#374151" font-family="Arial, sans-serif" font-size="12">{_escape(series.name)}</text>',
            )
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


__all__ = ["ChartDocument", "ChartPoint", "ChartSeries", "render_svg_chart"]
