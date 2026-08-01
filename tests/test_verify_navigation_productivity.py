from pathlib import Path

import pytest

from scripts import verify_navigation_productivity as verifier
from scripts.verify_navigation_productivity import run_verifier, verifier_config


def test_verifier_requires_persistent_api_and_surreal_runtime(tmp_path: Path) -> None:
    result = run_verifier(api_url="http://127.0.0.1:9", fixture_root=tmp_path / "fixture", output_path=tmp_path / "proof.json")
    assert result.exit_code != 0
    assert result.report["status"] == "blocked"
    assert result.report["external_writes"] == 0
    assert result.report["source_hashes_unchanged"] is True


def test_verifier_rejects_real_second_brain_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fixture root required"):
        verifier_config(fixture_root=Path("/Users/Antman/Desktop/2nd Brains"), output_path=tmp_path / "proof.json")


def test_report_contains_only_redacted_synthetic_evidence(tmp_path: Path) -> None:
    result = run_verifier(api_url="http://127.0.0.1:9", fixture_root=tmp_path / "fixture", output_path=tmp_path / "proof.json")
    assert result.report["fixture"]["kind"] == "synthetic"  # type: ignore[index]
    assert "Plan.md" not in (tmp_path / "proof.json").read_text(encoding="utf-8")


def test_verifier_rejects_existing_user_content_and_output_inside_fixture(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "user.md").write_text("do not touch", encoding="utf-8")
    with pytest.raises(ValueError, match="fixture root required"):
        verifier_config(fixture_root=root, output_path=tmp_path / "proof.json")

    owned = tmp_path / "owned"
    verifier_config(fixture_root=owned, output_path=tmp_path / "proof.json")
    with pytest.raises(ValueError, match="proof output"):
        verifier_config(fixture_root=owned, output_path=owned / "proof.json")


def test_verifier_rejects_existing_output_and_keeps_aggregate_status_blocked(tmp_path: Path) -> None:
    output = tmp_path / "proof.json"
    output.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="proof output"):
        verifier_config(fixture_root=tmp_path / "fixture", output_path=output)

    result = run_verifier(api_url="http://127.0.0.1:9", fixture_root=tmp_path / "fresh", output_path=tmp_path / "fresh-proof.json")
    assert result.report["status"] == "blocked"
    assert result.report["synthetic_passed"] is True


def test_source_hash_baseline_precedes_every_proof_action(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "fixture"

    def mutate_after_baseline(_: str) -> tuple[bool, None]:
        (root / "obsidian" / "Pages" / "Plan.md").write_text("changed", encoding="utf-8")
        return False, None

    monkeypatch.setattr(verifier, "_api_health", mutate_after_baseline)
    result = run_verifier(api_url="http://127.0.0.1:9", fixture_root=root, output_path=tmp_path / "proof.json")
    assert result.report["source_hashes_unchanged"] is False
