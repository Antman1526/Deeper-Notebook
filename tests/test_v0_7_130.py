"""v0.7.130 regression tests covering:
  * Studio observability counters (record_studio_* helpers + increment paths)
  * Podcasts pagination (X-Total-Count header + slice semantics)
  * Settings observability endpoint (env-driven read-only view)
  * Settings PUT after removal of redundant cast()/dup imports

Hermetic — no SurrealDB, no surreal-commands worker, no external services.
The DB-touching tests stub the relevant domain helpers via monkeypatch
or fastapi.testclient with mocked dependencies, mirroring the existing
tests/test_*.py patterns.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------- #
# Studio observability counters
# ---------------------------------------------------------------------- #


def _counter_value(counter, **labels) -> float:
    """Read the current value of a Prometheus Counter. For labeled
    counters pass label kwargs; for unlabeled use no kwargs.

    The prometheus-client library doesn't expose a stable public API
    for reading values — `.collect()[0].samples` is the supported
    surface. We grab the `_total` sample which is the cumulative count.
    """
    samples = list(counter.collect())[0].samples
    for s in samples:
        if not s.name.endswith("_total"):
            continue
        if labels and s.labels != labels:
            continue
        if not labels and s.labels:
            continue
        return s.value
    return 0.0


class TestStudioMetrics:
    """v0.7.130 — Prometheus counter helpers added in api/metrics.py."""

    def test_record_studio_generation_increments_with_labels(self):
        from api.metrics import (
            record_studio_generation,
            studio_generations_total,
        )

        before = _counter_value(
            studio_generations_total, mode="notebook", outcome="success"
        )
        record_studio_generation("notebook", "success")
        after = _counter_value(
            studio_generations_total, mode="notebook", outcome="success"
        )
        assert after == before + 1

    def test_record_studio_generation_different_labels_independent(self):
        from api.metrics import (
            record_studio_generation,
            studio_generations_total,
        )

        before_success = _counter_value(
            studio_generations_total, mode="both", outcome="success"
        )
        before_failed = _counter_value(
            studio_generations_total, mode="both", outcome="failed"
        )
        record_studio_generation("both", "failed")
        assert (
            _counter_value(studio_generations_total, mode="both", outcome="success")
            == before_success
        )
        assert (
            _counter_value(studio_generations_total, mode="both", outcome="failed")
            == before_failed + 1
        )

    def test_record_studio_outline_parse_failure_reasons(self):
        from api.metrics import (
            record_studio_outline_parse_failure,
            studio_outline_parse_failures_total,
        )

        before_json = _counter_value(
            studio_outline_parse_failures_total, reason="json_decode"
        )
        before_val = _counter_value(
            studio_outline_parse_failures_total, reason="validation"
        )
        record_studio_outline_parse_failure("json_decode")
        record_studio_outline_parse_failure("validation")
        record_studio_outline_parse_failure("json_decode")
        assert (
            _counter_value(studio_outline_parse_failures_total, reason="json_decode")
            == before_json + 2
        )
        assert (
            _counter_value(studio_outline_parse_failures_total, reason="validation")
            == before_val + 1
        )

    def test_record_studio_single_note_fallback_unlabeled(self):
        from api.metrics import (
            record_studio_single_note_fallback,
            studio_single_note_fallbacks_total,
        )

        before = _counter_value(studio_single_note_fallbacks_total)
        record_studio_single_note_fallback()
        record_studio_single_note_fallback()
        after = _counter_value(studio_single_note_fallbacks_total)
        assert after == before + 2

    def test_metrics_helpers_surface_via_render(self):
        """Sanity: the new metrics actually show up in /metrics output."""
        from api.metrics import (
            record_studio_generation,
            record_studio_outline_parse_failure,
            record_studio_single_note_fallback,
            render_prometheus,
        )

        record_studio_generation("notebook", "success")
        record_studio_outline_parse_failure("json_decode")
        record_studio_single_note_fallback()
        body, content_type = render_prometheus()
        assert "text/plain" in content_type or "openmetrics" in content_type
        text = body.decode("utf-8")
        assert "onp_studio_generations_total" in text
        assert "onp_studio_outline_parse_failures_total" in text
        assert "onp_studio_single_note_fallbacks_total" in text


# ---------------------------------------------------------------------- #
# Podcasts pagination — header + slice semantics
# ---------------------------------------------------------------------- #


class _FakeEpisode:
    """Minimal Pydantic-free stand-in for a Podcast Episode row. The
    real one has more fields; only the attributes touched by the
    list_podcast_episodes handler need to be present here."""

    def __init__(self, idx: int, with_audio: bool = True):
        self.id = f"podcast_episode:fake{idx}"
        self.name = f"Episode {idx}"
        # PodcastEpisodeResponse declares episode_profile/speaker_profile
        # as `dict` (not str) and transcript/outline as Optional[dict].
        self.episode_profile = {"name": "default-pod"}
        self.speaker_profile = {"name": "default-speaker"}
        self.briefing = ""
        self.audio_file = f"/tmp/fake-{idx}.mp3" if with_audio else None
        self.transcript = None
        self.outline = None
        self.created = "2026-05-19T03:00:00Z"
        self.command = f"command:fake{idx}" if with_audio else None
        self.selection_summary = {
            "version": 1,
            "total_count": 2,
            "included_count": 2,
            "authority_counts": {"external_read_only": 2},
        }
        self.selection_fingerprint = "a" * 64
        self.editorial_brief = {
            "central_question": "What changes after the research is connected?",
            "audience": "Research team",
            "outline": ["Context", "Decision"],
        }
        self.model_plan_receipts = [
            {
                "version": 1,
                "role": "podcast_outline",
                "outcome": "ready",
                "reason": "automatic selected the standard verified local candidate after all route gates.",
            }
        ]

    async def get_job_detail(self):
        return {"status": "completed", "error_message": None}


class TestPodcastsPagination:
    """v0.7.130 — GET /podcasts/episodes accepts offset+limit and
    returns total count via X-Total-Count header."""

    def _make_client(self, episode_count: int = 75):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routers.podcasts import router

        episodes = [_FakeEpisode(i) for i in range(episode_count)]

        # Patch PodcastService.list_episodes + the audio-path resolver
        # to keep this fully hermetic (no filesystem, no SurrealDB).
        patcher_list = patch(
            "api.routers.podcasts.PodcastService.list_episodes",
            AsyncMock(return_value=episodes),
        )
        patcher_audio = patch(
            "api.routers.podcasts._resolve_audio_path",
            return_value=None,  # makes audio_url come back as None — fine
        )
        patcher_list.start()
        patcher_audio.start()

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        return client, [patcher_list, patcher_audio]

    def test_default_pagination_returns_50(self):
        client, stoppers = self._make_client(episode_count=75)
        try:
            r = client.get("/podcasts/episodes")
            assert r.status_code == 200
            data = r.json()
            assert len(data) == 50, "default limit should be 50"
            assert r.headers["X-Total-Count"] == "75"
            assert r.headers["X-Offset"] == "0"
            assert r.headers["X-Limit"] == "50"
        finally:
            for p in stoppers:
                p.stop()

    def test_episode_list_returns_only_the_redacted_studio_receipt(self):
        client, stoppers = self._make_client(episode_count=1)
        try:
            response = client.get("/podcasts/episodes")

            assert response.status_code == 200
            episode = response.json()[0]
            assert episode["selection_summary"]["authority_counts"] == {
                "external_read_only": 2
            }
            assert episode["selection_fingerprint"] == "a" * 64
            assert episode["editorial_brief"]["audience"] == "Research team"
            assert episode["model_plan_receipts"][0]["role"] == "podcast_outline"
            assert "content" not in str(episode)
            assert "relative_locator" not in str(episode)
            assert "model_id" not in str(episode)
        finally:
            for patcher in stoppers:
                patcher.stop()

    def test_offset_skips_first_n(self):
        client, stoppers = self._make_client(episode_count=75)
        try:
            r = client.get("/podcasts/episodes?offset=10&limit=5")
            assert r.status_code == 200
            data = r.json()
            assert len(data) == 5
            # Episode names should match Episode 10-14
            assert data[0]["name"] == "Episode 10"
            assert data[-1]["name"] == "Episode 14"
            assert r.headers["X-Total-Count"] == "75"
            assert r.headers["X-Offset"] == "10"
            assert r.headers["X-Limit"] == "5"
        finally:
            for p in stoppers:
                p.stop()

    def test_limit_cap_at_200(self):
        client, stoppers = self._make_client(episode_count=10)
        try:
            # 201 must be rejected by FastAPI Query(le=200) validation
            r = client.get("/podcasts/episodes?limit=201")
            assert r.status_code == 422
        finally:
            for p in stoppers:
                p.stop()

    def test_negative_offset_rejected(self):
        client, stoppers = self._make_client(episode_count=10)
        try:
            r = client.get("/podcasts/episodes?offset=-1")
            assert r.status_code == 422
        finally:
            for p in stoppers:
                p.stop()

    def test_offset_beyond_total_returns_empty(self):
        client, stoppers = self._make_client(episode_count=5)
        try:
            r = client.get("/podcasts/episodes?offset=100&limit=10")
            assert r.status_code == 200
            assert r.json() == []
            assert r.headers["X-Total-Count"] == "5"
        finally:
            for p in stoppers:
                p.stop()


# ---------------------------------------------------------------------- #
# Settings observability endpoint
# ---------------------------------------------------------------------- #


class TestSettingsObservability:
    """v0.7.130 — GET /settings/observability returns env-derived
    read-only view of DEEPER_NOTEBOOK_* observability/security knobs."""

    def _make_client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routers.settings import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_defaults_when_no_env_set(self, monkeypatch):
        # Wipe all DEEPER_NOTEBOOK_* env that could affect this test
        for k in (
            "DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS",
            "DEEPER_NOTEBOOK_ENCRYPTION_KDF",
            "DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD",
            "DEEPER_NOTEBOOK_CHECKPOINT_PRUNE_INTERVAL_HOURS",
            "DEEPER_NOTEBOOK_DB_POOL_SIZE",
            "DEEPER_NOTEBOOK_DB_POOL_DISABLED",
        ):
            monkeypatch.delenv(k, raising=False)

        client = self._make_client()
        r = client.get("/settings/observability")
        assert r.status_code == 200
        data = r.json()
        assert data["slow_query_log_ms"] is None
        assert data["encryption_kdf"] == "raw"
        assert data["checkpoint_keep_per_thread"] == 50
        assert data["checkpoint_prune_interval_hours"] == 24
        assert data["db_pool_size"] == 4
        assert data["db_pool_disabled"] is False
        assert data["metrics_endpoint_path"] == "/metrics"

    def test_env_values_round_trip(self, monkeypatch):
        monkeypatch.setenv("DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS", "750")
        monkeypatch.setenv("DEEPER_NOTEBOOK_ENCRYPTION_KDF", "pbkdf2")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD", "100")
        monkeypatch.setenv("DEEPER_NOTEBOOK_CHECKPOINT_PRUNE_INTERVAL_HOURS", "6")
        monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "16")
        monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_DISABLED", "true")

        client = self._make_client()
        r = client.get("/settings/observability")
        assert r.status_code == 200
        data = r.json()
        assert data["slow_query_log_ms"] == 750
        assert data["encryption_kdf"] == "pbkdf2"
        assert data["checkpoint_keep_per_thread"] == 100
        assert data["checkpoint_prune_interval_hours"] == 6
        assert data["db_pool_size"] == 16
        assert data["db_pool_disabled"] is True

    def test_garbage_int_env_falls_back_to_default(self, monkeypatch):
        """A typo in .env shouldn't crash the endpoint — the helper
        warns + returns the default. This is a defensive-coding
        regression test for `_env_int`."""
        monkeypatch.setenv("DEEPER_NOTEBOOK_CHECKPOINT_KEEP_PER_THREAD", "not-a-number")
        monkeypatch.setenv("DEEPER_NOTEBOOK_SLOW_QUERY_LOG_MS", "also-bad")

        client = self._make_client()
        r = client.get("/settings/observability")
        assert r.status_code == 200
        data = r.json()
        assert data["checkpoint_keep_per_thread"] == 50  # default kicks in
        assert data["slow_query_log_ms"] is None  # default for unparseable

    def test_bool_parsing_case_insensitive(self, monkeypatch):
        # Exhaustive matrix for the truthy set defined in _env_bool
        for truthy in ("1", "true", "TRUE", "True", "yes", "YES", "on", "ON"):
            monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_DISABLED", truthy)
            client = self._make_client()
            r = client.get("/settings/observability")
            assert r.json()["db_pool_disabled"] is True, f"{truthy!r} should be truthy"

        for falsy in ("0", "false", "no", "off", "garbage", ""):
            monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_DISABLED", falsy)
            client = self._make_client()
            r = client.get("/settings/observability")
            assert r.json()["db_pool_disabled"] is False, f"{falsy!r} should be falsy"


# ---------------------------------------------------------------------- #
# Settings PUT — sanity that the cast() removal didn't change behavior
# ---------------------------------------------------------------------- #


class TestSettingsUpdate:
    """v0.7.130 — removed redundant cast() calls + duplicate imports.
    Behavior must remain identical: PUT /settings still validates
    Literal[…] fields via Pydantic + still rejects bad values."""

    def _make_client(self, settings_instance):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routers.settings import router

        with patch(
            "api.routers.settings.ContentSettings.get_instance",
            AsyncMock(return_value=settings_instance),
        ):
            app = FastAPI()
            app.include_router(router)
            yield TestClient(app)

    def test_invalid_literal_rejected_by_pydantic(self, monkeypatch):
        """Pydantic on the SettingsUpdate model must reject a value
        that isn't in the Literal — proves the validation still
        happens at the request boundary, not somewhere we lost
        when removing cast()."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.routers.settings import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        # 'banana' is not in Literal["auto", "docling", "simple"]
        r = client.put(
            "/settings",
            json={"default_content_processing_engine_doc": "banana"},
        )
        assert r.status_code == 422
