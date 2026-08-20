"""v0.7.134 tests — pool warmup retry-with-backoff (Area for Review #6).

The other two items in v0.7.134 (#22 bundle-analyzer tree-shaking
verification, #27 memory-recall baseline) are documentation closures
in `docs/operator/observability.md`. Bundle-analyzer is tree-shaken
because `enabled: false` makes withBundleAnalyzer a passthrough; the
verification is a one-time manual `open .next/analyze/client.html`
check that doesn't belong in CI (see docs for the why).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


class TestWarmupRetry:
    """v0.7.134 — `_warmup_pool_acquire_with_retry` retries up to 3
    times with 0.5s/1.0s/2.0s backoff before re-raising the last
    exception. Previously a single transient failure aborted warmup
    and the first chat hit a cold pool — exactly what warmup was
    meant to prevent."""

    @pytest.mark.asyncio
    async def test_first_attempt_succeeds_no_retry(self):
        from api.main import _warmup_pool_acquire_with_retry

        fake_conn = object()
        acquire_mock = AsyncMock(return_value=fake_conn)
        with patch(
            "deeper_notebook.database.repository._acquire",
            acquire_mock,
        ):
            result = await _warmup_pool_acquire_with_retry(timeout_s=10.0)
        assert result is fake_conn
        assert acquire_mock.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        """First two attempts raise; third succeeds. Returns the
        connection from attempt 3 and the caller never sees the
        intermediate failures."""
        from api.main import _warmup_pool_acquire_with_retry

        fake_conn = object()
        call_count = [0]

        async def flaky_acquire():
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError(f"transient failure {call_count[0]}")
            return fake_conn

        with (
            patch(
                "deeper_notebook.database.repository._acquire",
                flaky_acquire,
            ),
            patch(
                "asyncio.sleep",
                AsyncMock(),  # don't actually wait
            ),
        ):
            result = await _warmup_pool_acquire_with_retry(timeout_s=10.0)
        assert result is fake_conn
        assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_all_attempts_fail_reraises_last_exception(self):
        """If every attempt raises, the LAST exception bubbles. The
        outer call site uses this to distinguish timeout-after-retries
        from generic-failure-after-retries in its logging."""
        from api.main import _warmup_pool_acquire_with_retry

        async def always_fails():
            raise RuntimeError("connection refused")

        with (
            patch(
                "deeper_notebook.database.repository._acquire",
                always_fails,
            ),
            patch(
                "asyncio.sleep",
                AsyncMock(),
            ),
        ):
            with pytest.raises(RuntimeError, match="connection refused"):
                await _warmup_pool_acquire_with_retry(timeout_s=10.0)

    @pytest.mark.asyncio
    async def test_timeout_reraises_after_all_retries(self):
        """Specifically: `asyncio.TimeoutError` should re-raise so
        the outer call site's `except asyncio.TimeoutError` branch
        can fire with the right log message.

        NOTE: we patch `_WARMUP_RETRY_DELAYS_S` to tiny values
        instead of `asyncio.sleep`. Patching `asyncio.sleep` globally
        breaks `asyncio.wait_for` internally (wait_for itself sleeps
        to enforce its timeout), which makes the test pass the
        TimeoutError without actually exercising the timeout path.
        """
        from api.main import _warmup_pool_acquire_with_retry

        async def hang_forever():
            await asyncio.sleep(60)

        with (
            patch(
                "deeper_notebook.database.repository._acquire",
                hang_forever,
            ),
            patch(
                "api.main._WARMUP_RETRY_DELAYS_S",
                (0.001, 0.001, 0.001),
            ),
        ):
            with pytest.raises(asyncio.TimeoutError):
                # Tiny per-attempt timeout so the test is fast
                await _warmup_pool_acquire_with_retry(timeout_s=0.05)

    @pytest.mark.asyncio
    async def test_backoff_delays_match_constant(self):
        """The delays between attempts should match
        _WARMUP_RETRY_DELAYS_S. We verify by patching asyncio.sleep
        and inspecting the call args."""
        from api.main import _WARMUP_RETRY_DELAYS_S, _warmup_pool_acquire_with_retry

        async def always_fails():
            raise RuntimeError("nope")

        sleep_mock = AsyncMock()
        with (
            patch(
                "deeper_notebook.database.repository._acquire",
                always_fails,
            ),
            patch(
                "asyncio.sleep",
                sleep_mock,
            ),
        ):
            with pytest.raises(RuntimeError):
                await _warmup_pool_acquire_with_retry(timeout_s=10.0)

        # Sleep should have been called between attempts 1→2 and 2→3,
        # but NOT after attempt 3 (which gives up).
        # That's len(_WARMUP_RETRY_DELAYS_S) - 1 = 2 sleep calls.
        assert sleep_mock.call_count == len(_WARMUP_RETRY_DELAYS_S) - 1

        # Each sleep arg should match the corresponding delay constant.
        called_delays = [c.args[0] for c in sleep_mock.call_args_list]
        assert called_delays == list(_WARMUP_RETRY_DELAYS_S[:-1])
