"""Local, deterministic completion stages for persisted Research Runs."""

from __future__ import annotations

from open_notebook.domain.notebook import Source
from open_notebook.research.comparison import (
    ComparisonSource,
    ResearchComparison,
    compare_research_sources,
    require_strict_comparison,
)
from open_notebook.research.state import ResearchRun, ResearchStageResult

MAX_ANALYSIS_SOURCES = 20
MAX_SOURCE_CHARS = 100_000


async def _comparison_sources(run: ResearchRun) -> list[ComparisonSource]:
    """Read only the sources accepted by this run, with explicit size bounds."""
    sources: list[ComparisonSource] = []
    for index, source_id in enumerate(run.source_ids[:MAX_ANALYSIS_SOURCES], start=1):
        source = await Source.get(source_id)
        text = (source.full_text or "").strip()
        if not text:
            raise ValueError(f"Research source {source_id} has no extractable text")
        sources.append(
            ComparisonSource(
                source_id=str(source.id or source_id),
                text=text[:MAX_SOURCE_CHARS],
                citation_marker=f"[S{index}]",
            )
        )
    if not sources:
        raise ValueError("Research analysis requires at least one imported source")
    return sources


async def extract_research_evidence(run: ResearchRun) -> ResearchStageResult:
    """Create a compact receipt without duplicating source text into run state."""
    sources = await _comparison_sources(run)
    return ResearchStageResult(
        checkpoint={
            "source_count": len(sources),
            "source_ids": [source.source_id for source in sources],
            "text_limits_applied": MAX_SOURCE_CHARS,
        }
    )


async def compare_research_evidence(run: ResearchRun) -> ResearchStageResult:
    """Compare only persisted source text under the strict citation verifier."""
    comparison = compare_research_sources(await _comparison_sources(run))
    return ResearchStageResult(checkpoint=comparison.as_checkpoint())


def _comparison_from_run(run: ResearchRun) -> ResearchComparison:
    return require_strict_comparison(run.checkpoints.get("compare", {}))


async def synthesize_research_evidence(run: ResearchRun) -> ResearchStageResult:
    """Persist a non-generative summary receipt; it cannot introduce new claims."""
    comparison = _comparison_from_run(run)
    return ResearchStageResult(
        checkpoint={
            "objective": run.objective,
            "supported_claim_count": len(comparison.verdicts),
            "agreement_count": len(comparison.agreements),
            "contradiction_count": len(comparison.contradictions),
            "gap_count": len(comparison.gaps),
        }
    )


async def validate_research_evidence(run: ResearchRun) -> ResearchStageResult:
    """Carry forward the exact comparison receipt required by workflow completion."""
    comparison = _comparison_from_run(run)
    return ResearchStageResult(checkpoint=comparison.as_checkpoint())
