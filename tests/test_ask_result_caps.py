"""v0.7.9 — regression tests for the Ask graph's per-result content cap.

`deeper_notebook.graphs.ask.provide_answer` used to pass `vector_search`
results verbatim into the prompt via `{{results}}`. Each result's
`matches` field is `array::flatten(content)` and can hold many chunks
from a hot source, so a single result was easily 10-30 KB and 10 of
them 100-300 KB — large enough to overflow a 16k-context local LLM
(the project's documented target after v0.7.8).

These tests pin the new `_truncate_ask_results` contract so a future
refactor can't silently reintroduce the unbounded payload.
"""

from __future__ import annotations

import pytest

from deeper_notebook.graphs import ask

# ---------------------------------------------------------------------------
# _truncate_ask_results — pure function tests
# ---------------------------------------------------------------------------


def _result(rid: str, matches: list[str] | str | None) -> dict:
    """Build a vector_search-shaped result dict for testing."""
    base = {
        "id": rid,
        "parent_id": rid,
        "title": "T",
        "similarity": 0.5,
    }
    if matches is not None:
        base["matches"] = matches
    return base


def test_truncate_caps_results_to_default_max(monkeypatch):
    """Default max is 10 — pass 25 results, only first 10 survive."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    results = [_result(f"source:{i}", ["short"]) for i in range(25)]
    out = ask._truncate_ask_results(results)
    assert len(out) == 10
    assert out[0]["id"] == "source:0"
    assert out[-1]["id"] == "source:9"


def test_truncate_respects_env_max_results(monkeypatch):
    """DEEPER_NOTEBOOK_ASK_MAX_RESULTS lowers the cap."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", "3")
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    results = [_result(f"source:{i}", ["x"]) for i in range(10)]
    out = ask._truncate_ask_results(results)
    assert len(out) == 3


def test_truncate_truncates_oversize_matches(monkeypatch):
    """A result whose joined matches exceed the cap gets sliced + marked.

    This is the core local-model fix: a 30 KB chunk pile becomes a
    1500-char snippet plus a truncation marker, so the LLM still sees
    the source and its top semantic content without blowing context.
    """
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv(
        "DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False
    )  # 1500 default

    big = "A" * 30_000  # one match, 30 KB
    out = ask._truncate_ask_results([_result("source:big", [big])])
    assert len(out) == 1
    matches = out[0]["matches"]
    assert isinstance(matches, str)
    assert len(matches) <= 1500 + len(ask._TRUNCATION_MARKER) + 10
    assert matches.endswith(ask._TRUNCATION_MARKER)
    # Content preserved up to cap (not silently dropped or replaced)
    assert matches.startswith("A" * 100)


def test_truncate_leaves_small_matches_alone(monkeypatch):
    """A result that fits under the cap is untouched (no marker appended)."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    short_chunks = ["hello", "world", "this is fine"]
    out = ask._truncate_ask_results([_result("note:1", short_chunks)])
    assert len(out) == 1
    matches = out[0]["matches"]
    assert "[...truncated" not in matches
    # Joined with newlines, no truncation
    assert matches == "hello\nworld\nthis is fine"


def test_truncate_respects_env_char_cap(monkeypatch):
    """DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP overrides the per-result content cap."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", "500")

    out = ask._truncate_ask_results([_result("source:x", ["Z" * 10_000])])
    matches = out[0]["matches"]
    assert len(matches) <= 500 + len(ask._TRUNCATION_MARKER) + 10
    assert matches.endswith(ask._TRUNCATION_MARKER)


def test_truncate_falls_back_on_invalid_env(monkeypatch):
    """Garbage env vars fall back to defaults instead of crashing or
    passing through to be parsed elsewhere as int."""
    monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", "not-an-int")
    monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", "garbage")

    # Should not raise; should use defaults (10 and 1500)
    results = [_result(f"s:{i}", ["A" * 5000]) for i in range(15)]
    out = ask._truncate_ask_results(results)
    assert len(out) == 10  # default max
    for r in out:
        assert len(r["matches"]) <= 1500 + len(ask._TRUNCATION_MARKER) + 10


