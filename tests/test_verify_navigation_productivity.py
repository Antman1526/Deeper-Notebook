import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

import pytest

from scripts import verify_navigation_productivity as verifier
from scripts.verify_navigation_productivity import run_verifier, verifier_config


class _DirectHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


@contextmanager
def _direct_health_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _DirectHealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_verifier_requires_persistent_api_and_surreal_runtime(tmp_path: Path) -> None:
    result = run_verifier(api_url="http://127.0.0.1:9", fixture_root=tmp_path / "fixture", output_path=tmp_path / "proof.json")
    assert result.exit_code != 0
    assert result.report["status"] == "blocked"
    assert result.report["external_writes"] == 0
    assert result.report["source_hashes_unchanged"] is True


def test_verifier_probes_the_native_api_direct_health_endpoint() -> None:
    with _direct_health_server() as api_url:
        assert verifier._api_health(api_url) == (True, 200)


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


def test_default_cli_uses_fresh_owned_child_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class OwnedTemporaryDirectory:
        def __enter__(self) -> str:
            return str(tmp_path)

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(verifier.tempfile, "TemporaryDirectory", lambda **_: OwnedTemporaryDirectory())
    monkeypatch.setattr(verifier, "_api_health", lambda _: (False, None))
    monkeypatch.setattr(sys, "argv", ["verify_navigation_productivity.py"])
    assert verifier.main() == 2
    report = (tmp_path / "proof.json").read_text(encoding="utf-8")
    assert '"status": "blocked"' in report
    assert '"synthetic_passed": true' in report
    assert (tmp_path / "fixture" / verifier._FIXTURE_SENTINEL).is_file()


def test_default_cli_accepts_a_real_temporary_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    original_run = verifier.run_verifier

    def capture_run(**kwargs: object):
        captured.update(kwargs)
        return original_run(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(verifier, "run_verifier", capture_run)
    monkeypatch.setattr(verifier, "_api_health", lambda _: (False, None))
    monkeypatch.setattr(sys, "argv", ["verify_navigation_productivity.py"])
    assert verifier.main() == 2
    fixture_root = captured["fixture_root"]
    output_path = captured["output_path"]
    assert isinstance(fixture_root, Path) and isinstance(output_path, Path)
    assert fixture_root.name == "fixture"
    assert output_path.name == "proof.json"
    assert output_path.parent == fixture_root.parent
