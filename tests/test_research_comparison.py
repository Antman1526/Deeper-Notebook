"""Deterministic contradiction and evidence-gap contracts for Research Runs."""

import pytest

from open_notebook.research.comparison import (
    ClaimVerificationError,
    ComparisonSource,
    compare_research_sources,
)
from open_notebook.research.graph import ResearchWorkflow
from open_notebook.research.state import ResearchRun, ResearchStageResult
from open_notebook.studio.renderers import render_artifact_markdown
from open_notebook.studio.schemas import ResearchRunDocument


def _source(source_id: str, text: str, marker: str) -> ComparisonSource:
    return ComparisonSource(source_id, text, marker)


def test_comparison_groups_matching_numeric_claims_as_a_cited_agreement() -> None:
    comparison = compare_research_sources(
        [
            _source("source:policy", "The policy permits three retries.", "[S1]"),
            _source("source:guide", "The policy permits 3 retries.", "[S2]"),
        ]
    )

    assert len(comparison.agreements) == 1
    agreement = comparison.agreements[0]
    assert {position.source_id for position in agreement.positions} == {
        "source:policy",
        "source:guide",
    }
    assert all(position.citations for position in agreement.positions)
    assert comparison.contradictions == []
    assert comparison.gaps == []


def test_comparison_marks_numeric_and_date_disagreement_with_positions() -> None:
    comparison = compare_research_sources(
        [
            _source(
                "source:release",
                "The migration completed on 12 March 2026 after 3 retries.",
                "[S1]",
            ),
            _source(
                "source:incident",
                "The migration completed on 13 March 2026 after 2 retries.",
                "[S2]",
            ),
        ]
    )

    assert len(comparison.contradictions) == 1
    contradiction = comparison.contradictions[0]
    assert "2026-03-12" in contradiction.values
    assert "2026-03-13" in contradiction.values
    assert {position.source_id for position in contradiction.positions} == {
        "source:release",
        "source:incident",
    }


def test_comparison_exposes_single_source_claim_as_an_unresolved_gap() -> None:
    comparison = compare_research_sources(
        [_source("source:one", "The archive retains audit receipts.", "[S1]")]
    )

    assert comparison.agreements == []
    assert comparison.contradictions == []
    assert comparison.gaps == [
        "Unresolved evidence for archive: archive retain audit receipt (sources: source:one)."
    ]


def test_comparison_fails_closed_when_an_extracted_claim_is_not_supported() -> None:
    with pytest.raises(ClaimVerificationError, match="not supported"):
        compare_research_sources(
            [
                ComparisonSource(
                    "source:guide",
                    "The import retries two times after failure.",
                    "[S1]",
                    claims=("The import retries three times.",),
                )
            ]
        )


@pytest.mark.asyncio
async def test_validate_stage_requires_strict_comparison_before_complete() -> None:
    class Store:
        def __init__(self) -> None:
            self.run = ResearchRun(
                id="research_run:comparison",
                objective="Compare the sources",
                stage="validate",
            )

        async def get(self, run_id: str):
            return self.run if self.run.id == run_id else None

        async def save_stage_result(self, run, stage, result):
            self.run = run.with_stage_result(stage, result)
            return self.run

        async def request_cancellation(self, run_id: str):
            return self.run

        async def set_command_id(self, run_id: str, command_id: str):
            return self.run

    comparison = compare_research_sources(
        [
            _source("source:one", "The archive retains audit receipts.", "[S1]"),
            _source("source:two", "The archive retains audit receipts.", "[S2]"),
        ]
    )

    async def validate(run: ResearchRun) -> ResearchStageResult:
        return ResearchStageResult(checkpoint=comparison.as_checkpoint())

    completed = await ResearchWorkflow(Store(), {"validate": validate}).resume(
        "research_run:comparison"
    )
    assert completed.stage == "complete"

    async def invalid_validate(run: ResearchRun) -> ResearchStageResult:
        return ResearchStageResult(checkpoint={})

    with pytest.raises(ClaimVerificationError, match="strict comparison receipt"):
        await ResearchWorkflow(Store(), {"validate": invalid_validate}).resume(
            "research_run:comparison"
        )


def test_research_run_schema_and_markdown_remain_compatible_with_new_comparisons() -> (
    None
):
    legacy = ResearchRunDocument.model_validate(
        {
            "artifact_type": "research_run",
            "title": "Legacy research",
            "objective": "Retain old schema-v1 payloads.",
            "stages": [{"title": "Review", "status": "complete"}],
        }
    )
    assert legacy.agreements == []
    assert legacy.contradictions == []

    comparison = compare_research_sources(
        [
            _source("source:one", "The archive retains audit receipts.", "[S1]"),
            _source("source:two", "The archive retains audit receipts.", "[S2]"),
        ]
    )
    document = legacy.model_copy(
        update={
            "agreements": comparison.agreements,
            "contradictions": comparison.contradictions,
            "gaps": comparison.gaps,
        }
    )
    markdown = render_artifact_markdown(document)
    assert "## Agreements" in markdown
    assert "The archive retains audit receipts. [S1]" in markdown
