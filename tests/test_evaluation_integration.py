from types import SimpleNamespace

import pytest

from api.routers import evaluations
from open_notebook.evaluation.schemas import ClaimVerdict
from open_notebook.studio.generation.service import (
    _critical_verdicts,
    _strict_evidence_required,
)


@pytest.mark.asyncio
async def test_evaluation_detail_requires_matching_notebook(monkeypatch):
    async def fake_query(query, variables):
        assert variables["run_id"] == "evaluation_run:one"
        assert variables["notebook_id"] == "notebook:mine"
        return [
            {
                "id": "evaluation_run:one",
                "notebook_id": "notebook:mine",
                "evaluator_version": "deterministic-v1",
                "metrics": {"status": "completed"},
            }
        ]

    class Repository:
        async def list_verdicts(self, run_id):
            assert run_id == "evaluation_run:one"
            return [
                ClaimVerdict(
                    claim="The report is complete.",
                    status="uncited",
                    confidence=1,
                    explanation="No source marker.",
                )
            ]

    monkeypatch.setattr(evaluations, "repo_query", fake_query)
    monkeypatch.setattr(evaluations, "ensure_record_id", lambda value: value)
    monkeypatch.setattr(evaluations, "EvaluationRepository", Repository)

    payload = await evaluations.get_evaluation("evaluation_run:one", "notebook:mine")
    assert payload["status"] == "completed"
    assert payload["counts"]["uncited"] == 1
    assert payload["run"]["notebook_id"] == "notebook:mine"


def test_strict_mode_defaults_only_to_publishable_artifacts(monkeypatch):
    monkeypatch.delenv("ONP_STUDIO_STRICT_EVIDENCE", raising=False)
    assert _strict_evidence_required(SimpleNamespace(artifact_type="report"))
    assert not _strict_evidence_required(SimpleNamespace(artifact_type="flashcards"))
    monkeypatch.setenv("ONP_STUDIO_STRICT_EVIDENCE", "false")
    assert not _strict_evidence_required(SimpleNamespace(artifact_type="report"))


def test_critical_evidence_keeps_contradiction_distinct_from_partial():
    source = SimpleNamespace(id="source:one", full_text="The launch date is 2025.")
    verdicts = _critical_verdicts("The launch date is 2026 [S1].", [source])
    assert [verdict.status for verdict in verdicts] == ["contradicted"]
