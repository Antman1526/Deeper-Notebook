"""v0.8.82 — keyless scholarly search (OpenAlex → arXiv).

No live network: ``httpx.AsyncClient`` is monkeypatched throughout.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from deeper_notebook.environment import SETTINGS as _SETTINGS
from deeper_notebook.tools import scholarly_search as ss


def _clear_setting(monkeypatch, canonical: str) -> None:
    """Delete a setting under every spelling the resolver accepts.

    Product env normalization mirrors a canonical name into its legacy aliases,
    and monkeypatch cannot undo writes it did not make — so a bare
    ``delenv(canonical)`` lets "disabled" leak into later test modules. The
    spellings come from the resolver's own registry rather than being written
    out here, so this stays correct if the alias scheme changes.
    """
    aliases = _SETTINGS.get(canonical)
    for name in (aliases.precedence if aliases else (canonical,)):
        monkeypatch.delenv(name, raising=False)

OPENALEX_PAYLOAD = {
    "results": [
        {
            "display_name": "Retrieval-Augmented Generation",
            "doi": "https://doi.org/10.1234/rag",
            "id": "https://openalex.org/W1",
            "publication_year": 2023,
            "cited_by_count": 702,
            # OpenAlex ships abstracts as an inverted index, not prose.
            "abstract_inverted_index": {"Large": [0], "language": [1], "models": [2]},
        },
        {
            "display_name": "Active RAG",
            "id": "https://openalex.org/W2",
            "publication_year": 2023,
            "cited_by_count": 416,
        },
    ]
}

ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2312.10997v5</id>
    <published>2023-12-18T00:00:00Z</published>
    <title>Retrieval-Augmented Generation
      for Large Language Models</title>
    <summary>A survey of RAG methods
      across many tasks.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2305.06983v2</id>
    <published>2023-05-11T00:00:00Z</published>
    <title>Active Retrieval</title>
    <summary>Another abstract.</summary>
  </entry>
</feed>
"""


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for canonical in (
        "DEEPER_NOTEBOOK_SCHOLARLY_SEARCH",
        "DEEPER_NOTEBOOK_SCHOLARLY_MAILTO",
    ):
        _clear_setting(monkeypatch, canonical)
    ss.reset_scholarly_cache()
    yield
    ss.reset_scholarly_cache()


@pytest.fixture(autouse=True)
def _online(monkeypatch):
    class _Net:
        status = "online"

    async def _state():
        return _Net()

    monkeypatch.setattr(
        "deeper_notebook.health.network.get_network_state_with_settings", _state
    )
    yield


def _fake_client(*, json_payload=None, text="", calls=None, fail_on=()):
    class _Resp:
        def __init__(self, url):
            self.text = text
            self._url = url

        def raise_for_status(self):
            return None

        def json(self):
            return json_payload or {}

    class _Client:
        def __init__(self, *a, **k):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

        async def get(self, url, **kw):
            if any(token in url for token in fail_on):
                raise RuntimeError("provider down")
            if calls is not None:
                calls.append((url, kw))
            return _Resp(url)

    return _Client


# ----------------------------------------------------------------- parsing


def test_openalex_prefers_doi_and_rebuilds_inverted_abstract():
    results = ss.parse_openalex(OPENALEX_PAYLOAD, 5)
    assert results[0]["url"] == "https://doi.org/10.1234/rag"
    assert "Large language models" in results[0]["snippet"]
    assert "2023" in results[0]["snippet"]
    assert "702 citations" in results[0]["snippet"]


def test_openalex_falls_back_to_record_id_without_doi():
    assert ss.parse_openalex(OPENALEX_PAYLOAD, 5)[1]["url"] == "https://openalex.org/W2"


def test_openalex_respects_limit_and_skips_untitled():
    payload = {"results": [{"id": "x"}, {"display_name": "Kept", "id": "y"}]}
    results = ss.parse_openalex(payload, 5)
    assert [r["title"] for r in results] == ["Kept"]


@pytest.mark.parametrize("payload", [None, {}, {"results": "nope"}, {"results": [1, 2]}])
def test_openalex_malformed_payload_degrades_to_empty(payload):
    assert ss.parse_openalex(payload, 5) == []


def test_arxiv_atom_parses_and_collapses_whitespace():
    results = ss.parse_arxiv_atom(ARXIV_ATOM, 5)
    assert len(results) == 2
    assert results[0]["title"] == (
        "Retrieval-Augmented Generation for Large Language Models"
    )
    assert results[0]["url"] == "http://arxiv.org/abs/2312.10997v5"
    assert results[0]["snippet"].startswith("2023-12-18")
    assert "survey of RAG methods across many tasks" in results[0]["snippet"]


