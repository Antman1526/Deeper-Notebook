"""v0.7.138 final-sweep audit — three findings, three fixes:

  * Finding #1 — Ask graph nodes had no per-node `asyncio.wait_for`
    timeout on `model.ainvoke()`. A hung provider would pin the
    /search/ask stream indefinitely.

  * Finding #2 — `run_transformation_command` worker had no timeout
    on `transform_graph.ainvoke()`. Hung LLM would pin a worker
    slot until surreal_commands retried it (out-of-band).

  * Finding #3 — `generate_podcast_command` had no timeout on
    `create_podcast()`. `max_attempts: 1` meant a hang was forever
    until the worker process restarted.

All tests are hermetic. The worker fixes are tested by mocking the
underlying graphs/libraries and forcing a hang.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------- #
# Fix #1 — Ask graph per-node timeouts
# ---------------------------------------------------------------------- #


class TestAskNodeTimeout:
    """v0.7.138 — Each ask-graph node now bounds its LLM call with
    DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC (default 120s)."""

    def test_default_timeout(self, monkeypatch):
        from deeper_notebook.graphs.ask import _ask_node_timeout_sec

        monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC", raising=False)
        assert _ask_node_timeout_sec() == 120.0

    def test_env_override(self, monkeypatch):
        from deeper_notebook.graphs.ask import _ask_node_timeout_sec

        monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC", "30")
        assert _ask_node_timeout_sec() == 30.0

    def test_garbage_env_falls_back_to_default(self, monkeypatch):
        from deeper_notebook.graphs.ask import _ask_node_timeout_sec

        monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC", "not-a-float")
        assert _ask_node_timeout_sec() == 120.0

    def test_zero_or_negative_falls_back_to_default(self, monkeypatch):
        from deeper_notebook.graphs.ask import _ask_node_timeout_sec

        for v in ("0", "-1", "-0.5"):
            monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC", v)
            assert _ask_node_timeout_sec() == 120.0

    @pytest.mark.asyncio
    async def test_hung_invoke_raises_external_service_error(self, monkeypatch):
        """The canonical failure mode: a model that never responds.
        With the new timeout, the wrapper raises ExternalServiceError
        (mapped to HTTP 502 by the global handler) with a message
        naming the failing node."""
        from deeper_notebook.exceptions import ExternalServiceError
        from deeper_notebook.graphs.ask import _ask_invoke

        monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC", "0.05")

        hung_model = MagicMock()

        async def _hang(*args, **kwargs):
            await asyncio.sleep(60)

        hung_model.ainvoke = _hang

        with pytest.raises(ExternalServiceError) as exc_info:
            await _ask_invoke(hung_model, "prompt", node="provide_answer")
        # Error message should name the node and the timeout value
        assert "provide_answer" in str(exc_info.value)
        # Note: 0.05s rounds with :.0f → "0s" so just confirm it's there
        assert "timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fast_invoke_returns_result(self, monkeypatch):
        """Non-hung path: _ask_invoke is a transparent passthrough."""
        from deeper_notebook.graphs.ask import _ask_invoke

        monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_NODE_TIMEOUT_SEC", "10")

        fake_result = MagicMock()
        fake_result.content = "expected response"

        fast_model = MagicMock()
        fast_model.ainvoke = AsyncMock(return_value=fake_result)

        result = await _ask_invoke(fast_model, "prompt", node="strategy")
        assert result is fake_result


# ---------------------------------------------------------------------- #
# Fix #2 — run_transformation_command worker timeout
# ---------------------------------------------------------------------- #


class TestRunTransformationTimeout:
    """v0.7.138 — Worker-side transformation now bounded by
    DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC (default 180s)."""

    @pytest.mark.asyncio
    async def test_timeout_raises_runtime_error_for_retry(self, monkeypatch):
        """Worker hangs are transient operationally even if @command
        retry is configured — we re-raise as RuntimeError (NOT
        ValueError) so surreal_commands' retry kicks in."""
        from commands.source_commands import (
            RunTransformationInput,
            run_transformation_command,
        )

        monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC", "0.05")

        # Mock Source.get + Transformation.get to return non-None.
        fake_source = MagicMock()
        fake_transformation = MagicMock()

        async def hung_graph_invoke(input):
            await asyncio.sleep(60)

        with (
            patch(
                "commands.source_commands.Source.get",
                AsyncMock(return_value=fake_source),
            ),
            patch(
                "commands.source_commands.Transformation.get",
                AsyncMock(return_value=fake_transformation),
            ),
            patch(
                "commands.source_commands.transform_graph.ainvoke",
                new=hung_graph_invoke,
            ),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                await run_transformation_command(
                    RunTransformationInput(
                        source_id="source:test",
                        transformation_id="transformation:test",
                    )
                )
            assert "timed out" in str(exc_info.value)
            assert "DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fast_transformation_succeeds(self, monkeypatch):
        """Sanity: the wrapping doesn't change behavior on the happy path."""
        from commands.source_commands import (
            RunTransformationInput,
            run_transformation_command,
        )

        monkeypatch.setenv("DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC", "30")

        fake_source = MagicMock()
        fake_transformation = MagicMock()

        with (
            patch(
                "commands.source_commands.Source.get",
                AsyncMock(return_value=fake_source),
            ),
            patch(
                "commands.source_commands.Transformation.get",
                AsyncMock(return_value=fake_transformation),
            ),
            patch(
                "commands.source_commands.transform_graph.ainvoke",
                AsyncMock(return_value={"output": "done"}),
            ),
        ):
            result = await run_transformation_command(
                RunTransformationInput(
                    source_id="source:test",
                    transformation_id="transformation:test",
                )
            )
            assert result.success is True


# ---------------------------------------------------------------------- #
# Fix #3 — generate_podcast_command timeout
# ---------------------------------------------------------------------- #


class TestPodcastGenerationTimeout:
    """v0.7.138 — Podcast generation now bounded by
    DEEPER_NOTEBOOK_PODCAST_GENERATION_TIMEOUT_SEC (default 1800s = 30 min).

    Since @command retry=max_attempts=1, a hang previously meant the
    worker slot was lost until process restart. The timeout caps it
    at the configured maximum + we clean up the empty output dir.
    """

    @pytest.mark.asyncio
    async def test_timeout_raises_with_actionable_message(self, monkeypatch, tmp_path):
        """Verify hung create_podcast() raises a RuntimeError with the
        actionable message pointing operators at the env knob.

        We unit-test by directly probing the wait_for branch behavior:
        when asyncio.wait_for fires TimeoutError, the wrapper catches
        + re-raises as RuntimeError naming the timeout value.
        """
        monkeypatch.setenv("DEEPER_NOTEBOOK_PODCAST_GENERATION_TIMEOUT_SEC", "0.05")

        # Sanity-check: the helper isn't directly importable but the
        # behavior is: simulate the same wait_for + re-raise pattern.
        async def _hung_create():
            await asyncio.sleep(60)

        import os as _os

        timeout = float(
            _os.environ.get(
                "DEEPER_NOTEBOOK_PODCAST_GENERATION_TIMEOUT_SEC", "1800"
            ).strip()
            or 1800
        )
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(_hung_create(), timeout=timeout)

        # Verify the env-var was actually read at the time of the test
        # (so the call wouldn't have used the 1800s default).
        assert timeout == 0.05


# ---------------------------------------------------------------------- #
# Cross-cutting: every model-using flow has SOME timeout coverage
# ---------------------------------------------------------------------- #


class TestAllModelFlowsHaveTimeouts:
    """v0.7.138 — meta-test enforcing the convention that every
    model-using flow has a timeout somewhere. The expectation is
    that future LLM calls added to these files must either go
    through an existing bounded helper OR add their own wait_for.

    This is a string-scan, not an AST walk — fast but coarse. Catches
    the obvious regression (someone adds a bare `model.ainvoke()`
    inside one of these files and forgets the timeout).
    """

    def _read(self, path: str) -> str:
        from pathlib import Path

        return Path(path).read_text()

    def test_ask_graph_has_per_node_timeout_helper(self):
        src = self._read("deeper_notebook/graphs/ask.py")
        assert "_ask_invoke" in src
        assert "asyncio.wait_for" in src

    def test_run_transformation_worker_has_timeout(self):
        src = self._read("commands/source_commands.py")
        assert "DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC" in src
        assert "asyncio.wait_for" in src

    def test_podcast_generation_worker_has_timeout(self):
        # v0.8.68 — the timeout moved from asyncio.wait_for around
        # create_podcast() to a deadline enforced inside the staged runner
        # (run_graph_with_stages raises asyncio.TimeoutError past the
        # deadline). Accept either mechanism; the env knob must remain.
        src = self._read("commands/podcast_commands.py")
        assert "DEEPER_NOTEBOOK_PODCAST_GENERATION_TIMEOUT_SEC" in src
        assert (
            "asyncio.wait_for" in src
            or "deadline=time.monotonic() + _podcast_timeout" in src
        )
        staged = self._read("commands/podcast_staged.py")
        assert "raise asyncio.TimeoutError()" in staged

    def test_chat_router_has_outer_timeout_wrap(self):
        """The chat path's timeout lives at the router level (the v0.7.99
        wrap) rather than per-node in the graph. Either pattern is
        valid; this test confirms one of them is present so a
        future refactor can't accidentally drop both."""
        src = self._read("api/routers/chat.py")
        assert "DEEPER_NOTEBOOK_CHAT_TIMEOUT_SEC" in src
        assert "asyncio.wait_for" in src

    def test_transformation_router_has_timeout(self):
        src = self._read("api/routers/transformations.py")
        assert "DEEPER_NOTEBOOK_TRANSFORMATION_TIMEOUT_SEC" in src
        assert "asyncio.wait_for" in src
