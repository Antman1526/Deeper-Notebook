"""v0.7.139 tests covering:

* scripts/benchmark_models.py — probe shapes, JSON extraction,
  composite score math, report rendering. Hermetic via mocked
  httpx client (NO real API needed).

* ModelManager.get_model — improved error discrimination between
  "not found" (ConfigurationError, actionable) and "DB hiccup"
  (OpenNotebookError, transient).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------- #
# benchmark_models.py — score math + report rendering
# ---------------------------------------------------------------------- #


class TestComposite:
    def test_all_pass_fast_is_max_score(self):
        from scripts.benchmark_models import ModelReport, ProbeResult

        rep = ModelReport(
            model_id="m:1",
            model_name="m1",
            provider="p",
            model_type="language",
        )
        for probe in ("NOTEBOOK_CHAT", "STUDIO_OUTLINE", "PODCAST_TRANSCRIPT_TURN"):
            rep.results.append(
                ProbeResult(
                    probe=probe,
                    model_id="m:1",
                    model_name="m1",
                    provider="p",
                    success=True,
                    elapsed_s=0.3,
                )
            )
        # 100% pass + 100% latency = composite 100
        assert rep.composite_score == 100.0

    def test_all_fail_slow_is_min_score(self):
        from scripts.benchmark_models import ModelReport, ProbeResult

        rep = ModelReport(
            model_id="m:2",
            model_name="m2",
            provider="p",
            model_type="language",
        )
        for probe in ("NOTEBOOK_CHAT", "STUDIO_OUTLINE", "PODCAST_TRANSCRIPT_TURN"):
            rep.results.append(
                ProbeResult(
                    probe=probe,
                    model_id="m:2",
                    model_name="m2",
                    provider="p",
                    success=False,
                    elapsed_s=90.0,
                )
            )
        # 0% pass + 0% latency = composite 0
        assert rep.composite_score == 0.0

    def test_pass_dominates_over_latency(self):
        """A slow model that passes everything should outrank a fast
        model that fails everything."""
        from scripts.benchmark_models import ModelReport, ProbeResult

        slow_pass = ModelReport(
            model_id="m:3",
            model_name="m3",
            provider="p",
            model_type="language",
        )
        for probe in ("NOTEBOOK_CHAT", "STUDIO_OUTLINE", "PODCAST_TRANSCRIPT_TURN"):
            slow_pass.results.append(
                ProbeResult(
                    probe=probe,
                    model_id="m:3",
                    model_name="m3",
                    provider="p",
                    success=True,
                    elapsed_s=30.0,
                )
            )

        fast_fail = ModelReport(
            model_id="m:4",
            model_name="m4",
            provider="p",
            model_type="language",
        )
        for probe in ("NOTEBOOK_CHAT", "STUDIO_OUTLINE", "PODCAST_TRANSCRIPT_TURN"):
            fast_fail.results.append(
                ProbeResult(
                    probe=probe,
                    model_id="m:4",
                    model_name="m4",
                    provider="p",
                    success=False,
                    elapsed_s=0.2,
                )
            )
        assert slow_pass.composite_score > fast_fail.composite_score

    def test_partial_pass_ranks_between(self):
        """A model that passes 2/3 should rank above one that passes
        1/3 even with worse latency."""
        from scripts.benchmark_models import ModelReport, ProbeResult

        two_of_three = ModelReport(
            model_id="m:5",
            model_name="m5",
            provider="p",
            model_type="language",
        )
        two_of_three.results = [
            ProbeResult(
                probe="A",
                model_id="m:5",
                model_name="m5",
                provider="p",
                success=True,
                elapsed_s=10.0,
            ),
            ProbeResult(
                probe="B",
                model_id="m:5",
                model_name="m5",
                provider="p",
                success=True,
                elapsed_s=10.0,
            ),
            ProbeResult(
                probe="C",
                model_id="m:5",
                model_name="m5",
                provider="p",
                success=False,
                elapsed_s=10.0,
            ),
        ]
        one_of_three = ModelReport(
            model_id="m:6",
            model_name="m6",
            provider="p",
            model_type="language",
        )
        one_of_three.results = [
            ProbeResult(
                probe="A",
                model_id="m:6",
                model_name="m6",
                provider="p",
                success=True,
                elapsed_s=5.0,
            ),
            ProbeResult(
                probe="B",
                model_id="m:6",
                model_name="m6",
                provider="p",
                success=False,
                elapsed_s=5.0,
            ),
            ProbeResult(
                probe="C",
                model_id="m:6",
                model_name="m6",
                provider="p",
                success=False,
                elapsed_s=5.0,
            ),
        ]
        assert two_of_three.composite_score > one_of_three.composite_score


class TestJSONExtraction:
    """The STUDIO_OUTLINE probe needs to extract JSON even from models
    that wrap their output in code fences or add preamble. Real models
    do this often enough that lenient parsing is essential."""

    @pytest.mark.asyncio
    async def test_clean_json_passes(self):
        from scripts.benchmark_models import _run_studio_outline_probe

        clean = {"pages": [{"title": "Origin", "focus": "Hooke"}]}
        mock_client = self._make_mock_client(json.dumps(clean))
        res = await _run_studio_outline_probe(
            mock_client,
            {
                "id": "m:1",
                "name": "m1",
                "provider": "p",
            },
        )
        assert res.success, f"clean JSON should pass; error={res.error}"
        assert res.meta["json_shape_ok"] is True

    @pytest.mark.asyncio
    async def test_code_fence_wrapped_json_passes(self):
        from scripts.benchmark_models import _run_studio_outline_probe

        wrapped = (
            '```json\n{"pages": [{"title": "A"}, {"title": "B"}, {"title": "C"}]}\n```'
        )
        mock_client = self._make_mock_client(wrapped)
        res = await _run_studio_outline_probe(
            mock_client,
            {
                "id": "m:2",
                "name": "m2",
                "provider": "p",
            },
        )
        assert res.success, f"code-fenced JSON should pass; error={res.error}"
        assert res.meta["page_count"] == 3

    @pytest.mark.asyncio
    async def test_garbage_output_fails_with_parse_error(self):
        from scripts.benchmark_models import _run_studio_outline_probe

        mock_client = self._make_mock_client("here is your outline: just words")
        res = await _run_studio_outline_probe(
            mock_client,
            {
                "id": "m:3",
                "name": "m3",
                "provider": "p",
            },
        )
        assert not res.success
        assert "JSON parse failed" in res.error or "shape" in res.error

    @pytest.mark.asyncio
    async def test_json_with_wrong_shape_fails(self):
        from scripts.benchmark_models import _run_studio_outline_probe

        # Valid JSON, but no "pages" key
        mock_client = self._make_mock_client('{"sections": ["a", "b"]}')
        res = await _run_studio_outline_probe(
            mock_client,
            {
                "id": "m:4",
                "name": "m4",
                "provider": "p",
            },
        )
        assert not res.success
        assert "shape" in res.error.lower()

    def _make_mock_client(self, output: str):
        """Build a mock httpx.AsyncClient that returns `output` as the
        `output` field of the response body."""
        client = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"output": output}
        response.text = json.dumps({"output": output})
        client.post = AsyncMock(return_value=response)
        return client


class TestPodcastSpeakerDetection:
    """PODCAST_TRANSCRIPT_TURN passes only if the model produces BOTH
    ALICE and BOB speakers — otherwise it can't follow multi-speaker
    instructions and would fail in actual podcast generation."""

    @pytest.mark.asyncio
    async def test_both_speakers_passes(self):
        from scripts.benchmark_models import _run_podcast_turn_probe

        output = (
            "ALICE: Did you know plants convert sunlight to energy?\n"
            "BOB: Right, that's photosynthesis. Wild that the byproduct "
            "is the oxygen we breathe."
        )
        mock_client = self._make_mock_client(output)
        res = await _run_podcast_turn_probe(
            mock_client,
            {
                "id": "m:1",
                "name": "m1",
                "provider": "p",
            },
        )
        assert res.success
        assert res.meta["has_alice"] is True
        assert res.meta["has_bob"] is True

    @pytest.mark.asyncio
    async def test_only_one_speaker_fails(self):
        from scripts.benchmark_models import _run_podcast_turn_probe

        output = (
            "Photosynthesis is the process where plants convert sunlight "
            "into chemical energy. It happens in chloroplasts and releases "
            "oxygen as a side effect."
        )
        mock_client = self._make_mock_client(output)
        res = await _run_podcast_turn_probe(
            mock_client,
            {
                "id": "m:2",
                "name": "m2",
                "provider": "p",
            },
        )
        assert not res.success
        assert "ALICE" in res.error or "BOB" in res.error

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self):
        """Some local models lowercase speaker labels. The detection
        is case-insensitive so we don't reject those."""
        from scripts.benchmark_models import _run_podcast_turn_probe

        output = (
            "alice: hey did you hear about photosynthesis?\n"
            "bob: yeah, it's how plants make food. cool stuff."
        )
        mock_client = self._make_mock_client(output)
        res = await _run_podcast_turn_probe(
            mock_client,
            {
                "id": "m:3",
                "name": "m3",
                "provider": "p",
            },
        )
        assert res.success

    def _make_mock_client(self, output: str):
        client = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"output": output}
        client.post = AsyncMock(return_value=response)
        return client


