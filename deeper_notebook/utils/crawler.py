"""v0.8.67u — Local crawling utility using crawl4ai."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from deeper_notebook.research.safe_fetch import SafeFetchResponse
from deeper_notebook.security.outbound_url import validate_outbound_url


async def extract_url_with_crawl4ai(
    url: str, *, prefetched: SafeFetchResponse | None = None
) -> Optional[str]:
    """Scrapes a URL using a local crawl4ai instance.

    v0.8.67u — Dynamically loads crawl4ai to avoid dependency conflicts
    (such as lxml versions) and falls back gracefully to None if the library
    or its browser binaries are not installed or configured.
    """
    # Normal source ingestion provides a prefetched response. Rendering that
    # locally keeps Crawl4AI/Playwright from issuing unobservable subrequests.
    if prefetched is not None:
        if prefetched.content_type.startswith("text/"):
            return prefetched.text
        logger.warning("crawl4ai cannot render a non-text checked response")
        return None

    try:
        # Keep the legacy utility guarded for callers outside the source graph.
        # The source graph uses the prefetched branch above, which is stricter.
        checked_url = await validate_outbound_url(url)
        from crawl4ai import AsyncWebCrawler

        logger.info(f"Attempting local page extraction via crawl4ai: {checked_url.url}")
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=checked_url.url, bypass_cache=True)
            if hasattr(result, "success") and result.success:
                return result.markdown

            error_msg = getattr(result, "error_message", "Unknown error")
            logger.warning(f"crawl4ai failed to scrape URL {url}: {error_msg}")
            return None

    except ImportError:
        logger.warning(
            "crawl4ai package is not available. Local JS-rendering crawler will "
            "be disabled. Install via `pip install crawl4ai` to enable."
        )
        return None
    except Exception as e:
        logger.warning(
            f"crawl4ai failed during extraction for URL {url}: {e}. "
            "Make sure you ran `playwright install` or `crawl4ai-setup`."
        )
        return None
