"""v0.8.67r — Native tool to autonomously import web search results/URLs as notebook sources."""

from __future__ import annotations

from typing import Optional

from content_core import extract_content
from langchain_core.tools import StructuredTool
from loguru import logger
from pydantic import BaseModel, Field

from open_notebook.domain.content_settings import ContentSettings
from open_notebook.domain.notebook import Asset, Source


class AddWebSourceInput(BaseModel):
    url: str = Field(
        ...,
        description="The URL of the web search result/page to import into the notebook.",
    )
    title: Optional[str] = Field(None, description="Optional title for the new source.")


def build_add_web_source_tool(
    notebook_id: str, captures: list | None = None
) -> StructuredTool:
    """Build the StructuredTool for the chat model to bind and invoke."""

    async def _invoke(url: str, title: Optional[str] = None) -> str:
        try:
            logger.info(
                f"Autonomously importing web source: {url} to notebook {notebook_id}"
            )

            # Load content settings for URL processing engine preference
            try:
                content_settings = await ContentSettings.get_instance()
            except Exception as exc:
                logger.warning(
                    f"add_web_source: failed to load ContentSettings singleton ({exc}); using safe defaults"
                )
                content_settings = None

            url_engine = (
                getattr(content_settings, "default_content_processing_engine_url", None)
                or "auto"
            )
            document_engine = (
                getattr(content_settings, "default_content_processing_engine_doc", None)
                or "auto"
            )

            content_state = {
                "url": url,
                "url_engine": url_engine,
                "document_engine": document_engine,
                "output_format": "markdown",
            }

            # v0.8.67u — Integrated crawl4ai scraping with standard content_core fallback.
            from content_core.common.state import ProcessSourceOutput

            from open_notebook.utils.crawler import extract_url_with_crawl4ai

            processed_state = None
            if url_engine == "crawl4ai":
                content = await extract_url_with_crawl4ai(url)
                if content:
                    processed_state = ProcessSourceOutput(
                        title=title or "Imported Web Source (crawl4ai)",
                        content=content,
                        url=url,
                        source_type="url",
                        identified_type="text",
                    )

            if processed_state is None:
                # Source ingestion must cross the same fail-closed fetch boundary
                # as the interactive source graph. Do not delegate a raw URL to
                # content-core, whose fetcher has a different localhost policy.
                from open_notebook.graphs.source import _extract_checked_url

                processed_state = await _extract_checked_url(content_state)

            if not processed_state.content or not processed_state.content.strip():
                raise ValueError("Could not extract any text content from the URL.")

            final_title = title or processed_state.title or "Imported Web Source"
            extraction_provenance = {
                key: value
                for key, value in {
                    "content_source_type": getattr(
                        processed_state, "source_type", None
                    ),
                    "identified_type": getattr(
                        processed_state, "identified_type", None
                    ),
                    "extractor": "content_core",
                }.items()
                if value is not None
            }

            # Create the source record
            source = Source(
                title=final_title,
                topics=[],
                asset=Asset(url=url),
                full_text=processed_state.content,
                provenance={
                    "origin": "web_import",
                    "url": url,
                    "extraction": extraction_provenance,
                },
                source_type="web_import",
            )
            await source.save()

            # Link to the notebook
            await source.add_to_notebook(notebook_id)

            # Vectorize/embed the source
            await source.vectorize()

            result_message = f"Successfully imported and vectorized source {final_title!r} (ID: {source.id}) into the notebook."

            if captures is not None:
                captures.append(
                    {
                        "index": len(captures) + 1,
                        "name": "add_web_source_to_notebook",
                        "args": {"url": url, "title": title},
                        "text": result_message,
                        "blocks": [],
                    }
                )
            return result_message

        except Exception as e:
            err_msg = f"Failed to import web source: {e}"
            logger.error(err_msg)
            return err_msg

    return StructuredTool.from_function(
        coroutine=_invoke,
        name="add_web_source_to_notebook",
        description=(
            "Import/add a web page or web search result URL as a new source in the current notebook. "
            "This downloads the web page, extracts its content, embeds it for semantic search, and "
            "permanently attaches it to the notebook so that it can be used for future queries."
        ),
        args_schema=AddWebSourceInput,
    )
