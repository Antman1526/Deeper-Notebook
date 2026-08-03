#!/usr/bin/env python3
"""Verify Podcast Intelligence Studio safety with owned synthetic data only.

This verifier never discovers or mounts a user vault. It creates a sentinel-
owned temporary Obsidian/Logseq pair, proves the read-only selection boundary
against that pair, and records native/browser proof as separate gates.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from pydantic import TypeAdapter

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from deeper_notebook.podcasts.selection_contracts import PodcastSelection
from deeper_notebook.podcasts.selection_service import (
    PodcastSelectionService,
    ResolvedSelectionItem,
)

_FIXTURE_SENTINEL = ".deeper-notebook-podcast-studio-fixture"
_FORBIDDEN_ROOT_PARTS = {"2nd Brains", "BrainPulse Ventures LLC", "MacBook AI models"}
_SELECTION_ADAPTER = TypeAdapter(PodcastSelection)
_PLAYWRIGHT_NATIVE_TEST_FILE = "e2e/podcast-intelligence-studio.spec.ts"
_PLAYWRIGHT_NATIVE_TEST_COUNT = 5


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


class _SyntheticReadOnlyResolver:
    """Bounded fixture reader injected into the real selection service."""

    def __init__(self, fixture_root: Path) -> None:
        self._fixture_root = fixture_root
        self.external_write_attempts = 0

    async def resolve(self, selection: PodcastSelection) -> list[ResolvedSelectionItem]:
        if selection.kind != "saved_search":
            raise ValueError("podcast_selection_kind_unavailable")
        fixture_files = (
            self._fixture_root / "obsidian" / "Plan.md",
            self._fixture_root / "logseq" / "pages" / "Research.md",
        )
        items: list[ResolvedSelectionItem] = []
        for index, fixture_file in enumerate(fixture_files, start=1):
            content = fixture_file.read_text(encoding="utf-8").strip()
            items.append(
                ResolvedSelectionItem(
                    stable_id=f"knowledge_engine_document:synthetic_{index}",
                    title=f"Synthetic fixture {index}",
                    authority_kind="external_read_only",
                    relative_locator=f"fixture_{index}",
                    revision_id=f"knowledge_engine_revision:synthetic_{index}",
                    fingerprint=hashlib.sha256(content.encode()).hexdigest(),
                    content=content,
                )
            )
        return items


class _SyntheticEpisodeProfile:
    pass


class _SyntheticSpeakerProfile:
    speakers = ("Synthetic one", "Synthetic two")


class _SyntheticRetryEpisode:
    """Storage-neutral episode fake for the real durable retry handler."""

    id = "episode:synthetic"
    name = "Synthetic verification episode"
    episode_profile = {"name": "Synthetic episode"}
    speaker_profile = {"name": "Synthetic speakers"}
    briefing_suffix = None
    mode = "deep_dive"
    custom_prompt = None
    selection_summary = {"version": 1, "included_count": 2}
    selection_fingerprint = "a" * 64
    editorial_brief = None
    model_plan_receipts: list[dict[str, object]] = []
    retry_submitted = None

    def __init__(self, *, content: str, audio_file: str) -> None:
        self.content = content
        self.audio_file = audio_file
        self.command = "command:original"
        self.deleted = False
        self.saved = False

    async def get_job_detail(self) -> dict[str, str]:
        return {"status": "failed", "error_message": "synthetic failure"}

    async def save(self) -> None:
        self.saved = True

    async def delete(self) -> None:
        self.deleted = True


async def _execute_read_only_flow(fixture_root: Path) -> dict[str, object]:
    """Execute bounded preview, submission, retry, and inspection seams."""
    import api.podcast_service as podcast_service_module
    import api.routers.podcasts as podcast_router_module
    from api.podcast_service import PodcastService
    from deeper_notebook.podcasts.models import EpisodeProfile, SpeakerProfile

    resolver = _SyntheticReadOnlyResolver(fixture_root)
    selection = _SELECTION_ADAPTER.validate_python(
        {
            "kind": "saved_search",
            "query": "synthetic research",
            "search_mode": "text",
            "space_ids": ["knowledge_engine_space:synthetic"],
            "authority_kinds": ["external_read_only"],
        }
    )
    preparation = await PodcastSelectionService(resolver=resolver).prepare([selection])
    if not preparation.preview.current_worker_eligible:
        raise RuntimeError("synthetic selection was unexpectedly ineligible")

    submissions: list[str] = []

    async def profile_lookup(name: str):
        if name == "Synthetic episode":
            return _SyntheticEpisodeProfile()
        if name == "Synthetic speakers":
            return _SyntheticSpeakerProfile()
        return None

    async def allow_synthetic_local_profiles(*_args: object) -> None:
        return None

    def fake_submit_command(module: str, command: str, _arguments: dict[str, object]) -> str:
        if (module, command) != ("open_notebook", "generate_podcast"):
            raise AssertionError("unexpected synthetic command")
        job_id = f"command:synthetic-{len(submissions) + 1}"
        submissions.append(job_id)
        return job_id

    with tempfile.TemporaryDirectory(prefix="deeper-notebook-podcast-audio-") as audio_directory:
        audio_root = (Path(audio_directory) / "episodes").resolve()
        audio_root.mkdir()
        old_audio = audio_root / "episode.mp3"
        old_audio.write_bytes(b"synthetic audio bytes")
        old_audio_bytes = old_audio.stat().st_size
        episode = _SyntheticRetryEpisode(
            content=preparation.content,
            audio_file=str(old_audio),
        )

        async def get_synthetic_episode(episode_id: str) -> _SyntheticRetryEpisode:
            if episode_id != episode.id:
                raise LookupError("synthetic episode not found")
            return episode

        with (
            patch.object(EpisodeProfile, "get_by_name", new=profile_lookup),
            patch.object(SpeakerProfile, "get_by_name", new=profile_lookup),
            patch.object(
                PodcastService,
                "_gate_offline_cloud_models",
                new=allow_synthetic_local_profiles,
            ),
            patch.object(
                podcast_service_module,
                "submit_command",
                new=fake_submit_command,
            ),
            patch.object(PodcastService, "get_episode", new=get_synthetic_episode),
            patch.object(podcast_router_module, "_AUDIO_ROOT", new=audio_root),
        ):
            first_job_id = await PodcastService.submit_generation_job(
                episode_profile_name="Synthetic episode",
                speaker_profile_name="Synthetic speakers",
                episode_name="Synthetic verification episode",
                content=preparation.content,
            )
            retry = await podcast_router_module._retry_podcast_episode_locked(episode.id)

    retry_marker = getattr(episode, "retry_submitted", None)
    if (
        first_job_id != "command:synthetic-1"
        or retry.get("job_id") != "command:synthetic-2"
        or not episode.deleted
        or retry_marker is None
        or retry_marker.job_id != retry.get("job_id")
    ):
        raise RuntimeError("synthetic podcast flow did not complete durably")
    return {
        "status": "passed",
        "preview": {"included_count": len(preparation.preview.entries)},
        "submission": {"fake_worker_job_count": len(submissions)},
        "retry": {"job_id": retry["job_id"], "durable_fence": True},
        "metadata_audio": {
            "old_audio_bytes": old_audio_bytes,
            "old_audio_removed_after_retry": not old_audio.exists(),
        },
        "external_write_receipts": resolver.external_write_attempts,
    }


def _native_health(native_url: str) -> tuple[bool, int | None]:
    try:
        with urlopen(f"{native_url}/health", timeout=2) as response:  # nosec B310: loopback validated
            return 200 <= response.status < 300, response.status
    except (URLError, OSError):
        return False, None


def _playwright_native_gate(report_path: Path | None) -> dict[str, object]:
    """Accept only a complete, passing report for the owned native project."""
    if report_path is None:
        return {
            "status": "blocked",
            "reason": "requires persistent native-runtime Playwright proof",
        }
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "blocked",
            "reason": "requires a readable native-runtime Playwright JSON report",
        }
    if not isinstance(report, dict) or report.get("errors") != []:
        return {
            "status": "blocked",
            "reason": "native-runtime Playwright report contains runner errors",
        }
    config = report.get("config")
    if not isinstance(config, dict):
        return {
            "status": "blocked",
            "reason": "native-runtime Playwright report is missing its test configuration",
        }
    argv = config.get("argv")
    root_dir = config.get("rootDir")
    if (
        not isinstance(argv, list)
        or _PLAYWRIGHT_NATIVE_TEST_FILE not in argv
        or not isinstance(root_dir, str)
        or Path(root_dir).name != "e2e"
    ):
        return {
            "status": "blocked",
            "reason": "Playwright report does not target the native studio test file",
        }

    matching_tests: list[dict[str, object]] = []

    def collect_matching_tests(suites: object) -> None:
        if not isinstance(suites, list):
            return
        for suite in suites:
            if not isinstance(suite, dict):
                continue
            suite_file = suite.get("file")
            if suite_file == Path(_PLAYWRIGHT_NATIVE_TEST_FILE).name:
                specs = suite.get("specs")
                if isinstance(specs, list):
                    for spec in specs:
                        if not isinstance(spec, dict):
                            continue
                        tests = spec.get("tests")
                        if not isinstance(tests, list):
                            continue
                        for test in tests:
                            if (
                                isinstance(test, dict)
                                and test.get("projectName") == "native-runtime"
                            ):
                                matching_tests.append(test)
            collect_matching_tests(suite.get("suites"))

    collect_matching_tests(report.get("suites"))
    statuses: list[object] = []
    for test in matching_tests:
        results = test.get("results")
        if not isinstance(results, list) or len(results) != 1:
            return {
                "status": "blocked",
                "reason": "native-runtime Playwright report has incomplete test results",
            }
        result = results[0]
        statuses.append(result.get("status") if isinstance(result, dict) else None)

    stats = report.get("stats")
    if (
        len(matching_tests) != _PLAYWRIGHT_NATIVE_TEST_COUNT
        or statuses != ["passed"] * _PLAYWRIGHT_NATIVE_TEST_COUNT
        or not isinstance(stats, dict)
        or stats.get("expected") != _PLAYWRIGHT_NATIVE_TEST_COUNT
        or stats.get("unexpected") != 0
        or stats.get("skipped") != 0
    ):
        return {
            "status": "blocked",
            "reason": "native-runtime Playwright report must contain five passing, unskipped studio cases",
        }
    return {
        "status": "passed",
        "test_file": _PLAYWRIGHT_NATIVE_TEST_FILE,
        "test_count": _PLAYWRIGHT_NATIVE_TEST_COUNT,
    }


def run_verifier(
    *,
    native_url: str,
    fixture_root: Path,
    output_path: Path,
    playwright_report_path: Path | None = None,
) -> VerificationResult:
    config = verifier_config(
        fixture_root=fixture_root, output_path=output_path, native_url=native_url
    )
    _create_fixture(config.fixture_root)
    before = _hashes(config.fixture_root)
    exact_text = _exact_text_selection_check()
    semantic = _semantic_selection_check()
    read_only_flow = asyncio.run(_execute_read_only_flow(config.fixture_root))
    after = _hashes(config.fixture_root)
    native_ok, native_status = _native_health(config.native_url)
    playwright_native = _playwright_native_gate(playwright_report_path)
    passed = (
        exact_text["status"] == "passed"
        and read_only_flow["status"] == "passed"
        and before == after
        and read_only_flow["external_write_receipts"] == 0
        and native_ok
        and playwright_native["status"] == "passed"
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "status": "passed" if passed else "blocked",
        "synthetic_passed": exact_text["status"] == "passed" and read_only_flow["status"] == "passed",
        "fixture": {
            "kind": "synthetic_obsidian_logseq",
            "file_count": len(before),
            "inventory_hash": hashlib.sha256(
                json.dumps(before, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        },
        "source_hashes_unchanged": before == after,
        "external_writes": read_only_flow["external_write_receipts"],
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
            "playwright_native": playwright_native,
        },
    }
    config.output_path.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return VerificationResult(0 if passed else 2, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-url", default="http://localhost:65060")
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--playwright-report", type=Path)
    args = parser.parse_args()
    if args.fixture_root is None:
        with tempfile.TemporaryDirectory(prefix="deeper-notebook-podcast-studio-") as directory:
            root = Path(directory).resolve()
            return run_verifier(
                native_url=args.native_url,
                fixture_root=root / "fixture",
                output_path=args.output or root / "proof.json",
                playwright_report_path=args.playwright_report,
            ).exit_code
    if args.output is None:
        parser.error("--output is required when --fixture-root is supplied")
    return run_verifier(
        native_url=args.native_url,
        fixture_root=args.fixture_root,
        output_path=args.output,
        playwright_report_path=args.playwright_report,
    ).exit_code


if __name__ == "__main__":
    raise SystemExit(main())
