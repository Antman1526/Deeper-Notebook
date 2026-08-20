"""Static contract for the required real-SurrealDB CI authority gate."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/test.yml"


def test_integration_surreal_ci_uses_the_tested_server_and_real_test_gate():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = workflow["jobs"]["integration-surreal"]
    start = next(step for step in job["steps"] if step["name"] == "Start SurrealDB")

    assert job["env"]["SURREAL_INTEGRATION"] == "1"
    assert "surrealdb/surrealdb:v2.6.5" in start["run"]
    assert "uv run pytest tests/integration/ -v -m integration_surreal" in next(
        step["run"] for step in job["steps"] if step["name"] == "Run integration tests"
    )
