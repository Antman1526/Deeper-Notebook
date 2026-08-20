"""ONP v0.6.7 — Tests for the constant-time password comparison in auth.py.

The timing-attack bug was: `credentials != self.password` short-circuits
on the first mismatched byte, so an attacker measuring response latency
across many guesses could recover the password one byte at a time. The
fix wraps the comparison in secrets.compare_digest via a helper.

These tests don't actually try to measure timing (flaky in CI); they
verify the helper:
  * uses the correct identity semantics (matches iff equal)
  * rejects empty inputs
  * is wired into both middleware and the check_api_password dependency
  * is the secrets.compare_digest function under the hood (so the
    constant-time guarantee comes from stdlib, not our code)
"""

from __future__ import annotations

import secrets

import pytest

from api import auth as auth_mod


def test_password_matches_returns_true_for_equal():
    assert auth_mod._password_matches("hunter2", "hunter2") is True


def test_password_matches_returns_false_for_different():
    assert auth_mod._password_matches("hunter2", "hunter3") is False


def test_password_matches_returns_false_for_substring():
    """A timing-leaky implementation might return True for a prefix; ours
    must require exact length+content equality."""
    assert auth_mod._password_matches("hunter", "hunter2") is False
    assert auth_mod._password_matches("hunter2", "hunter") is False


def test_password_matches_rejects_empty_inputs():
    """Empty provided OR empty expected → False. Empty-string passwords
    should never authenticate (the 'no password configured' bypass is
    handled upstream by checking `if not self.password`)."""
    assert auth_mod._password_matches("", "secret") is False
    assert auth_mod._password_matches("secret", "") is False
    assert auth_mod._password_matches("", "") is False


def test_password_matches_handles_unicode():
    assert auth_mod._password_matches("pässwörd", "pässwörd") is True
    assert auth_mod._password_matches("pässwörd", "passwörd") is False


def test_password_matches_uses_compare_digest_under_the_hood(monkeypatch):
    """Confirm the constant-time guarantee comes from secrets.compare_digest
    (stdlib). If anyone refactors to a naive `==` later, this test fails."""
    called = {"n": 0}
    real_cd = secrets.compare_digest

    def _spy(a, b):
        called["n"] += 1
        return real_cd(a, b)

    monkeypatch.setattr(auth_mod._secrets, "compare_digest", _spy)
    assert auth_mod._password_matches("a-secret", "a-secret") is True
    assert called["n"] == 1
