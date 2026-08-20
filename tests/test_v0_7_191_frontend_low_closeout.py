"""v0.7.191 — Round-9 audit LOW-severity closeout (frontend).

Four small but defensible improvements:

1.  `useNotebookChat` now exposes `cancelStreaming` (audit #3) —
    parity with useSourceChat which already had it. Previously the
    UI had no way to stop a runaway local-LLM mid-generation; only
    the unmount path aborted.

2.  `useNotebookChat.buildContext` callback now depends on stable
    string keys (`sourcesKey`, `notesKey`, `selectionsKey`) instead
    of array references (audit #4). TanStack Query returns fresh
    arrays on every refetch even when the row set is identical;
    pre-fix the callback identity churned on every poll, retriggering
    the gated effect and POSTing `/chat/build-context` again per
    refetch even with zero user input.

3.  `use-sources.ts` mutations use a predicate-based invalidation
    that excludes per-source status polling keys (audit #7). Broad
    `['sources']` invalidation matched `['sources', sourceId,
    'status']` too — every mutation triggered a status refetch
    for every source the user had open, even completed ones.

4.  ChatColumn removed dead `if (!sources && !notes)` branch
    (audit #10) — both `sources` (prop) and `notes` (useNotes
    default `[]`) are ALWAYS truthy arrays, so the "unable to
    load chat" UI was unreachable. AlertCircle import dropped
    with it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# useNotebookChat — public cancelStreaming
# ---------------------------------------------------------------------------


def test_use_notebook_chat_exposes_cancel_streaming():
    """v0.7.191: cancelStreaming must be in the hook's public
    return so the UI can stop a runaway local-LLM mid-generation.
    Parity with useSourceChat."""
    src = _read_source("frontend/src/lib/hooks/useNotebookChat.ts")
    assert "const cancelStreaming = useCallback(" in src, (
        "v0.7.191 regression: useNotebookChat lost its "
        "cancelStreaming callback. UI has no way to stop a runaway "
        "local-LLM mid-generation."
    )
    assert "cancelStreaming,  // v0.7.191" in src or "cancelStreaming," in src, (
        "v0.7.191 regression: cancelStreaming defined but not "
        "exported from the hook's return object — UI can't reach it."
    )


# ---------------------------------------------------------------------------
# useNotebookChat — stable buildContext identity
# ---------------------------------------------------------------------------


def test_use_notebook_chat_buildcontext_uses_stable_keys():
    """v0.7.191: buildContext useCallback deps must use stable
    fingerprint strings (sourcesKey, notesKey, selectionsKey), not
    raw array references that churn on every TanStack refetch."""
    src = _read_source("frontend/src/lib/hooks/useNotebookChat.ts")
    # The stable keys are derived.
    assert "const sourcesKey = sources.map" in src, (
        "v0.7.191 regression: sourcesKey fingerprint is gone. "
        "buildContext will refire per refetch."
    )
    assert "const notesKey = notes.map" in src
    assert "const selectionsKey = JSON.stringify(contextSelections)" in src
    # And the useCallback deps reference them.
    assert "[notebookId, sourcesKey, notesKey, selectionsKey]" in src, (
        "v0.7.191 regression: buildContext useCallback no longer "
        "depends on the stable keys. Array-reference churn will "
        "trigger spurious /chat/build-context POSTs again."
    )


# ---------------------------------------------------------------------------
# use-sources — predicate-scoped invalidation
# ---------------------------------------------------------------------------


def test_use_sources_uses_predicate_invalidation():
    """v0.7.191: source mutations must use predicate-based
    invalidation that excludes per-source status polling keys.
    Broad `['sources']` invalidation hit status polls too,
    causing redundant refetches per mutation per open source."""
    src = _read_source("frontend/src/lib/hooks/use-sources.ts")
    assert "_isSourcesListQuery" in src, (
        "v0.7.191 regression: list-query predicate helper gone. "
        "Mutations will trigger status-poll refetches again."
    )
    # The predicate is used at the mutation sites.
    assert (
        "queryClient.invalidateQueries({ predicate: q => _isSourcesListQuery" in src
    ), (
        "v0.7.191 regression: mutation invalidations reverted to the "
        "broad `['sources']` form. Per-source status polls will be "
        "redundantly refetched on every mutation."
    )
    # And the broad-form bad pattern is GONE from non-comment lines.
    code_only = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("//")
    )
    bad = "queryClient.invalidateQueries({ queryKey: ['sources'] })"
    assert bad not in code_only, (
        f"v0.7.191 regression: bare `{bad}` is back. Use the "
        f"_isSourcesListQuery predicate instead."
    )


# ---------------------------------------------------------------------------
# ChatColumn — dead-code branch removed
# ---------------------------------------------------------------------------


def test_chat_column_has_no_unreachable_unable_to_load_branch():
    """v0.7.191: ChatColumn's `if (!sources && !notes)` branch was
    unreachable (both are always truthy arrays). Removed alongside
    the orphaned AlertCircle import."""
    src = _read_source(
        "frontend/src/app/(dashboard)/notebooks/components/ChatColumn.tsx"
    )
    # Strip // comment lines and /* block comment */ regions so the
    # rationale comment that mentions the removed branch doesn't
    # false-trigger.
    code_only = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("//")
    )
    assert "if (!sources && !notes)" not in code_only, (
        "v0.7.191 regression: dead unreachable branch is back. "
        "Both sources and notes are always truthy arrays; this "
        "branch never renders. If real load-failure UI is wanted, "
        "check useNotes().error explicitly."
    )
    # Orphaned import is also gone — no stray AlertCircle reference.
    assert "AlertCircle" not in code_only, (
        "v0.7.191 regression: AlertCircle import re-added without "
        "a corresponding use. Strip it."
    )
