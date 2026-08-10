"""v0.8.55 — Phase 5.1c: confidence-aware memory.

The extract prompt asks the model for a confidence (0.0-1.0) per fact. v0.8.55
(a) drops candidates below DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR and (b) persists the
real score (via metadata → surreal_store). Default floor 0.0 → keep all
(unchanged); a missing/garbled score is treated as 1.0 (never dropped on an
absent number).
"""
from __future__ import annotations

import pytest

from desktop.memory import writer as writer_mod
from desktop.memory.surreal_store import SurrealMemoryStore
from desktop.memory.writer import _coerce_confidence, apply_tool_call


class _FakeMemClient:
    def __init__(self):
        self.added: list[dict] = []

    # v0.8.66 (audit C1) — accept `infer` (the writer now passes infer=False so
    # mem0 stores the pre-extracted fact verbatim instead of re-running an LLM).
    def add(self, messages, user_id=None, metadata=None, infer=None):
        self.added.append(
            {"messages": messages, "metadata": metadata, "infer": infer}
        )


def _call(conf=None, name="remember_fact", text="uses Python"):
    args = {"text": text, "scope": "user"}
    if conf is not None:
        args["confidence"] = conf
    return {"name": name, "arguments": args}


# ---------------------------------------------------------------------------
# _coerce_confidence + _confidence_floor
# ---------------------------------------------------------------------------


def test_coerce_confidence():
    assert _coerce_confidence(0.5) == 0.5
    assert _coerce_confidence("0.8") == 0.8
    assert _coerce_confidence(None) == 1.0        # absent → trust
    assert _coerce_confidence("garbage") == 1.0   # garbled → trust
    assert _coerce_confidence(1.7) == 1.0         # clamp high
    assert _coerce_confidence(-0.3) == 0.0        # clamp low


def test_confidence_floor_default(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR", raising=False)
    assert writer_mod._confidence_floor() == 0.0


@pytest.mark.parametrize("val,expected", [
    ("0.5", 0.5), ("0", 0.0), ("1", 1.0),
    ("1.5", 0.0), ("-1", 0.0), ("x", 0.0), ("", 0.0),
])
def test_confidence_floor_parsing(monkeypatch, val, expected):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR", val)
    assert writer_mod._confidence_floor() == expected


# ---------------------------------------------------------------------------
# apply_tool_call — floor + persistence
# ---------------------------------------------------------------------------


def test_default_floor_keeps_everything(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR", raising=False)
    mem = _FakeMemClient()
    apply_tool_call(mem, _call(conf=0.1))  # low but floor is 0.0
    assert len(mem.added) == 1


def test_floor_drops_low_confidence(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR", "0.6")
    mem = _FakeMemClient()
    apply_tool_call(mem, _call(conf=0.4))   # below floor → dropped
    apply_tool_call(mem, _call(conf=0.9))   # above floor → kept
    assert len(mem.added) == 1
    assert mem.added[0]["metadata"]["confidence"] == 0.9


def test_missing_confidence_not_dropped_even_with_floor(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR", "0.6")
    mem = _FakeMemClient()
    apply_tool_call(mem, _call(conf=None))  # absent → treated as 1.0 → kept
    assert len(mem.added) == 1
    assert mem.added[0]["metadata"]["confidence"] == 1.0


def test_confidence_persisted_in_metadata(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_MEMORY_CONFIDENCE_FLOOR", raising=False)
    mem = _FakeMemClient()
    apply_tool_call(mem, _call(conf=0.75))
    assert mem.added[0]["metadata"]["confidence"] == 0.75
    assert mem.added[0]["metadata"]["kind"] == "fact"


# ---------------------------------------------------------------------------
# surreal_store.insert — confidence read from metadata
# ---------------------------------------------------------------------------


class _CaptureClient:
    def __init__(self):
        self.rows: list[dict] = []

    def query(self, sql, vars=None):
        if sql.strip().startswith("CREATE") and vars and "row" in vars:
            self.rows.append(vars["row"])
        return []


def test_store_persists_confidence_from_metadata():
    client = _CaptureClient()
    store = SurrealMemoryStore.from_test_client(client)
    store.insert(
        vectors=[[0.0] * 768],
        payloads=[{"text": "fact", "metadata": {"kind": "fact", "scope": "user",
                                                "confidence": 0.42}}],
        ids=None,
    )
    assert client.rows[0]["confidence"] == 0.42
    assert client.rows[0]["scope"] == "user"


def test_store_defaults_confidence_when_absent():
    client = _CaptureClient()
    store = SurrealMemoryStore.from_test_client(client)
    store.insert(
        vectors=[[0.0] * 768],
        payloads=[{"text": "fact", "metadata": {"kind": "fact"}}],
        ids=None,
    )
    assert client.rows[0]["confidence"] == 1.0