class TestReportRendering:
    def test_renders_with_zero_models(self):
        from scripts.benchmark_models import _render_markdown

        md = _render_markdown([], total_wall_clock_s=0.0)
        # Must produce a usable header even if no models tested
        assert "Model Benchmark Report" in md
        assert "**Models tested**: 0" in md

    def test_renders_with_three_models(self):
        from scripts.benchmark_models import (
            ModelReport,
            ProbeResult,
            _render_markdown,
        )

        reps = []
        for i in range(3):
            r = ModelReport(
                model_id=f"m:{i}",
                model_name=f"m{i}",
                provider="prov",
                model_type="language",
            )
            for probe in ("NOTEBOOK_CHAT", "STUDIO_OUTLINE", "PODCAST_TRANSCRIPT_TURN"):
                r.results.append(
                    ProbeResult(
                        probe=probe,
                        model_id=r.model_id,
                        model_name=r.model_name,
                        provider=r.provider,
                        success=(i % 2 == 0),
                        elapsed_s=1.0 + i * 0.5,
                    )
                )
            reps.append(r)
        md = _render_markdown(reps, total_wall_clock_s=10.0)
        # Each model appears in the ranking
        assert "`m0`" in md
        assert "`m1`" in md
        assert "`m2`" in md
        # All three probe sections appear
        assert "NOTEBOOK_CHAT" in md
        assert "STUDIO_OUTLINE" in md
        assert "PODCAST_TRANSCRIPT_TURN" in md


