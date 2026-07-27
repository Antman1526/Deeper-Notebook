"""Typed inputs and receipts for source-grounded local video output."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoNarrationSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=8_000)
    citation_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def end_follows_start(self) -> "VideoNarrationSegment":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("caption end must follow its start")
        return self


class VideoOverviewDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    slide_image_paths: list[Path] = Field(min_length=1, max_length=60)
    narration_audio_path: Path
    narration_segments: list[VideoNarrationSegment] = Field(
        min_length=1, max_length=500
    )
    caption_language: str = Field(pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$")
    width: int = 1920
    height: int = 1080

    @model_validator(mode="after")
    def only_supported_resolution(self) -> "VideoOverviewDocument":
        if (self.width, self.height) != (1920, 1080):
            raise ValueError("Video Overviews must use 1920x1080 output")
        previous_end = 0.0
        for segment in self.narration_segments:
            if segment.start_seconds < previous_end:
                raise ValueError("caption segments must be monotonic")
            previous_end = segment.end_seconds
        if previous_end > 3_600:
            raise ValueError("Video Overviews may not exceed one hour")
        return self


class VideoOverviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mp4_path: Path
    vtt_path: Path
    duration_seconds: float = Field(gt=0)
