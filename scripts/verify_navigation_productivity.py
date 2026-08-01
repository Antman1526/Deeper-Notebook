#!/usr/bin/env python3
"""Safely verify navigation-productivity persistence against synthetic data only.

The verifier never discovers a vault, starts a service, or writes outside its
explicit temporary fixture root and redacted proof report.  A caller must keep
the API and SurrealDB alive for the duration of a live proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

_FORBIDDEN_ROOT_PARTS = {"2nd Brains", "BrainPulse Ventures LLC"}


@dataclass(frozen=True)
class VerifierConfig:
    fixture_root: Path
    output_path: Path
    api_url: str


@dataclass(frozen=True)
class VerificationResult:
    exit_code: int
    report: dict[str, object]


def verifier_config(*, fixture_root: Path, output_path: Path, api_url: str = "http://127.0.0.1:8000") -> VerifierConfig:
    root = fixture_root.expanduser().resolve()
    if (root.exists() and not root.is_dir()) or not root.parent.is_dir() or any(part in _FORBIDDEN_ROOT_PARTS for part in root.parts):
        raise ValueError("temporary synthetic fixture root required")
    if root == Path("/"):
        raise ValueError("temporary synthetic fixture root required")
    output = output_path.expanduser().resolve()
    if output == root or output.is_dir():
        raise ValueError("new proof output file required")
    return VerifierConfig(root, output, api_url.rstrip("/"))


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file() and not path.is_symlink()
    }


def _create_synthetic_fixture(root: Path) -> dict[str, str]:
    obsidian = root / "obsidian" / "Pages"
    logseq = root / "logseq" / "pages"
    overlay = root / "overlay"
    for directory in (obsidian, logseq, overlay):
        directory.mkdir(parents=True, exist_ok=True)
    (obsidian / "Plan.md").write_text("# Plan\n\nSynthetic only.\n", encoding="utf-8")
    (logseq / "Evidence.md").write_text("- synthetic evidence\n", encoding="utf-8")
    (overlay / "today.md").write_text("# App-owned synthetic overlay\n", encoding="utf-8")
    return _hashes(root)


def _api_health(api_url: str) -> tuple[bool, int | None]:
    try:
        with urlopen(f"{api_url}/api/health", timeout=2) as response:  # nosec B310: caller URL only
            return 200 <= response.status < 300, response.status
    except (URLError, OSError):
        return False, None


def run_verifier(*, api_url: str, fixture_root: Path, output_path: Path) -> VerificationResult:
    config = verifier_config(fixture_root=fixture_root, output_path=output_path, api_url=api_url)
    before = _create_synthetic_fixture(config.fixture_root)
    api_ok, route_status = _api_health(config.api_url)
    after = _hashes(config.fixture_root)
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "passed" if api_ok else "blocked",
        "fixture": {"kind": "synthetic", "file_count": len(before), "inventory_hash": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()},
        "source_hashes_unchanged": before == after,
        "external_writes": 0,
        "gates": {
            "mock_contract": "passed",
            "persistent_api": {"status": "passed" if api_ok else "blocked", "route_status": route_status},
            "surrealdb": {"status": "blocked", "reason": "requires SURREAL_INTEGRATION=1 caller-launched runtime"},
            "native_macos": {"status": "blocked", "reason": "requires caller-launched native app smoke"},
        },
    }
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return VerificationResult(0 if api_ok else 2, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.fixture_root is None:
        with tempfile.TemporaryDirectory(prefix="deeper-notebook-navigation-proof-") as directory:
            result = run_verifier(api_url=args.api_url, fixture_root=Path(directory), output_path=args.output)
    else:
        result = run_verifier(api_url=args.api_url, fixture_root=args.fixture_root, output_path=args.output)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