# ---------------------------------------------------------------------- #
# ModelManager.get_model — improved error discrimination
# ---------------------------------------------------------------------- #


class TestGetModelErrorDiscrimination:
    """v0.7.139 — get_model now distinguishes:
    - model record doesn't exist in DB → ConfigurationError (actionable)
    - DB lookup raised unexpectedly       → OpenNotebookError (transient)
    - model has invalid `type` field      → ConfigurationError with hint
    """

    @pytest.mark.asyncio
    async def test_none_from_model_get_raises_configuration_error(self):
        """If Model.get returns None instead of raising, we still need
        to surface "not found" cleanly."""
        from deeper_notebook.ai.models import ModelManager
        from deeper_notebook.exceptions import ConfigurationError

        with patch(
            "deeper_notebook.ai.models.Model.get",
            AsyncMock(return_value=None),
        ):
            with pytest.raises(ConfigurationError, match="not found"):
                await ModelManager().get_model("model:doesnotexist")

    @pytest.mark.asyncio
    async def test_notfound_error_maps_to_configuration_error(self):
        from deeper_notebook.ai.models import ModelManager
        from deeper_notebook.exceptions import (
            ConfigurationError,
            NotFoundError,
        )

        with patch(
            "deeper_notebook.ai.models.Model.get",
            AsyncMock(side_effect=NotFoundError("model:foo")),
        ):
            with pytest.raises(ConfigurationError, match="not found"):
                await ModelManager().get_model("model:foo")

    @pytest.mark.asyncio
    async def test_unexpected_exception_maps_to_deeper_notebook_error(self):
        """A DB pool timeout / connection refused / generic exception
        from Model.get is operational, not configuration — must surface
        as OpenNotebookError so the user doesn't go re-creating
        perfectly-valid models."""
        from deeper_notebook.ai.models import ModelManager
        from deeper_notebook.exceptions import OpenNotebookError

        with patch(
            "deeper_notebook.ai.models.Model.get",
            AsyncMock(side_effect=RuntimeError("connection refused")),
        ):
            with pytest.raises(OpenNotebookError, match="connection refused"):
                await ModelManager().get_model("model:foo")

    @pytest.mark.asyncio
    async def test_typed_exception_passes_through(self):
        """OpenNotebookError-subclass exceptions from Model.get pass
        through verbatim — no double-wrapping."""
        from deeper_notebook.ai.models import ModelManager
        from deeper_notebook.exceptions import RateLimitError

        with patch(
            "deeper_notebook.ai.models.Model.get",
            AsyncMock(side_effect=RateLimitError("rate limited")),
        ):
            with pytest.raises(RateLimitError, match="rate limited"):
                await ModelManager().get_model("model:foo")

    @pytest.mark.asyncio
    async def test_invalid_type_field_includes_actionable_hint(self):
        """A model with type=None or unknown type should produce an
        error that names the model + tells the user where to fix it."""
        from deeper_notebook.ai.models import ModelManager
        from deeper_notebook.exceptions import ConfigurationError

        fake_model = MagicMock()
        fake_model.id = "model:weird"
        fake_model.name = "weirdo"
        fake_model.type = None

        with patch(
            "deeper_notebook.ai.models.Model.get",
            AsyncMock(return_value=fake_model),
        ):
            with pytest.raises(ConfigurationError) as exc_info:
                await ModelManager().get_model("model:weird")
        # Error must name the model + point to Settings → Models
        assert "weirdo" in str(exc_info.value)
        assert "Settings" in str(exc_info.value)


# ---------------------------------------------------------------------- #
# Cross-cutting: scripts/ dir is recognized as a runnable package
# ---------------------------------------------------------------------- #


def test_benchmark_models_is_executable():
    """The script must have a shebang + main-guard so `python scripts/
    benchmark_models.py` works."""
    src = Path("scripts/benchmark_models.py").read_text()
    assert src.startswith("#!"), "Missing shebang"
    assert 'if __name__ == "__main__"' in src


def test_makefile_has_benchmark_target():
    src = Path("Makefile").read_text()
    assert "benchmark-models:" in src
    assert "benchmark_models.py" in src
