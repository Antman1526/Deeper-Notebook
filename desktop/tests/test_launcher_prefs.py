"""v0.8.6 Item D — Unit tests for desktop/launcher_prefs.py.

Six test cases covering the full behaviour contract:
1. Missing file → empty dict.
2. Simple read.
3. Comments and blank lines preserved through a round-trip write.
4. None value removes a key.
5. Shell env wins on merge (env-wins rule).
6. Malformed line raises a clear ValueError.
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, content: str) -> Path:
    """Write content to launcher.env inside tmp_path and return the path."""
    p = tmp_path / ".open-notebook-plus" / "launcher.env"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_missing_file_returns_empty(tmp_path, monkeypatch):
    """Case 1: when the file doesn't exist, get_prefs() must return {}."""
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path",
                        lambda: tmp_path / ".open-notebook-plus" / "launcher.env")
    from desktop.launcher_prefs import get_prefs
    assert get_prefs() == {}


def test_simple_read(tmp_path, monkeypatch):
    """Case 2: present file with two whitelisted keys is read correctly."""
    _write(tmp_path, "ONP_CHAT_LLM_CTX=8192\nONP_CHAT_LLM_CTX_MAX=32768\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path",
                        lambda: tmp_path / ".open-notebook-plus" / "launcher.env")
    from desktop.launcher_prefs import get_prefs
    prefs = get_prefs()
    assert prefs == {"ONP_CHAT_LLM_CTX": "8192", "ONP_CHAT_LLM_CTX_MAX": "32768"}


def test_comments_and_blank_lines_preserved(tmp_path, monkeypatch):
    """Case 3: round-trip write preserves comment and blank lines."""
    original = (
        "# launcher.env — managed by Open Notebook Plus\n"
        "\n"
        "ONP_CHAT_LLM_CTX=4096\n"
    )
    path = _write(tmp_path, original)
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop import launcher_prefs as lp
    lp.update_prefs({"ONP_CHAT_LLM_CTX_MAX": "65536"})
    new_text = path.read_text()
    # Original comment and blank line preserved
    assert "# launcher.env" in new_text
    # Both old and new keys present
    assert "ONP_CHAT_LLM_CTX=4096" in new_text
    assert "ONP_CHAT_LLM_CTX_MAX=65536" in new_text


def test_none_value_removes_key(tmp_path, monkeypatch):
    """Case 4: update_prefs({KEY: None}) removes the key from the file."""
    path = _write(tmp_path, "ONP_CHAT_LLM_CTX=8192\nONP_CHAT_LLM_CTX_MAX=32768\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop import launcher_prefs as lp
    result = lp.update_prefs({"ONP_CHAT_LLM_CTX_MAX": None})
    assert "ONP_CHAT_LLM_CTX_MAX" not in result
    assert "ONP_CHAT_LLM_CTX_MAX" not in path.read_text()
    assert result == {"ONP_CHAT_LLM_CTX": "8192"}


def test_env_wins_on_merge(tmp_path, monkeypatch):
    """Case 5: merge_with_env must NOT overwrite keys already in env."""
    path = _write(tmp_path, "ONP_CHAT_LLM_CTX=99999\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import merge_with_env

    env = {"ONP_CHAT_LLM_CTX": "4096"}  # pre-existing shell env value
    merge_with_env(env)
    # Shell value must NOT have been overwritten
    assert env["ONP_CHAT_LLM_CTX"] == "4096"


def test_malformed_line_raises(tmp_path, monkeypatch):
    """Case 6: a non-comment, non-blank line without '=' raises ValueError."""
    path = _write(tmp_path, "ONP_CHAT_LLM_CTX=8192\nNOT_A_VALID_LINE\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import get_prefs
    with pytest.raises(ValueError, match="expected KEY=VALUE"):
        get_prefs()


def test_update_prefs_rejects_unknown_key(tmp_path, monkeypatch):
    """Bonus: non-whitelisted key raises ValueError (not silently stored)."""
    path = tmp_path / ".open-notebook-plus" / "launcher.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import update_prefs
    with pytest.raises(ValueError, match="not in whitelist"):
        update_prefs({"SECRET_KEY": "my-secret"})


def test_merge_with_env_fills_missing_keys(tmp_path, monkeypatch):
    """File value fills in when key is absent from env."""
    path = _write(tmp_path, "ONP_CHAT_LLM_CTX=16384\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import merge_with_env

    env: dict[str, str] = {}
    merge_with_env(env)
    assert env.get("ONP_CHAT_LLM_CTX") == "16384"
