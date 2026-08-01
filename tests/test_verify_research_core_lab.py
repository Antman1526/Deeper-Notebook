import sys
from pathlib import Path

import pytest

from scripts import verify_research_core_lab as verifier
from scripts.verify_research_core_lab import run_verifier, verifier_config


def test_verifier_uses_only_a_new_owned_temporary_synthetic_root(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    output = tmp_path / "proof.json"
    result = run_verifier(
        native_url="http://127.0.0.1:9",
        fixture_root=root,
        output_path=output,
    )

    assert result.exit_code == 2
    assert result.report["status"] == "blocked"
    assert result.report["synthetic_passed"] is True
    assert result.report["source_hashes_unchanged"] is True
    assert result.report["external_writes"] == 0
    assert result.report["fixture"]["kind"] == "synthetic"  # type: ignore[index]
    assert (root / verifier._FIXTURE_SENTINEL).is_file()


def test_verifier_records_the_phase_one_contract_proofs_without_paths(tmp_path: Path) -> None:
    output = tmp_path / "proof.json"
    result = run_verifier(
        native_url="http://127.0.0.1:9",
        fixture_root=tmp_path / "fixture",
        output_path=output,
    )

    checks = result.report["checks"]  # type: ignore[assignment]
    assert checks["workspace_migration"]["status"] == "passed"  # type: ignore[index]
    assert checks["strict_local"]["cloud_requests"] == 0  # type: ignore[index]
    assert checks["heavyweight_mlx"]["second_reservation"] == "queued"  # type: ignore[index]
    assert checks["focused_gates"]["status"] == "not_run"  # type: ignore[index]
    proof = output.read_text(encoding="utf-8")
    assert str(tmp_path) not in proof
    assert "Plan.md" not in proof


def test_verifier_rejects_user_content_and_non_temporary_or_output_roots(tmp_path: Path) -> None:
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "user.md").write_text("do not touch", encoding="utf-8")
    with pytest.raises(ValueError, match="temporary synthetic fixture root required"):
        verifier_config(fixture_root=root, output_path=tmp_path / "proof.json")

    with pytest.raises(ValueError, match="temporary synthetic fixture root required"):
        verifier_config(fixture_root=Path("/Users/Antman/Desktop/MacBook AI models"), output_path=tmp_path / "proof.json")

    owned = tmp_path / "owned"
    verifier_config(fixture_root=owned, output_path=tmp_path / "proof.json")
    with pytest.raises(ValueError, match="new proof output file required"):
        verifier_config(fixture_root=owned, output_path=owned / "proof.json")


def test_default_cli_creates_a_fresh_owned_child_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class OwnedTemporaryDirectory:
        def __enter__(self) -> str:
            return str(tmp_path)

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(verifier.tempfile, "TemporaryDirectory", lambda **_: OwnedTemporaryDirectory())
    monkeypatch.setattr(sys, "argv", ["verify_research_core_lab.py"])
    assert verifier.main() == 2
    assert (tmp_path / "fixture" / verifier._FIXTURE_SENTINEL).is_file()
