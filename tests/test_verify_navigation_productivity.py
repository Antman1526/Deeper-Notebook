from pathlib import Path

import pytest

from scripts.verify_navigation_productivity import run_verifier, verifier_config


def test_verifier_requires_persistent_api_and_surreal_runtime(tmp_path: Path) -> None:
    result = run_verifier(api_url="http://127.0.0.1:9", fixture_root=tmp_path, output_path=tmp_path / "proof.json")
    assert result.exit_code != 0
    assert result.report["status"] == "blocked"
    assert result.report["external_writes"] == 0
    assert result.report["source_hashes_unchanged"] is True


def test_verifier_rejects_real_second_brain_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fixture root required"):
        verifier_config(fixture_root=Path("/Users/Antman/Desktop/2nd Brains"), output_path=tmp_path / "proof.json")


def test_report_contains_only_redacted_synthetic_evidence(tmp_path: Path) -> None:
    result = run_verifier(api_url="http://127.0.0.1:9", fixture_root=tmp_path, output_path=tmp_path / "proof.json")
    assert result.report["fixture"]["kind"] == "synthetic"  # type: ignore[index]
    assert "Plan.md" not in (tmp_path / "proof.json").read_text(encoding="utf-8")
