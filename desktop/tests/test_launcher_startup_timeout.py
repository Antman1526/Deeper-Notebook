"""v0.8.67b — `_startup_timeout` env-tunable startup readiness timeout.

Regression for the EARLY-INIT FAILURE class: the first launch after an app
update re-extracts the runtime + rebuilds the venv, and that I/O delayed
SurrealDB's bind past the old hard 30 s `_wait_tcp` gate. Because SurrealDB is a
core service, the gate aborted the WHOLE supervisor → dead app / empty chatbot.
The fix makes the gate env-tunable with a raised default; these tests pin the
parsing/fallback contract so a bad override can never make the gate *tighter*
than the safe default by accident.
"""

from __future__ import annotations

import pytest

from deeper_notebook.environment import SETTINGS
from desktop.launcher import _startup_timeout


def test_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", raising=False)
    assert _startup_timeout("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", 90.0) == 90.0


def test_valid_override_is_honored(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", "150")
    assert _startup_timeout("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", 90.0) == 150.0


def test_whitespace_is_stripped(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_SIDECAR_TCP_TIMEOUT", "  45.5  ")
    assert _startup_timeout("DEEPER_NOTEBOOK_SIDECAR_TCP_TIMEOUT", 90.0) == 45.5


@pytest.mark.parametrize("bad", ["", "abc", "1e3x", "nan-ish", "  "])
def test_unparseable_falls_back_to_default(monkeypatch, bad):
    monkeypatch.setenv("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", bad)
    assert _startup_timeout("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", 90.0) == 90.0


@pytest.mark.parametrize("nonpos", ["0", "-1", "-30.0"])
def test_non_positive_falls_back_to_default(monkeypatch, nonpos):
    # A zero/negative ceiling would make _wait_tcp give up instantly — never
    # allow an override to be *more* fragile than the default.
    monkeypatch.setenv("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", nonpos)
    assert _startup_timeout("DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT", 90.0) == 90.0


def test_surreal_default_raised_above_old_30s(monkeypatch):
    # The historical hard gate was 30 s; the new default must be strictly more
    # generous so a post-update slow-but-alive SurrealDB start isn't aborted.
    canonical = "DEEPER_NOTEBOOK_SURREAL_TCP_TIMEOUT"
    for alias in SETTINGS[canonical].precedence:
        monkeypatch.delenv(alias, raising=False)

    assert _startup_timeout(canonical, 90.0) > 30.0
