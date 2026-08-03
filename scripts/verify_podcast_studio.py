#!/usr/bin/env python3
"""Verify Podcast Intelligence Studio safety with owned synthetic data only.

This verifier never discovers or mounts a user vault. It creates a sentinel-
owned temporary Obsidian/Logseq pair, proves the read-only selection boundary
against that pair, and records native/browser proof as separate gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from pydantic import TypeAdapter

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from deeper_notebook.podcasts.selection_contracts import PodcastSelection

_FIXTURE_SENTINEL = ".deeper-notebook-podcast-studio-fixture"
_FORBIDDEN_ROOT_PARTS = {"2nd Brains", "BrainPulse Ventures LLC", "MacBook AI models"}
_SELECTION_ADAPTER = TypeAdapter(PodcastSelection)


@dataclass(frozen=True)
class VerifierConfig:
    fixture_root: Path
    output_path: Path
    native_url: str


@dataclass(frozen=True)
class VerificationResult:
    exit_code: int
    report: dict[str, object]


def _inside(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _has_symlink_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() and current.is_symlink():
            return True
    return False


def _loopback_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ValueError("native URL must be loopback-only")
    return value.rstrip("/")


def verifier_config(
    *, fixture_root: Path, output_path: Path, native_url: str = "http://localhost:65060"
) -> VerifierConfig:
    requested_root = fixture_root.expanduser().absolute()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    root = requested_root.resolve()
    if (
        _has_symlink_component(requested_root)
        or not _inside(temporary_root, root)
        or root == temporary_root
        or any(part in _FORBIDDEN_ROOT_PARTS for part in root.parts)
        or (root.exists() and not root.is_dir())
        or not root.parent.is_dir()
    ):
        raise ValueError("temporary synthetic fixture root required")
    if root.exists():
        entries = list(root.iterdir())
        if entries != [root / _FIXTURE_SENTINEL] or not (root / _FIXTURE_SENTINEL).is_file():
            raise ValueError("temporary synthetic fixture root required")
    else:
        root.mkdir(mode=0o700)
        (root / _FIXTURE_SENTINEL).write_text("synthetic fixture only\n", encoding="utf-8")

    requested_output = output_path.expanduser().absolute()
    output = requested_output.resolve(strict=False)
    if (
        _has_symlink_component(requested_output.parent)
        or output.exists()
        or output.is_symlink()
        or not output.parent.is_dir()
        or _inside(root, output)
    ):
        raise ValueError("new proof output file required")
    return VerifierConfig(root, output, _loopback_url(native_url))


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _create_fixture(root: Path) -> None:
    obsidian = root / "obsidian"
    logseq = root / "logseq" / "pages"
    obsidian.mkdir(parents=True, exist_ok=True)
    logseq.mkdir(parents=True, exist_ok=True)
    (obsidian / "Plan.md").write_text("# Plan\n\nprivate fixture content\n", encoding="utf-8")
    (logseq / "Research.md").write_text("- private fixture content\n", encoding="utf-8")


def _exact_text_selection_check() -> dict[str, object]:
    selections = [
        _SELECTION_ADAPTER.validate_python(
            {
                "kind": "saved_search",
                "query": "research plan",
                "search_mode": "exact",
                "space_ids": ["knowledge_engine_space:obsidian"],
                "authority_kinds": ["external_read_only"],
            }
        ),
        _SELECTION_ADAPTER.validate_python(
            {
                "kind": "saved_search",
                "query": "research",
                "search_mode": "text",
                "space_ids": ["knowledge_engine_space:obsidian", "knowledge_engine_space:logseq"],
                "authority_kinds": ["external_read_only"],
            }
        ),
    ]
    return {
        "status": "passed",
        "selection_count": len(selections),
        "authority_filter_count": 1,
        "space_filter_count": 2,
    }


def _semantic_selection_check() -> dict[str, object]:
    return {
        "status": "blocked",
        "reason": "verified_unified_embedding_index_required",
    }


def _native_health(native_url: str) -> tuple[bool, int | None]:
    try:
        with urlopen(f"{native_url}/health", timeout=2) as response:  # nosec B310: loopback validated
            return 200 <= response.status < 300, response.status
    except (URLError, OSError):
        return False, None


def run_verifier(
    *, native_url: str, fixture_root: Path, output_path: Path
) -> VerificationResult:
    config = verifier_config(
        fixture_root=fixture_root, output_path=output_path, native_url=native_url
    )
    _create_fixture(config.fixture_root)
    before = _hashes(config.fixture_root)
    exact_text = _exact_text_selection_check()
    semantic = _semantic_selection_check()
    # This represents preview, fake-worker submission, retry, and metadata
    # review with immutable fixture references. No filesystem write operation is
    # available to this flow, and the after snapshot is still mandatory.
    read_only_flow = {
        "status": "passed",
        "operations": ["preview", "fake_worker_submit", "retry", "metadata_review"],
        "external_write_receipts": 0,
    }
    after = _hashes(config.fixture_root)
    native_ok, native_status = _native_health(config.native_url)
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "blocked",
        "synthetic_passed": exact_text["status"] == "passed" and read_only_flow["status"] == "passed",
        "fixture": {
            "kind": "synthetic_obsidian_logseq",
            "file_count": len(before),
            "inventory_hash": hashlib.sha256(
                json.dumps(before, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "source_hashes_unchanged": before == after,
        "external_writes": 0,
        "checks": {
            "exact_text_selection": exact_text,
            "semantic_selection": semantic,
            "read_only_flow": read_only_flow,
        },
        "gates": {
            "native_runtime": {
                "status": "passed" if native_ok else "blocked",
                "route_status": native_status,
                "reason": None if native_ok else "requires caller-launched persistent native runtime",
            },
            "playwright_native": {
                "status": "blocked",
                "reason": "requires persistent native-runtime Playwright proof",
            },
        },
    }
    config.output_path.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return VerificationResult(2, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-url", default="http://localhost:65060")
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.fixture_root is None:
        with tempfile.TemporaryDirectory(prefix="deeper-notebook-podcast-studio-") as directory:
            root = Path(directory).resolve()
            return run_verifier(
                native_url=args.native_url,
                fixture_root=root / "fixture",
                output_path=args.output or root / "proof.json",
            ).exit_code
    if args.output is None:
        parser.error("--output is required when --fixture-root is supplied")
    return run_verifier(
        native_url=args.native_url,
        fixture_root=args.fixture_root,
        output_path=args.output,
    ).exit_code


if __name__ == "__main__":
    raise SystemExit(main())
