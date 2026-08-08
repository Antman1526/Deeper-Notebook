"""Guarded source discovery and ingestion handlers for Research Runs.

Discovery is deliberately separate from ingestion.  A search result is only a
candidate: no URL is fetched until the notebook owner submits its candidate id
to the approval endpoint.  Both approval and ingestion cross the outbound URL
policy, so search-provider output never becomes a bypass around normal source
ingestion safeguards.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from loguru import logger

from deeper_notebook.domain.content_settings import ContentSettings
from deeper_notebook.domain.notebook import Asset, Source
from deeper_notebook.graphs.source import _extract_checked_url
from deeper_notebook.research.state import (
    ResearchCandidate,
    ResearchRun,
    ResearchStageResult,
)
from deeper_notebook.security.outbound_url import (
    OutboundURLPolicyError,
    normalize_outbound_url,
)
from deeper_notebook.tools.web_evidence import WebEvidence
from deeper_notebook.tools.web_search import (
    run_web_search_with_evidence,
    web_search_enabled,
)

MAX_DISCOVERY_RESULTS = 20


def candidate_domain(url: str) -> str:
    """Return the display-only canonical host already stored in a candidate."""
    return urlsplit(url).hostname or ""


def candidate_id_for_url(url: str) -> str:
    """Use a stable id so retries and duplicate provider entries remain harmless."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return f"candidate:{digest}"


def normalize_candidates(
    results: Iterable[WebEvidence | Mapping[object, object]],
) -> list[ResearchCandidate]:
    """Canonicalize provider output without fetching any candidate URL.

    Invalid, credential-bearing, and non-HTTP(S) values are discarded here.
    DNS/public-address validation deliberately happens again during approval and
    in the fetcher immediately before connection, when it can resist rebinding.
    """
    candidates: list[ResearchCandidate] = []
    seen_urls: set[str] = set()
    for result in results:
        if isinstance(result, WebEvidence):
            raw_url = result.url
            title = result.title
            snippet = result.snippet
            evidence = result
        elif isinstance(result, Mapping):
            try:
                raw_url = result.get("url")
                title = result.get("title")
                snippet = result.get("snippet")
            except Exception:
                continue
            evidence = None
        else:
            continue
        if not isinstance(raw_url, str):
            continue
        try:
            url = normalize_outbound_url(raw_url)
        except OutboundURLPolicyError:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        # WebEvidence fingerprints bind its canonical URL. If outbound policy
        # canonicalizes the URL further (for example, adding a root slash),
        # drop the receipt rather than attaching hashes for a different URL.
        candidate_evidence = (
            evidence if evidence is None or evidence.url == url else None
        )
        candidates.append(
            ResearchCandidate(
                candidate_id=candidate_id_for_url(url),
                url=url,
                title=title.strip()
                if isinstance(title, str) and title.strip()
                else None,
                summary=(
                    snippet.strip()
                    if isinstance(snippet, str) and snippet.strip()
                    else None
                ),
                evidence=candidate_evidence,
            )
        )
        if len(candidates) >= MAX_DISCOVERY_RESULTS:
            break
    return candidates


async def discover_sources(run: ResearchRun) -> ResearchStageResult:
    """Search the existing provider chain and checkpoint candidates only."""
    query = next((item.strip() for item in run.search_queries if item.strip()), "")
    if not query or not web_search_enabled():
        return ResearchStageResult(checkpoint={"query": query, "candidate_count": 0})
    try:
        results = await run_web_search_with_evidence(
            query, max_results=MAX_DISCOVERY_RESULTS
        )
    except Exception as exc:
        # Discovery is best effort. Do not turn a provider outage into an
        # ingestion attempt or expose provider details to API callers.
        logger.warning("Research discovery failed: {}", exc)
        results = []
    candidates = normalize_candidates(results)
    return ResearchStageResult(
        checkpoint={"query": query, "candidate_count": len(candidates)},
        candidates=candidates,
    )


async def ingest_approved_sources(run: ResearchRun) -> ResearchStageResult:
    """Import only explicitly approved candidates through checked URL extraction."""
    if not run.notebook_id:
        return ResearchStageResult(errors=["Research run is missing its notebook"])

    try:
        settings = await ContentSettings.get_instance()
    except Exception as exc:
        logger.warning("Research ingestion settings unavailable: {}", exc)
        settings = None

    source_ids: list[str] = []
    errors: list[str] = []
    for candidate in run.candidates:
        if candidate.candidate_id not in run.approved_candidate_ids():
            continue
        try:
            # _extract_checked_url performs the same safe fetch used by the
            # regular source graph; never pass a raw remote URL to content-core.
            processed = await _extract_checked_url(
                {
                    "url": candidate.url,
                    "title": candidate.title,
                    "url_engine": getattr(
                        settings, "default_content_processing_engine_url", "auto"
                    ),
                    "document_engine": getattr(
                        settings, "default_content_processing_engine_doc", "auto"
                    ),
                    "output_format": "markdown",
                }
            )
            content = (getattr(processed, "content", None) or "").strip()
            if not content:
                raise ValueError("checked source did not contain importable text")
            source = Source(
                title=candidate.title
                or getattr(processed, "title", None)
                or "Web source",
                topics=[],
                asset=Asset(url=getattr(processed, "url", None) or candidate.url),
                full_text=content,
                provenance={
                    "origin": "research_run",
                    "research_candidate_id": candidate.candidate_id,
                    "url": candidate.url,
                },
                source_type="web_import",
            )
            await source.save()
            await source.add_to_notebook(run.notebook_id)
            await source.vectorize()
            source_ids.append(str(source.id))
        except Exception as exc:
            logger.warning(
                "Research source import failed for {}: {}", candidate.url, exc
            )
            # Keep the public record useful without leaking transport or parser
            # details that may include an upstream URL/query fragment.
            errors.append(f"Could not import approved source {candidate.candidate_id}")
    return ResearchStageResult(
        checkpoint={
            "approved_candidate_ids": sorted(run.approved_candidate_ids()),
            "imported_source_count": len(source_ids),
        },
        source_ids=source_ids,
        errors=errors,
    )
