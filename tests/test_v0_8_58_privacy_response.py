"""v0.8.58 — privacy-gate decision surfaced in the chat response.

The gate's reroute (cloud→local on sensitive content) is now reported via
`privacy_gated` + `privacy_categories` on ExecuteChatResponse, mirroring the
v0.8.1 selected_provider plumbing. These tests pin the response-model shape
and guard the cross-layer wiring (provision → graph node → router) by source,
since the full path is the live-SurrealDB chat integration.
"""

from __future__ import annotations

from pathlib import Path

from api.routers.chat import ExecuteChatResponse

_ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_response_model_accepts_privacy_fields():
    r = ExecuteChatResponse(
        session_id="chat_session:x",
        messages=[],
        privacy_gated=True,
        privacy_categories=["email", "person_name"],
    )
    assert r.privacy_gated is True
    assert r.privacy_categories == ["email", "person_name"]


def test_response_model_privacy_fields_default_none():
    r = ExecuteChatResponse(session_id="chat_session:x", messages=[])
    assert r.privacy_gated is None
    assert r.privacy_categories is None


def test_provision_sets_privacy_selection_keys():
    src = _src("deeper_notebook/ai/provision.py")
    assert 'selection_out["privacy_gated"] = True' in src
    assert 'selection_out["privacy_categories"]' in src
    assert "findings_out=gate_findings" in src


def test_graph_node_returns_privacy_fields():
    src = _src("deeper_notebook/graphs/chat.py")
    assert '"privacy_gated": selection_out.get("privacy_gated")' in src
    assert '"privacy_categories": selection_out.get("privacy_categories")' in src


def test_router_reads_and_returns_privacy_fields():
    src = _src("api/routers/chat.py")
    # /chat/execute reads from result + passes to the response
    assert 'result.get("privacy_gated")' in src
    assert "privacy_gated=privacy_gated" in src
    # /chat/stream done event includes them too
    assert '"privacy_gated": privacy_gated_out' in src


def test_categories_are_labels_only_never_values():
    """Guard the safety invariant: the gate exposes category LABELS, never the
    matched secret values. apply_privacy_gate populates findings_out from
    `findings` (category names from detect_sensitive / extra_findings), not
    from the content."""
    src = _src("deeper_notebook/ai/privacy_gate.py")
    assert "findings_out.extend(findings)" in src
    # findings come from detect_sensitive (labels) ∪ extra_findings (labels)
    assert 'set(detect_sensitive(content or ""))' in src
