"""v0.7.199 — `/search/ask` SSE handler accepts both dict and Pydantic
state shapes from LangGraph nodes.

Background: LangGraph state-shape variance — a node may return a
plain dict OR a typed Pydantic model depending on its signature.
`api/routers/search.py:stream_ask_response()` previously did
`if not isinstance(output, dict): continue` and silently dropped all
SSE events when a Pydantic model came through. Users saw a blank
streaming response on the Ask flow even though the upstream graph
nodes had completed.

The v0.7.55 fix already used this pattern in /search/ask/simple;
v0.7.199 extends it to the streaming-events handler.

Test is AST-level so it doesn't depend on a running ask_graph.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_stream_ask_response_accepts_pydantic_state_shape():
    """v0.7.199 — handler must access output via a getattr-fallback
    helper, not a bare `isinstance(output, dict)` gate that drops
    every subsequent SSE event when a node returns a Pydantic model."""
    src = _src("api/routers/search.py")
    # The bare-isinstance early-continue must be gone.
    assert (
        "if not isinstance(output, dict):\n                    continue" not in src
    ), (
        "v0.7.199 regression: bare isinstance(output, dict) gate is "
        "back. LangGraph nodes returning Pydantic models will drop "
        "all subsequent strategy/answer/final_answer SSE events."
    )
    # The new `_get` helper (or equivalent getattr-fallback) must be present.
    assert "def _get(" in src and "getattr(output, key, None)" in src, (
        "v0.7.199 regression: getattr-fallback helper removed from "
        "stream_ask_response. Pydantic state shape will be dropped."
    )


def test_use_search_uses_translating_helper():
    """v0.7.199 — frontend `lib/hooks/use-search.ts` must use the
    translating error helper (not the key-returning one) in its
    toast description. v0.7.196 swept the rest of the hook layer
    but missed this file."""
    src = _src("frontend/src/lib/hooks/use-search.ts")
    assert "getApiErrorMessage(" in src, (
        "v0.7.199 regression: use-search.ts dropped getApiErrorMessage. "
        "Toast description will leak raw backend error strings."
    )
    # The bare-key variant is removed from the toast onError handler.
    # Strip comment lines so the historical-rationale comment doesn't
    # false-positive the regex.
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("//")
    )
    assert "t(getApiErrorKey(error.message))" not in code_only
    assert "description: t(getApiErrorKey(" not in code_only


def test_zod_schemas_use_translation_factory():
    """v0.7.199 — three zod schemas (transformations, notes,
    notebooks) must be factory-pattern with the validation messages
    routed via the t() function. Previously they had hardcoded
    English messages (or no message at all, falling back to zod's
    default "String must contain at least 1 character(s)") that
    non-English users saw in field errors."""
    for rel in (
        "frontend/src/app/(dashboard)/transformations/components/TransformationEditorDialog.tsx",
        "frontend/src/app/(dashboard)/notebooks/components/NoteEditorDialog.tsx",
        "frontend/src/components/notebooks/CreateNotebookDialog.tsx",
    ):
        src = _src(rel)
        # Factory function with t parameter must exist.
        assert "(t: (key: string) => string) =>" in src, (
            f"v0.7.199 regression: {rel} no longer uses the factory "
            f"pattern for zod schema. Form-field validation messages "
            f"will render in English on non-English locales."
        )
        # The infer-type must use ReturnType pattern.
        assert "ReturnType<typeof make" in src
        # No hardcoded English required-messages.
        assert "'Name is required'" not in src
        assert "'Content is required'" not in src
        assert "'Title is required'" not in src
        assert "'Prompt is required'" not in src
