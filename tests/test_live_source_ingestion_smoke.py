"""Unit pins for the opt-in live source-ingestion smoke script."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live_source_ingestion_smoke.py"
SPEC = importlib.util.spec_from_file_location("live_source_ingestion_smoke", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
sys.modules["live_source_ingestion_smoke"] = smoke
SPEC.loader.exec_module(smoke)


def test_build_api_url_handles_plain_api_and_prefixed_bases():
    assert (
        smoke.build_api_url("http://127.0.0.1:5055", "/sources")
        == "http://127.0.0.1:5055/api/sources"
    )
    assert (
        smoke.build_api_url("http://127.0.0.1:5055/api", "/sources")
        == "http://127.0.0.1:5055/api/sources"
    )
    assert (
        smoke.build_api_url("http://127.0.0.1:5055", "/api/sources")
        == "http://127.0.0.1:5055/api/sources"
    )


def test_source_readiness_requires_marker_text_embedding_and_quality():
    ready = {
        "full_text": "hello onp-smoke-123",
        "embedded": True,
        "extraction_quality": "ok",
    }
    assert smoke.source_is_ready(ready, "onp-smoke-123") is True

    assert smoke.source_is_ready({**ready, "full_text": "hello"}, "onp-smoke-123") is False
    assert smoke.source_is_ready({**ready, "embedded": False}, "onp-smoke-123") is False
    assert smoke.source_is_ready({**ready, "extraction_quality": "no_text"}, "onp-smoke-123") is False


def test_source_processing_statuses_are_conservative():
    for status in ("new", "queued", "running", "unknown"):
        assert smoke.source_is_processing(status) is True
    for status in ("completed", "failed", None):
        assert smoke.source_is_processing(status) is False
