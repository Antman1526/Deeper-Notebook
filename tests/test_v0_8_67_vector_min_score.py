"""v0.8.67 (audit A1) — vector_search relevance floor.

Default raised 0.2 → 0.3 (matches the memory layer's _MIN_SCORE; 0.0-0.3 is
"unrelated"), env-tunable via DEEPER_NOTEBOOK_VECTOR_MIN_SCORE. An explicit caller value is
honored as-is; None resolves to the env/default.
"""

from __future__ import annotations

import asyncio

import pytest

from deeper_notebook.domain import notebook as nb


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


@pytest.mark.parametrize(
    "val,expected",
    [
        (None, 0.3),
        ("", 0.3),
        ("0.5", 0.5),
        ("0", 0.0),
        ("1", 1.0),
        ("garbage", 0.3),
        ("1.5", 0.3),
        ("-0.1", 0.3),
    ],
)
def test_vector_min_score_env(monkeypatch, val, expected):
    if val is None:
        monkeypatch.delenv("DEEPER_NOTEBOOK_VECTOR_MIN_SCORE", raising=False)
    else:
        monkeypatch.setenv("DEEPER_NOTEBOOK_VECTOR_MIN_SCORE", val)
    assert nb._vector_min_score() == expected


def _patch_search(monkeypatch):
    """Capture the minimum_score that reaches repo_query."""
    captured = {}

    async def _fake_embed(_kw):
        return [0.0] * 8

    async def _fake_repo_query(sql, vars=None):
        captured["vars"] = vars or {}
        return []

    import deeper_notebook.utils.embedding as emb

    monkeypatch.setattr(emb, "generate_embedding", _fake_embed)
    monkeypatch.setattr(nb, "repo_query", _fake_repo_query)
    return captured


def test_vector_search_none_uses_default(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_VECTOR_MIN_SCORE", raising=False)
    captured = _patch_search(monkeypatch)
    _run(nb.vector_search("hello", 10))
    assert captured["vars"]["minimum_score"] == 0.3


def test_vector_search_env_override(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_VECTOR_MIN_SCORE", "0.45")
    captured = _patch_search(monkeypatch)
    _run(nb.vector_search("hello", 10))
    assert captured["vars"]["minimum_score"] == 0.45


def test_vector_search_explicit_value_honored(monkeypatch):
    monkeypatch.setenv(
        "DEEPER_NOTEBOOK_VECTOR_MIN_SCORE", "0.45"
    )  # ignored when caller passes one
    captured = _patch_search(monkeypatch)
    _run(nb.vector_search("hello", 10, minimum_score=0.1))
    assert captured["vars"]["minimum_score"] == 0.1
