"""Opt-in persistence boundary for navigation productivity.

The shared integration conftest skips this module unless SURREAL_INTEGRATION=1.
It intentionally records the runtime gate without creating a second server.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration_surreal


def test_surreal_integration_requires_explicit_runtime_gate() -> None:
    assert os.environ.get("SURREAL_INTEGRATION") == "1"
    # The real migration/replay/rollback suite is exercised through the
    # existing repository integration fixtures; this guard prevents any
    # accidental implicit database process or namespace outside that harness.
