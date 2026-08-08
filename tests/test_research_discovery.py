"""Research discovery keeps immutable web evidence separate from approval."""

from __future__ import annotations

from deeper_notebook.research.discovery import normalize_candidates
from deeper_notebook.research.state import ResearchRun
from deeper_notebook.tools.web_evidence import normalize_web_results


def test_research_candidate_keeps_optional_evidence() -> None:
    evidence = normalize_web_results(
        [
            {
                "title": "T",
                "url": "https://example.com/source",
                "snippet": "S",
            }
        ],
        query="q",
        provider="tavily",
    )[0]

    candidate = normalize_candidates([evidence])[0]
    assert candidate.evidence == evidence

    round_tripped = ResearchRun.model_validate(
        ResearchRun(objective="q", candidates=[candidate]).model_dump()
    )
    assert round_tripped.candidates[0].evidence == evidence


def test_discovery_rejects_invalid_evidence_urls_without_dropping_valid_entries() -> None:
    valid = normalize_web_results(
        [{"title": "Valid", "url": "https://example.com/source", "snippet": "S"}],
        query="q",
        provider="tavily",
    )[0]
    invalid = valid.model_copy(update={"url": "file:///etc/passwd"})

    candidates = normalize_candidates([invalid, valid])

    assert len(candidates) == 1
    assert candidates[0].url == "https://example.com/source"
    assert candidates[0].evidence == valid


def test_discovery_drops_evidence_when_outbound_url_is_canonicalized() -> None:
    evidence = normalize_web_results(
        [{"title": "Root", "url": "https://example.com", "snippet": "S"}],
        query="q",
        provider="tavily",
    )[0]

    candidates = normalize_candidates([evidence])

    assert candidates[0].url == "https://example.com/"
    assert candidates[0].evidence is None