def test_truncate_falls_back_when_char_cap_too_low(monkeypatch):
    """A char cap below 200 is almost certainly a typo (no useful
    snippet fits) — fall back to default rather than ship a useless
    one-sentence-per-result payload."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.setenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", "50")

    out = ask._truncate_ask_results([_result("s:1", ["X" * 10_000])])
    matches = out[0]["matches"]
    # Default 1500 kicked in, not the bogus 50
    assert len(matches) > 200


def test_truncate_handles_string_matches(monkeypatch):
    """`matches` can be a string (single chunk) — handle gracefully."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    out = ask._truncate_ask_results([_result("s:1", "A" * 5000)])
    matches = out[0]["matches"]
    assert isinstance(matches, str)
    assert len(matches) <= 1500 + len(ask._TRUNCATION_MARKER) + 10


def test_truncate_preserves_non_matches_fields(monkeypatch):
    """id, parent_id, title, similarity must survive untouched —
    the prompt template needs them for citation."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    r = {
        "id": "source:abc",
        "parent_id": "source:abc",
        "title": "My Source",
        "similarity": 0.87,
        "matches": ["A" * 5000],
    }
    out = ask._truncate_ask_results([r])[0]
    assert out["id"] == "source:abc"
    assert out["parent_id"] == "source:abc"
    assert out["title"] == "My Source"
    assert out["similarity"] == 0.87


def test_truncate_does_not_mutate_input(monkeypatch):
    """Other callers might still hold the original list (no surprise
    side effects)."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    original_matches = ["A" * 5000]
    results = [_result("s:1", original_matches)]
    out = ask._truncate_ask_results(results)

    # Output truncated...
    assert isinstance(out[0]["matches"], str)
    # ...but the input matches list is unchanged
    assert results[0]["matches"] is original_matches
    assert results[0]["matches"] == ["A" * 5000]


def test_truncate_handles_empty_list(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)
    assert ask._truncate_ask_results([]) == []


def test_truncate_handles_result_without_matches(monkeypatch):
    """A result dict missing `matches` is passed through, not crashed on."""
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    r = {"id": "source:weird", "parent_id": "source:weird", "title": "T"}
    out = ask._truncate_ask_results([r])
    assert out == [r]


# ---------------------------------------------------------------------------
# provide_answer integration — ensure the truncator is actually wired in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provide_answer_invokes_truncation(monkeypatch):
    """provide_answer must call _truncate_ask_results — not the raw
    vector_search output — when building the prompt payload.

    The agent that runs this graph node should never see oversized
    `matches` in the rendered prompt.
    """
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_MAX_RESULTS", raising=False)
    monkeypatch.delenv("DEEPER_NOTEBOOK_ASK_PER_RESULT_CHAR_CAP", raising=False)

    # 12 results, each with a fat 8 KB chunk — would be ~96 KB raw.
    fake_results = [
        {
            "id": f"source:{i}",
            "parent_id": f"source:{i}",
            "title": f"src {i}",
            "similarity": 0.9 - (i * 0.01),
            "matches": ["B" * 8000],
        }
        for i in range(12)
    ]

    async def fake_vector_search(*args, **kw):
        return fake_results

    rendered_payloads: list[dict] = []

    class _FakePrompter:
        def __init__(self, *args, **kw):
            pass

        def render(self, data):
            rendered_payloads.append(data)
            return "rendered"

    class _FakeMsg:
        content = "fake answer"

    class _FakeModel:
        async def ainvoke(self, prompt):
            return _FakeMsg()

    async def fake_provision(*args, **kw):
        return _FakeModel()

    monkeypatch.setattr(ask, "vector_search", fake_vector_search)
    monkeypatch.setattr(ask, "Prompter", _FakePrompter)
    monkeypatch.setattr(ask, "provision_langchain_model", fake_provision)

    state = {
        "question": "q",
        "term": "t",
        "instructions": "i",
    }
    out = await ask.provide_answer(state, {"configurable": {}})

    assert out == {"answers": ["fake answer"]}
    assert len(rendered_payloads) == 1
    payload = rendered_payloads[0]
    # Cap of 10 applied
    assert len(payload["results"]) == 10
    # Each result's matches was truncated to a string under the cap
    for r in payload["results"]:
        assert isinstance(r["matches"], str)
        assert len(r["matches"]) <= 1500 + len(ask._TRUNCATION_MARKER) + 10
    # ids list reflects the capped results
    assert len(payload["ids"]) == 10
