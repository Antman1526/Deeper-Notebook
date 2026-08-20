"""v0.8.68 — source-chat offline-fallback parity guards.

The notebook-chat leg is covered by test_offline_gate.py /
test_provisioning_fallback.py / test_chat_offline_fallback_plumbing.py.
Source chat reuses the exact same gate; what's specific here is the
THREADING: node → SSE event → frontend stash. These are source-anchor
regression guards (same style as the v0.8.44 source-chat parity tests and
the v0.8.67n launcher anchors) — they fail loudly if a refactor drops one
link of the chain, without needing a live graph/DB.
"""

from __future__ import annotations

import inspect
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def test_source_chat_node_threads_fallback_out():
    """Both provisioning calls in the source-chat node must pass
    fallback_out, and the node result must carry offline_fallback."""
    from deeper_notebook.graphs import source_chat

    src = inspect.getsource(source_chat)
    assert src.count("fallback_out=offline_fallback_out") >= 2, (
        "source_chat node must thread fallback_out through BOTH the "
        "explicit-model and smart-router provisioning calls"
    )
    assert '"offline_fallback": offline_fallback_out or None' in src, (
        "source_chat node must return offline_fallback in its result dict"
    )


def test_source_chat_node_has_midturn_network_retry():
    from deeper_notebook.graphs import source_chat

    src = inspect.getsource(source_chat)
    assert "report_network_failure()" in src
    assert "retry_fallback" in src, (
        "mid-turn NetworkError must retry once on the gated local model"
    )


def test_source_chat_router_emits_offline_fallback_event():
    router_src = (_REPO / "api" / "routers" / "source_chat.py").read_text()
    assert '"type": "offline_fallback"' in router_src, (
        "SSE stream must emit the offline_fallback event when the gate acted"
    )
    # Dual-path guard: the Pydantic-state branch must also capture the field.
    assert (
        'getattr(\n                                output, "offline_fallback", None\n                            )'
        in router_src
        or 'getattr(output, "offline_fallback", None)'
        in router_src.replace("\n", " ").replace("  ", " ")
        or '"offline_fallback": getattr(' in router_src
    ), "Pydantic-state branch must capture offline_fallback too"


def test_use_source_chat_stashes_offline_fallback():
    hook_src = (
        _REPO / "frontend" / "src" / "lib" / "hooks" / "useSourceChat.ts"
    ).read_text()
    assert "data.type === 'offline_fallback'" in hook_src, (
        "useSourceChat must handle the offline_fallback SSE event"
    )
    assert "'chat', 'selected-provider', streamingAiId" in hook_src, (
        "the stash must use ChatMessageProviderBadge's cache key shape"
    )


def test_source_chat_panel_renders_provider_badge():
    panel_src = (
        _REPO / "frontend" / "src" / "components" / "source" / "ChatPanel.tsx"
    ).read_text()
    assert "ChatMessageProviderBadge" in panel_src, (
        "source ChatPanel must render the badge that shows the offline pill"
    )


def test_source_chat_node_threads_selection_out():
    """v0.8.68 item 4 — the smart-router decision reaches the node result
    so the local/cloud badge gets data on the source-chat surface."""
    from deeper_notebook.graphs import source_chat

    src = inspect.getsource(source_chat)
    assert "selection_out=selection_out" in src
    assert '"selected_provider": selection_out.get("selected_provider")' in src


def test_source_chat_router_emits_selected_provider_event():
    router_src = (_REPO / "api" / "routers" / "source_chat.py").read_text()
    assert '"type": "selected_provider"' in router_src


def test_use_source_chat_merges_selection_into_badge_cache():
    hook_src = (
        _REPO / "frontend" / "src" / "lib" / "hooks" / "useSourceChat.ts"
    ).read_text()
    assert "data.type === 'selected_provider'" in hook_src
    # Both handlers must MERGE (updater function), not overwrite.
    assert hook_src.count("...(old ?? {})") >= 2
