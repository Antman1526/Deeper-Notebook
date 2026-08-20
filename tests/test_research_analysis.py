"""Evidence-only completion coverage for Research Runs."""

from types import SimpleNamespace

import pytest

from deeper_notebook.research import analysis
from deeper_notebook.research.state import ResearchRun


@pytest.mark.asyncio
async def test_research_analysis_uses_only_saved_sources_and_strict_receipts(
    monkeypatch,
) -> None:
    sources = {
        "source:one": SimpleNamespace(
            id="source:one", full_text="The archive retains audit receipts."
        ),
        "source:two": SimpleNamespace(
            id="source:two", full_text="The archive retains audit receipts."
        ),
    }

    async def source_get(source_id: str):
        return sources[source_id]

    monkeypatch.setattr(analysis.Source, "get", source_get)
    run = ResearchRun(
        id="research_run:one",
        objective="Check archive evidence",
        stage="extract",
        source_ids=["source:one", "source:two"],
    )

    extracted = await analysis.extract_research_evidence(run)
    compared = await analysis.compare_research_evidence(run)
    run = run.with_stage_result("extract", extracted).with_stage_result(
        "compare", compared
    )
    synthesized = await analysis.synthesize_research_evidence(run)
    run = run.with_stage_result("synthesize", synthesized)
    validated = await analysis.validate_research_evidence(run)

    assert extracted.checkpoint["source_ids"] == ["source:one", "source:two"]
    assert compared.checkpoint["comparison"]["agreements"]
    assert synthesized.checkpoint["supported_claim_count"] == 2
    assert validated.checkpoint == compared.checkpoint


@pytest.mark.asyncio
async def test_research_analysis_rejects_empty_saved_source_text(monkeypatch) -> None:
    async def source_get(source_id: str):
        return SimpleNamespace(id=source_id, full_text="")

    monkeypatch.setattr(analysis.Source, "get", source_get)
    with pytest.raises(ValueError, match="no extractable text"):
        await analysis.extract_research_evidence(
            ResearchRun(objective="Check source", source_ids=["source:empty"])
        )
