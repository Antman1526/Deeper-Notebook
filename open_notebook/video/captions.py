"""Safe WebVTT rendering for local Video Overview transcripts."""

from __future__ import annotations

from .contracts import VideoNarrationSegment


def _timestamp(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def render_webvtt(segments: list[VideoNarrationSegment]) -> str:
    lines = ["WEBVTT", ""]
    for index, segment in enumerate(segments, start=1):
        # Plain text VTT: never pass model-controlled markup to a renderer.
        text = segment.text.replace("-->", "→").replace("\x00", "").strip()
        lines.extend([str(index), f"{_timestamp(segment.start_seconds)} --> {_timestamp(segment.end_seconds)}", text, ""])
    return "\n".join(lines)
