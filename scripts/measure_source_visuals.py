#!/usr/bin/env python3
"""Measure deterministic local source-visual extraction and cache budgets."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from deeper_notebook.source_visuals.extractors import (
    extract_audio_artwork,
    extract_pdf_candidates,
    extract_video_candidates,
)
from deeper_notebook.source_visuals.media import VisualCandidate, prepare_webp
from deeper_notebook.source_visuals.storage import SourceVisualStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "source_visuals"
RECEIPT_PATH = Path(
    os.environ.get(
        "SOURCE_VISUAL_EXTRACTION_BUDGET_RECEIPT",
        "/tmp/deeper-notebook-source-gallery-extraction-budget.json",
    )
).resolve()
MAX_KIND_SECONDS = 60.0
MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class KindMeasurement:
    duration_seconds: float
    candidate_count: int
    output_webp_bytes: int
    fixture_sha256: str


def _fixture_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_and_publish(
    store: SourceVisualStore,
    kind: str,
    candidates: list[VisualCandidate],
) -> int:
    output_bytes = 0
    for index, candidate in enumerate(candidates):
        prepared = prepare_webp(candidate.encoded_bytes)
        output_bytes += len(prepared.encoded_bytes)
        content_sha256 = hashlib.sha256(candidate.encoded_bytes).hexdigest()
        staged = store.stage(f"source:budget-{kind}-{index}", content_sha256, prepared)
        store.publish(staged)
    return output_bytes


def _measure_sync(
    store: SourceVisualStore,
    kind: str,
    fixture: Path,
    extractor: object,
) -> KindMeasurement:
    started = time.perf_counter()
    candidates = list(extractor(fixture))  # type: ignore[operator]
    output_bytes = _prepare_and_publish(store, kind, candidates)
    duration = time.perf_counter() - started
    return KindMeasurement(duration, len(candidates), output_bytes, _fixture_sha256(fixture))


async def _measure_async(
    store: SourceVisualStore,
    kind: str,
    fixture: Path,
    extractor: object,
) -> KindMeasurement:
    started = time.perf_counter()
    extracted = await extractor(fixture)  # type: ignore[operator]
    candidates = [] if extracted is None else (extracted if isinstance(extracted, list) else [extracted])
    output_bytes = _prepare_and_publish(store, kind, candidates)
    duration = time.perf_counter() - started
    return KindMeasurement(duration, len(candidates), output_bytes, _fixture_sha256(fixture))


async def main() -> int:
    fixtures = {
        "pdf": FIXTURE_ROOT / "fixture.pdf",
        "video": FIXTURE_ROOT / "fixture.mp4",
        "audio": FIXTURE_ROOT / "fixture-artwork.m4a",
    }
    missing = [str(path) for path in fixtures.values() if not path.is_file()]
    if missing:
        raise RuntimeError(f"missing deterministic fixtures: {missing}")

    physical_temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
    with tempfile.TemporaryDirectory(
        prefix="dn-source-visual-budget-", dir=physical_temp_root
    ) as data_folder:
        store = SourceVisualStore(data_folder=data_folder)
        measurements = {
            "pdf": _measure_sync(store, "pdf", fixtures["pdf"], extract_pdf_candidates),
            "video": await _measure_async(
                store, "video", fixtures["video"], extract_video_candidates
            ),
            "audio": await _measure_async(
                store, "audio", fixtures["audio"], extract_audio_artwork
            ),
        }
        cache_bytes = store.cache_size_bytes()

    receipt = {
        "schema": "deeper-notebook.source-visual-extraction-budget.v1",
        "fixtures": {
            kind: {
                "sha256": measurement.fixture_sha256,
                "candidate_count": measurement.candidate_count,
                "duration_seconds": round(measurement.duration_seconds, 6),
                "output_webp_bytes": measurement.output_webp_bytes,
                "passed": measurement.duration_seconds <= MAX_KIND_SECONDS,
            }
            for kind, measurement in measurements.items()
        },
        "limits": {
            "per_kind_duration_seconds": MAX_KIND_SECONDS,
            "cache_bytes": MAX_CACHE_BYTES,
        },
        "cache": {"bytes": cache_bytes, "query_count": 1},
        "source_rows": {"query_count": 0, "mutated": False},
    }
    receipt["passed"] = bool(
        all(item.duration_seconds <= MAX_KIND_SECONDS for item in measurements.values())
        and cache_bytes <= MAX_CACHE_BYTES
        and not receipt["source_rows"]["mutated"]
    )

    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = RECEIPT_PATH.with_name(f"{RECEIPT_PATH.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(RECEIPT_PATH)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if not receipt["passed"]:
        raise RuntimeError("source visual extraction or cache budget exceeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
