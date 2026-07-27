from typing import ClassVar, List, Literal, Optional

from pydantic import Field

from deeper_notebook.domain.base import RecordModel


class ContentSettings(RecordModel):
    record_id: ClassVar[str] = "open_notebook:content_settings"
    default_content_processing_engine_doc: Optional[
        Literal["auto", "docling", "simple"]
    ] = Field("auto", description="Default Content Processing Engine for Documents")
    # v0.8.67u — Added "crawl4ai" as a supported local URL processing engine option.
    default_content_processing_engine_url: Optional[
        Literal["auto", "crawl4ai", "firecrawl", "jina", "simple"]
    ] = Field("auto", description="Default Content Processing Engine for URLs")
    default_embedding_option: Optional[Literal["ask", "always", "never"]] = Field(
        "ask", description="Default Embedding Option for Vector Search"
    )
    auto_delete_files: Optional[Literal["yes", "no"]] = Field(
        "yes", description="Auto Delete Uploaded Files"
    )
    youtube_preferred_languages: Optional[list[str]] = Field(
        ["en", "pt", "es", "de", "nl", "en-GB", "fr", "de", "hi", "ja"],
        description="Preferred languages for YouTube transcripts",
    )
    # v0.8.68 — user-forced offline mode. When true the app behaves as if
    # disconnected even when online: cloud chat falls back to the local
    # model, web search short-circuits, Gmail digests defer. Local-provider
    # models are never affected. Read via the network-state service.
    offline_mode: Optional[bool] = Field(
        False, description="Force offline: never use the internet"
    )
    # v0.8.88 — opt-in source auto-summary (improvement roadmap, Batch 4).
    # When True, adding a source also runs the built-in "Summary" transformation
    # on ingest (one extra LLM call per source), surfaced as a Summary insight +
    # a preview on the source card. Default OFF to respect local-LLM cost.
    auto_summarize_on_ingest: Optional[bool] = Field(
        False, description="Automatically summarize sources when they are added"
    )
    # v0.8.91 — opt-in source key-topics extraction (improvement roadmap, later
    # idea). When True, adding a source also runs the built-in "Key Topics"
    # transformation on ingest; the parsed topics populate the source's `topics`
    # field (the card's topic badges). Default OFF to respect local-LLM cost.
    auto_extract_topics_on_ingest: Optional[bool] = Field(
        False, description="Automatically extract key topics when sources are added"
    )
