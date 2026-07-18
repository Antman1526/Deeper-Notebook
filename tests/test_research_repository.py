"""Unit contracts for research-run persistence deserialization."""

from __future__ import annotations

from open_notebook.research.repository import _run_from_record


def test_research_repository_discards_database_audit_metadata() -> None:
    run = _run_from_record(
        {
            "id": "research_run:example",
            "objective": "Verify saved state",
            "created": "2026-07-18T00:00:00Z",
            "updated": "2026-07-18T00:01:00Z",
        }
    )

    assert run.id == "research_run:example"
    assert run.objective == "Verify saved state"
