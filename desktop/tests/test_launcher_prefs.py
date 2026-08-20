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
from pathlib import Path

import pytest

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
    monkeypatch.setattr(
        "desktop.launcher_prefs._prefs_path",
        lambda: tmp_path / ".open-notebook-plus" / "launcher.env",
    )
    from desktop.launcher_prefs import get_prefs

    assert get_prefs() == {}


def test_simple_read(tmp_path, monkeypatch):
    """Case 2: present file with two whitelisted keys is read correctly."""
    _write(
        tmp_path,
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192\nDEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX=32768\n",
    )
    monkeypatch.setattr(
        "desktop.launcher_prefs._prefs_path",
        lambda: tmp_path / ".open-notebook-plus" / "launcher.env",
    )
    from desktop.launcher_prefs import get_prefs

    prefs = get_prefs()
    assert prefs == {
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX": "8192",
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX": "32768",
    }


def test_comments_and_blank_lines_preserved(tmp_path, monkeypatch):
    """Case 3: round-trip write preserves comment and blank lines."""
    original = (
        "# launcher.env — managed by Open Notebook Plus\n"
        "\n"
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX=4096\n"
    )
    path = _write(tmp_path, original)
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop import launcher_prefs as lp

    lp.update_prefs({"DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX": "65536"})
    new_text = path.read_text()
    # Original comment and blank line preserved
    assert "# launcher.env" in new_text
    # Existing legacy keys are accepted, then written back canonically.
    assert "DEEPER_NOTEBOOK_CHAT_LLM_CTX=4096" in new_text
    assert "DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX=65536" in new_text


def test_none_value_removes_key(tmp_path, monkeypatch):
    """Case 4: update_prefs({KEY: None}) removes the key from the file."""
    path = _write(
        tmp_path,
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192\nDEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX=32768\n",
    )
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop import launcher_prefs as lp

    result = lp.update_prefs({"DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX": None})
    assert "DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX" not in result
    assert "DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX" not in path.read_text()
    assert result == {"DEEPER_NOTEBOOK_CHAT_LLM_CTX": "8192"}


