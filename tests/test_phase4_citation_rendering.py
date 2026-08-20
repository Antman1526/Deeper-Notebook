"""Phase 4 Task 15 — Citation marker pipeline tests.

The plan's Task 15 brief asked for a Python test that "parses a
synthetic assistant reply with both citation types and assert the
resulting React component has the right number of pills with the
right href targets" — but the React component lives in the
frontend and is already covered by 20 vitest cases in
`frontend/src/components/chat/CitationPill.test.tsx` and
`frontend/src/lib/utils/citations.test.ts`.

The backend-side gap worth a test: confirm the chat system prompt
renders with the v0.8.0 `[mcp:N]` instructions intact, and that
the marker regex (which the frontend splitter relies on) actually
matches the example payloads we ship in the template. If either
breaks, citations silently regress to plain text — easy to miss
in a code review.
"""

from __future__ import annotations

import re
from pathlib import Path

from ai_prompter import Prompter

# Same regex shape the frontend uses (see
# frontend/src/lib/utils/citations.ts). Keep these in sync.
CITATION_RE = re.compile(r"\[(mcp|source|note|insight):([A-Za-z0-9_-]+)\]")


def _rendered_system_prompt() -> str:
    """Render `prompts/chat/system.jinja` with no optional blocks
    populated. Mirrors a fresh chat turn with no notebook/memory/
    context yet."""
    return Prompter(prompt_template="chat/system").render(data={})


def test_system_prompt_contains_mcp_citation_section():
    """v0.8.0 Task 13 / v0.8.10 / v0.8.64 — the external-tool CITATIONS
    section must survive every template render. If it goes missing the
    LLM stops emitting `[mcp:N]` markers and the frontend pills go dark.
    v0.8.10: assert the tool-name-agnostic `mcp_<name>` prefix instead of
    the hardcoded mcp_search/mcp_fetch. v0.8.64: the section was renamed
    "MCP TOOL CITATIONS" → "EXTERNAL TOOL CITATIONS" so the built-in
    `web_search` tool shares the same `[mcp:N]` citation scheme as MCP
    tools (they append to one per-turn capture list)."""
    prompt = _rendered_system_prompt()
    # v0.8.64 — renamed from "MCP TOOL CITATIONS" to cover web_search too.
    assert "EXTERNAL TOOL CITATIONS" in prompt
    assert "[mcp:N]" in prompt
    # v0.8.10 — the prompt now uses the generic mcp_<name> form
    # since the actual tool names depend on which MCP server the
    # operator registered (gbrain: search/think; OpenChronicle: ...).
    assert "mcp_<name>" in prompt, (
        "v0.8.10: system prompt must refer to MCP tools generically "
        "as `mcp_<name>` since the actual names are server-dependent"
    )
    # v0.8.64 — the built-in web_search tool must be named so the model
    # knows it exists and cites it via the shared [mcp:N] scheme.
    assert "web_search" in prompt, (
        "v0.8.64: system prompt must name the built-in `web_search` tool"
    )


def test_system_prompt_capabilities_mentions_mcp_tools():
    """The CAPABILITIES block tells the model when to reach for
    MCP tools. If it disappears the model under-uses MCP even
    when the user clearly needs live info."""
    prompt = _rendered_system_prompt()
    # v0.8.10 — assert the generic mcp_<name> prefix (post-tool-name-
    # agnostic refactor) instead of the v0.8.0 hardcoded names.
    assert "mcp_<name>" in prompt
    # Look for a v0.8.x marker so a future cleanup that drops the
    # comment fails this test instead of silently breaking.
    assert "v0.8.0" in prompt or "v0.8.10" in prompt


def test_system_prompt_legacy_source_note_insight_citations_still_present():
    """The legacy citation block (source/note/insight) must still
    render — we extended, didn't replace."""
    prompt = _rendered_system_prompt()
    assert "[document_id]" in prompt
    assert "source:" in prompt
    assert "note:" in prompt
    assert "insight:" in prompt


