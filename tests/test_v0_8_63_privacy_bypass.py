"""v0.8.63 — privacy-gate bypass (redaction-review "Re-ask allowing cloud").

Security-critical contract: the bypass is OFF by default (the fail-closed gate
stays active) and is only honored when explicitly set True for a single turn.
The full provision path is the live-DB chat integration, so the cross-layer
wiring is guarded by source + a request-model default test.
"""

from __future__ import annotations

from pathlib import Path

from api.routers.chat import ExecuteChatRequest

_ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_request_bypass_defaults_false():
    """The gate stays active unless the client explicitly opts out."""
    req = ExecuteChatRequest(session_id="chat_session:x", message="hi", context={})
    assert req.bypass_privacy_gate is False


def test_request_bypass_can_be_set_true():
    req = ExecuteChatRequest(
        session_id="chat_session:x",
        message="hi",
        context={},
        bypass_privacy_gate=True,
    )
    assert req.bypass_privacy_gate is True


def test_router_threads_bypass_into_state():
    src = _src("api/routers/chat.py")
    # Both /chat/execute and /chat/stream set the state key from the request.
    assert (
        src.count(
            'state_values["bypass_privacy_gate"] = bool(request.bypass_privacy_gate)'
        )
        == 2
    )


def test_node_passes_bypass_to_provision():
    src = _src("deeper_notebook/graphs/chat.py")
    assert 'privacy_gate_bypass=bool(state.get("bypass_privacy_gate"))' in src


def test_provision_skips_gate_when_bypassed():
    """The gate block must be guarded by `if privacy_gate_bypass: ... else:`
    so a bypassed turn never runs the classifier or apply_privacy_gate."""
    src = _src("deeper_notebook/ai/provision.py")
    assert "privacy_gate_bypass: bool = False" in src
    assert "if privacy_gate_bypass:" in src
    # The gate call + classifier live in the else branch.
    bypass_idx = src.index("if privacy_gate_bypass:")
    gate_idx = src.index("choice = apply_privacy_gate(", bypass_idx)
    else_idx = src.index("else:", bypass_idx)
    assert else_idx < gate_idx, "apply_privacy_gate must be in the bypass else-branch"
