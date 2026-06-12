"""v0.8.67u — Local crawling utility using crawl4ai.
"""
from __future__ import annotations

from typing import Optional
from loguru import logger

async def extract_url_with_crawl4ai(url: str) -> Optional[str]:
    """Scrapes a URL using a local crawl4ai instance.
    
    v0.8.67u — Dynamically loads crawl4ai to avoid dependency conflicts
    (such as lxml versions) and falls back gracefully to None if the library
    or its browser binaries are not installed or configured.
    """
    try:
        from crawl4ai import AsyncWebCrawler
        
        logger.info(f"Attempting local page extraction via crawl4ai: {url}")
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url, bypass_cache=True)
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