def test_arxiv_respects_max_results():
    assert len(ss.parse_arxiv_atom(ARXIV_ATOM, 1)) == 1


@pytest.mark.parametrize("xml", ["", "not xml at all", "<feed></feed>", "<<<"])
def test_arxiv_malformed_feed_degrades_to_empty(xml):
    assert ss.parse_arxiv_atom(xml, 5) == []


# ---------------------------------------------------------------- end to end


def test_openalex_is_tried_first(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(json_payload=OPENALEX_PAYLOAD, calls=calls)
    )
    results = asyncio.run(ss.run_scholarly_search("rag"))
    assert calls[0][0] == ss._OPENALEX_ENDPOINT
    assert results[0]["title"] == "Retrieval-Augmented Generation"


def test_arxiv_is_the_failover_when_openalex_errors(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _fake_client(text=ARXIV_ATOM, calls=calls, fail_on=("openalex",)),
    )
    results = asyncio.run(ss.run_scholarly_search("rag"))
    assert calls and calls[0][0] == ss._ARXIV_ENDPOINT
    assert results[0]["url"] == "http://arxiv.org/abs/2312.10997v5"


def test_all_providers_failing_returns_empty(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(fail_on=("openalex", "arxiv"))
    )
    assert asyncio.run(ss.run_scholarly_search("rag")) == []


def test_mailto_is_sent_only_when_configured(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(json_payload=OPENALEX_PAYLOAD, calls=calls)
    )
    asyncio.run(ss.run_scholarly_search("rag"))
    assert "mailto" not in calls[0][1]["params"]

    ss.reset_scholarly_cache()
    calls.clear()
    monkeypatch.setenv("DEEPER_NOTEBOOK_SCHOLARLY_MAILTO", "me@example.com")
    asyncio.run(ss.run_scholarly_search("rag"))
    assert calls[0][1]["params"]["mailto"] == "me@example.com"


def test_offline_short_circuits(monkeypatch):
    class _Net:
        status = "offline"

    async def _state():
        return _Net()

    monkeypatch.setattr(
        "deeper_notebook.health.network.get_network_state_with_settings", _state
    )

    def _boom(*a, **k):
        raise AssertionError("network touched while offline")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    assert asyncio.run(ss.run_scholarly_search("rag")) == []


def test_kill_switch_disables_the_tool(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_SCHOLARLY_SEARCH", "0")
    assert ss.scholarly_search_enabled() is False
    assert asyncio.run(ss.run_scholarly_search("rag")) == []


def test_blank_query_never_hits_the_network(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("network touched for a blank query")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    assert asyncio.run(ss.run_scholarly_search("   ")) == []


def test_repeat_query_is_cached(monkeypatch):
    calls: list = []
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(json_payload=OPENALEX_PAYLOAD, calls=calls)
    )
    asyncio.run(ss.run_scholarly_search("rag"))
    asyncio.run(ss.run_scholarly_search("RAG"))
    assert len(calls) == 1


# ------------------------------------------------------------------- tool


def test_tool_metadata_steers_the_model_away_from_general_search():
    tool = ss.build_scholarly_search_tool()
    assert tool.name == "scholarly_search"
    assert "web_search" in tool.description, (
        "the description must tell the model when NOT to use this tool"
    )


def test_tool_records_a_citation_capture(monkeypatch):
    monkeypatch.setattr(
        httpx, "AsyncClient", _fake_client(json_payload=OPENALEX_PAYLOAD)
    )
    captures: list = []
    tool = ss.build_scholarly_search_tool(captures)
    text = asyncio.run(tool.coroutine(query="rag"))
    assert "Scholarly results" in text
    assert captures[0]["name"] == "scholarly_search"
    assert captures[0]["args"] == {"query": "rag"}


def test_empty_results_format_readably():
    assert ss.format_scholarly_results("x", []) == "No scholarly results found for 'x'."


def test_oversized_arxiv_feed_is_discarded_before_parsing():
    """v0.8.86 — Bandit B314 hardening: a multi-megabyte 'feed' is not a
    search result; it must be dropped before reaching the XML parser."""
    huge = "<feed>" + "x" * (ss._MAX_ARXIV_BYTES + 1) + "</feed>"
    assert ss.parse_arxiv_atom(huge, 5) == []