def test_env_wins_on_merge(tmp_path, monkeypatch):
    """Case 5: merge_with_env must NOT overwrite keys already in env."""
    path = _write(tmp_path, "DEEPER_NOTEBOOK_CHAT_LLM_CTX=99999\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import merge_with_env

    env = {"DEEPER_NOTEBOOK_CHAT_LLM_CTX": "4096"}  # pre-existing shell env value
    merge_with_env(env)
    # Shell value must NOT have been overwritten
    assert env["DEEPER_NOTEBOOK_CHAT_LLM_CTX"] == "4096"


def test_malformed_line_raises(tmp_path, monkeypatch):
    """Case 6: a non-comment, non-blank line without '=' raises ValueError."""
    path = _write(tmp_path, "DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192\nNOT_A_VALID_LINE\n")
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
    path = _write(tmp_path, "DEEPER_NOTEBOOK_CHAT_LLM_CTX=16384\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import merge_with_env

    env: dict[str, str] = {}
    merge_with_env(env)
    assert env.get("DEEPER_NOTEBOOK_CHAT_LLM_CTX") == "16384"


# ---------------------------------------------------------------------------
# v0.8.8 audit fixes — whitelist enforcement on READ paths + malformed
# file logging.
# ---------------------------------------------------------------------------


def test_get_prefs_filters_non_whitelist_keys(tmp_path, monkeypatch):
    """v0.8.8 — pre-fix, get_prefs returned ALL keys from launcher.env
    including non-whitelisted ones (from pre-whitelist history, manual
    edits, or a removed-from-whitelist release). That leaked them
    through to the API's GET /api/launcher-prefs response. Fix:
    get_prefs filters to ALLOWED_KEYS as defense-in-depth, matching
    the docstring promise of a 'strict whitelist'."""
    path = _write(
        tmp_path,
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX=16384\n"
        "MY_SECRET=should-not-leak\n"
        "DEEPER_NOTEBOOK_LOCAL_N_CTX=32768\n",
    )
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import get_prefs

    result = get_prefs()
    assert "DEEPER_NOTEBOOK_CHAT_LLM_CTX" in result
    assert "DEEPER_NOTEBOOK_LOCAL_N_CTX" in result
    assert "MY_SECRET" not in result, (
        "v0.8.8: non-whitelist keys must be filtered out of get_prefs() — "
        "otherwise they leak through the API endpoint"
    )


def test_merge_with_env_skips_non_whitelist_keys(tmp_path, monkeypatch):
    """v0.8.8 — pre-fix, merge_with_env wrote ALL file keys into the
    env dict, so a file with MY_SECRET=foo set os.environ['MY_SECRET']
    at launcher startup. Second-line defense matching get_prefs."""
    path = _write(
        tmp_path,
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192\nMY_SECRET=should-not-leak\n",
    )
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop.launcher_prefs import merge_with_env

    env: dict[str, str] = {}
    merge_with_env(env)
    assert env.get("DEEPER_NOTEBOOK_CHAT_LLM_CTX") == "8192"
    assert "MY_SECRET" not in env, (
        "v0.8.8: non-whitelist keys must NOT be injected into env — "
        "otherwise a hand-edited launcher.env can pollute os.environ"
    )


def test_merge_with_env_logs_warning_on_malformed_file(
    tmp_path,
    monkeypatch,
    caplog,
):
    """v0.8.8 — pre-fix, merge_with_env silently swallowed ValueError
    when the file had a malformed line. Operator edited one line wrong
    → ALL their prefs reverted with no indication. Fix: log a warning
    to launcher.log with the parse error and a hint about how to
    recover. Still non-fatal so a misconfigured file doesn't block
    startup."""
    path = _write(
        tmp_path,
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192\n"
        "this is not a valid line\n"  # missing '='
        "DEEPER_NOTEBOOK_LOCAL_N_CTX=32768\n",
    )
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    import logging

    from desktop.launcher_prefs import merge_with_env

    env: dict[str, str] = {}
    with caplog.at_level(logging.WARNING, logger="desktop.launcher_prefs"):
        merge_with_env(env)

    # Env must be unchanged (non-fatal) — but a warning must surface
    # so operators can find the broken line.
    assert env == {}, "merge_with_env on malformed file must not partially apply"
    assert any(
        "launcher.env could not be parsed" in rec.message for rec in caplog.records
    ), (
        "v0.8.8: malformed launcher.env must log a WARNING so operators "
        "see they have a broken config; pre-v0.8.8 was silent"
    )


def test_update_prefs_writes_only_canonical_winners(tmp_path, monkeypatch):
    """A mixed legacy/canonical file is rewritten without duplicate aliases."""
    path = _write(
        tmp_path,
        "DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH=/canonical/model.gguf\n"
        "ONP_LOCAL_DRAFT_MODEL_PATH=/legacy/model.gguf\n"
        "DN_CHAT_LLM_CTX=32768\n"
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX=8192\n",
    )
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop import launcher_prefs as lp

    result = lp.update_prefs({})
    text = path.read_text(encoding="utf-8")

    assert result == {
        "DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH": "/canonical/model.gguf",
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX": "8192",
    }
    assert "ONP_LOCAL_DRAFT_MODEL_PATH=" not in text
    assert "DN_CHAT_LLM_CTX=" not in text


def test_legacy_launcher_pref_remains_accepted_and_is_canonicalized(
    tmp_path,
    monkeypatch,
):
    path = _write(tmp_path, "ONP_CHAT_LLM_CTX_MAX=65536\n")
    monkeypatch.setattr("desktop.launcher_prefs._prefs_path", lambda: path)
    from desktop import launcher_prefs as lp

    result = lp.update_prefs({})

    assert result == {"DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX": "65536"}
    assert path.read_text(encoding="utf-8") == (
        "DEEPER_NOTEBOOK_CHAT_LLM_CTX_MAX=65536\n"
    )