def test_mcp_example_block_matches_citation_regex():
    """The NBA-Finals example in the system prompt is the
    canonical shape we want the model to imitate. Run the
    frontend's citation regex against the rendered prompt and
    confirm we extract exactly 2 mcp markers with indices 1 and 2.
    If the example block is reworded and accidentally breaks the
    regex, the frontend pill renderer silently degrades."""
    prompt = _rendered_system_prompt()
    # Slice to the example region so we don't accidentally match
    # `[mcp:N]` in the literal description text earlier.
    example_start = prompt.index("### MCP EXAMPLE")
    example = prompt[example_start:]

    matches = CITATION_RE.findall(example)
    mcp_matches = [m for m in matches if m[0] == "mcp"]
    # The example block uses [mcp:1] and [mcp:2] in BOTH the
    # assistant reply line and the trailing "Please note that ..."
    # disclaimer, so the regex finds each twice. Assert distinct
    # indices instead of exact list — guards against the example
    # being rewritten to skip [mcp:2] or jump to [mcp:3].
    distinct_indices = sorted({m[1] for m in mcp_matches})
    assert distinct_indices == ["1", "2"], (
        f"Expected example to demo [mcp:1] and [mcp:2]; got distinct indices {distinct_indices}"
    )
    assert len(mcp_matches) >= 2, "Example must show at least 2 mcp markers"


def test_legacy_example_block_matches_citation_regex():
    """The original example block uses note/insight markers with
    random-looking IDs. The frontend splitter must catch them
    too."""
    prompt = _rendered_system_prompt()
    matches = CITATION_RE.findall(prompt)
    kinds = {m[0] for m in matches}
    # We expect at least note and insight to appear in the legacy
    # example. Both must round-trip through the regex.
    assert "note" in kinds, kinds
    assert "insight" in kinds, kinds


def test_citation_regex_rejects_malformed_markers():
    """Frontend defense: the splitter must not match garbage that
    looks like a marker but isn't (e.g. `[mcp:]`, `[mcp:1 ]`,
    `[mcp:1!]`). If this assertion fires the frontend will start
    rendering empty / broken pills."""
    bad_cases = [
        "[mcp:]",
        "[mcp:1 ]",  # trailing space
        "[mcp:1!]",  # punctuation
        "[ mcp:1]",  # leading space
        "[unknown:1]",  # unknown kind
        "mcp:1",  # missing brackets
        "[[mcp:1]]",  # double brackets
    ]
    for s in bad_cases:
        assert not CITATION_RE.fullmatch(s), f"Should NOT match: {s!r}"


def test_citation_regex_accepts_all_valid_kinds():
    """Round-trip every valid kind through the regex."""
    good_cases = [
        ("[mcp:1]", "mcp", "1"),
        ("[mcp:42]", "mcp", "42"),
        ("[source:abc123def]", "source", "abc123def"),
        ("[note:XYZ_789]", "note", "XYZ_789"),
        ("[insight:hello-world]", "insight", "hello-world"),
    ]
    for raw, expected_kind, expected_value in good_cases:
        m = CITATION_RE.fullmatch(raw)
        assert m is not None, f"Should match: {raw!r}"
        assert m.group(1) == expected_kind
        assert m.group(2) == expected_value


def test_frontend_splitter_module_exists():
    """v0.8.0 Task 14 ships `frontend/src/lib/utils/citations.ts`.
    If someone deletes it the pills break silently — this test
    guards against that."""
    root = Path(__file__).resolve().parents[1]
    splitter = root / "frontend" / "src" / "lib" / "utils" / "citations.ts"
    pill = root / "frontend" / "src" / "components" / "chat" / "CitationPill.tsx"
    assert splitter.is_file(), f"Missing {splitter}"
    assert pill.is_file(), f"Missing {pill}"
