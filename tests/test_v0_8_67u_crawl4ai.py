"""v0.8.67u — Unit tests for crawl4ai local scraper and integration fallback logic.
"""
from __future__ import annotations

import sys
import types

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from open_notebook.utils.crawler import extract_url_with_crawl4ai
from open_notebook.tools.add_web_source import build_add_web_source_tool
from open_notebook.graphs import source as source_graph
from open_notebook.domain.content_settings import ContentSettings


# v0.8.68 — crawl4ai is an OPTIONAL heavy dependency (pulls Playwright);
# most dev environments don't have it installed, and `patch("crawl4ai.
# AsyncWebCrawler", ...)` imports the module first — so these tests failed
# with ModuleNotFoundError on any machine without the extra. Register a
# stub module when the real one is absent: the production code's dynamic
# `from crawl4ai import AsyncWebCrawler` resolves against sys.modules, and
# the patch() targets work identically. monkeypatch.setitem auto-restores.
@pytest.fixture(autouse=True)
def _stub_crawl4ai_module(monkeypatch):
    if "crawl4ai" not in sys.modules:
        try:
            import crawl4ai  # noqa: F401 — real package present, use it
        except ImportError:
            stub = types.ModuleType("crawl4ai")
            stub.AsyncWebCrawler = MagicMock(name="AsyncWebCrawler-stub")
            monkeypatch.setitem(sys.modules, "crawl4ai", stub)
    yield


# ------------------------------------------------------------- crawl4ai wrapper tests

@pytest.mark.asyncio
async def test_extract_url_with_crawl4ai_success(monkeypatch):
    # Mock AsyncWebCrawler
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.markdown = "Parsed Markdown Content"
    
    mock_crawler_instance = AsyncMock()
    mock_crawler_instance.__aenter__.return_value.arun.return_value = mock_result
    
    mock_crawler_class = MagicMock(return_value=mock_crawler_instance)
    
    # We must patch the import of AsyncWebCrawler inside crawler.py
    with patch("crawl4ai.AsyncWebCrawler", mock_crawler_class):
        content = await extract_url_with_crawl4ai("https://example.com/test")
        assert content == "Parsed Markdown Content"

@pytest.mark.asyncio
async def test_extract_url_with_crawl4ai_failure(monkeypatch):
    # Mock AsyncWebCrawler returning success=False
    mock_result = MagicMock()
    mock_result.success = False
    mock_result.error_message = "DDoS Blocked"
    
    mock_crawler_instance = AsyncMock()
    mock_crawler_instance.__aenter__.return_value.arun.return_value = mock_result
    
    mock_crawler_class = MagicMock(return_value=mock_crawler_instance)
    
    with patch("crawl4ai.AsyncWebCrawler", mock_crawler_class):
        content = await extract_url_with_crawl4ai("https://example.com/test")
        assert content is None

@pytest.mark.asyncio
async def test_extract_url_with_crawl4ai_import_error(monkeypatch):
    # Mock ImportError
    with patch("crawl4ai.AsyncWebCrawler", side_effect=ImportError("No module named crawl4ai")):
        content = await extract_url_with_crawl4ai("https://example.com/test")
        assert content is None

# ------------------------------------------------------------- tool integration tests

@pytest.mark.asyncio
async def test_add_web_source_tool_uses_crawl4ai(monkeypatch):
    # Mock ContentSettings
    settings = ContentSettings(
        default_content_processing_engine_url="crawl4ai"
    )
    monkeypatch.setattr(ContentSettings, "get_instance", AsyncMock(return_value=settings))
    
    # Mock extract_url_with_crawl4ai
    mock_extract = AsyncMock(return_value="Scraped by Crawl4AI")
    monkeypatch.setattr("open_notebook.utils.crawler.extract_url_with_crawl4ai", mock_extract)
    
    # Mock Source saving
    mock_source = MagicMock()
    mock_source.id = "src:999"
    mock_source.save = AsyncMock()
    mock_source.add_to_notebook = AsyncMock()
    mock_source.vectorize = AsyncMock()
    monkeypatch.setattr("open_notebook.tools.add_web_source.Source", MagicMock(return_value=mock_source))
    
    tool = build_add_web_source_tool("notebook:111")
    res = await tool.coroutine(url="https://test.crawl", title="Crawl Test")
    
    assert "Successfully imported" in res
    assert "Crawl Test" in res
    mock_extract.assert_called_once_with("https://test.crawl")

@pytest.mark.asyncio
async def test_add_web_source_tool_falls_back_on_failure(monkeypatch):
    settings = ContentSettings(
        default_content_processing_engine_url="crawl4ai"
    )
    monkeypatch.setattr(ContentSettings, "get_instance", AsyncMock(return_value=settings))
    
    # Mock extract_url_with_crawl4ai to fail
    monkeypatch.setattr("open_notebook.utils.crawler.extract_url_with_crawl4ai", AsyncMock(return_value=None))
    
    # Mock content_core extract_content fallback
    mock_fallback_res = MagicMock()
    mock_fallback_res.content = "Simple Scraped Content"
    mock_fallback_res.title = "Fallback Title"
    monkeypatch.setattr("open_notebook.tools.add_web_source.extract_content", AsyncMock(return_value=mock_fallback_res))
    
    mock_source = MagicMock()
    mock_source.id = "src:999"
    mock_source.save = AsyncMock()
    mock_source.add_to_notebook = AsyncMock()
    mock_source.vectorize = AsyncMock()
    monkeypatch.setattr("open_notebook.tools.add_web_source.Source", MagicMock(return_value=mock_source))
    
    tool = build_add_web_source_tool("notebook:111")
    res = await tool.coroutine(url="https://test.crawl", title="Crawl Test")
    
    assert "Successfully imported" in res
    assert "Crawl Test" in res

# ------------------------------------------------------------- graph node tests

@pytest.mark.asyncio
async def test_source_graph_node_uses_crawl4ai(monkeypatch):
    settings = ContentSettings(
        default_content_processing_engine_url="crawl4ai"
    )
    monkeypatch.setattr(ContentSettings, "get_instance", AsyncMock(return_value=settings))
    
    # Mock extract_url_with_crawl4ai
    mock_extract = AsyncMock(return_value="Scraped inside graph")
    monkeypatch.setattr("open_notebook.utils.crawler.extract_url_with_crawl4ai", mock_extract)
    
    state = {
        "content_state": {"url": "https://test.graph.url"},
        "source_id": "src:123",
        "notebook_id": "nb:456"
    }
    
    res = await source_graph.content_process(state)
    assert res["content_state"].content == "Scraped inside graph"
    mock_extract.assert_called_once_with("https://test.graph.url")
