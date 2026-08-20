"""Unit contracts for evaluation persistence queries."""

from __future__ import annotations

import pytest

from deeper_notebook.evaluation.repository import EvaluationRepository


@pytest.mark.asyncio
async def test_list_verdicts_selects_and_hides_ordering_metadata(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_repo_query(query: str, _vars: object) -> list[dict[str, object]]:
        captured["query"] = query
        return [
            {
                "created": "2026-07-18T00:00:00Z",
                "schema_version": 1,
                "claim": "A claim",
                "status": "uncited",
                "confidence": 0.2,
                "citation_markers": [],
                "evidence": [],
                "explanation": "No matching evidence was supplied.",
            }
        ]

    monkeypatch.setattr(
        "deeper_notebook.evaluation.repository.repo_query", fake_repo_query
    )

    verdicts = await EvaluationRepository().list_verdicts("evaluation_run:example")

    assert "SELECT created," in captured["query"]
    assert "ORDER BY created ASC" in captured["query"]
    assert [verdict.claim for verdict in verdicts] == ["A claim"]
