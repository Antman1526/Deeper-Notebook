"""Regression coverage for the deterministic source-visual budget receipt."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure_source_visuals.py"
SPEC = importlib.util.spec_from_file_location("measure_source_visuals", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
measure_source_visuals = importlib.util.module_from_spec(SPEC)
sys.modules["measure_source_visuals"] = measure_source_visuals
SPEC.loader.exec_module(measure_source_visuals)


def test_empty_extractor_results_fail_the_budget_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A zero-candidate run cannot claim a successful visual extraction proof."""

    async def no_candidates(_fixture: Path) -> list[object]:
        return []

    monkeypatch.setattr(
        measure_source_visuals, "RECEIPT_PATH", tmp_path / "receipt.json"
    )
    monkeypatch.setattr(
        measure_source_visuals, "extract_pdf_candidates", lambda _fixture: []
    )
    monkeypatch.setattr(
        measure_source_visuals, "extract_video_candidates", no_candidates
    )
    monkeypatch.setattr(measure_source_visuals, "extract_audio_artwork", no_candidates)

    with pytest.raises(RuntimeError, match="nonempty visual extraction"):
        asyncio.run(measure_source_visuals.main())

    receipt = json.loads((tmp_path / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["passed"] is False
    for fixture in receipt["fixtures"].values():
        assert fixture["candidate_count"] == 0
        assert fixture["output_webp_bytes"] == 0
