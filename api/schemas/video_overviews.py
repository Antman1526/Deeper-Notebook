"""Contracts for local, source-grounded Video Overview composition."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoOverviewComposeRequest(BaseModel):
    slide_deck_artifact_id: str = Field(min_length=1)
    podcast_episode_id: str = Field(min_length=1)
    caption_language: str = Field(
        default="en", pattern=r"^[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*$"
    )


class VideoOverviewResponse(BaseModel):
    artifact_id: str
    episode_id: str
    duration_seconds: float = Field(gt=0)
    media_url: str
    captions_url: str
