"""v0.7.189 — Frontend MED+LOW polish from round-9 audit.

Three small but visible UX wins:

1.  `useUpdateNote` now invalidates `QUERY_KEYS.notebooks` on
    success. Sidebar's recently-updated sort + per-notebook
    last-activity timestamp now refresh immediately after editing
    a note. Previously stale until window-focus refetch.
    `useCreateNote` and `useDeleteNote` already did this;
    `useUpdateNote` was the missing third side.

2.  New `formatDateTime(value, language)` + `formatDate(value, language)`
    helpers in `lib/utils/date-locale.ts`. The 5 sites that did
    `new Date(str).toLocaleString()` honoured the OS locale, not
    the app's i18n language — same component would render two
    different date formats stacked on each other if a user picked
    Chinese in the app while their OS was English. Migrated:
      - SourceDetailContent (2 sites)
      - RebuildEmbeddings (2 sites)
      - GmailIntegration (1 site)
    GeneratePodcastDialog + LoginForm were already doing it right
    (ad-hoc ternary on language); kept their existing code rather
    than risk regression but the new helper is available for next
    contributor.

3.  `useNotebookChat` now invalidates `QUERY_KEYS.notebookChatSessions`
    after a stream completes. Sidebar's session-card "last updated"
    timestamp refreshes immediately instead of staying stale until
    the next window-focus refetch. Matches the pattern useSourceChat
    already uses.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# useUpdateNote — notebooks list invalidation
# ---------------------------------------------------------------------------


def test_use_update_note_invalidates_notebooks_list():
    """v0.7.189: useUpdateNote's onSuccess must invalidate
    QUERY_KEYS.notebooks so the sidebar refreshes the
    last-updated time on the parent notebook."""
    src = _read_source("frontend/src/lib/hooks/use-notes.ts")
    # Find the useUpdateNote function bounds.
    fn_start = src.find("export function useUpdateNote()")
    assert fn_start != -1
    next_export = src.find("\nexport function ", fn_start + 1)
    body = src[fn_start:next_export]
    # The notebooks invalidation must be inside the function body.
    assert "QUERY_KEYS.notebooks" in body, (
        "v0.7.189 regression: useUpdateNote no longer invalidates "
        "the notebooks list. Sidebar 'last updated' will stay stale "
        "after every note edit until window focus."
    )


# ---------------------------------------------------------------------------
# Date-locale helpers
# ---------------------------------------------------------------------------


def test_date_locale_helper_exports_formatdatetime():
    """v0.7.189: the new formatDateTime + formatDate helpers must
    exist in lib/utils/date-locale.ts so future call sites have
    a canonical replacement for toLocaleString()."""
    src = _read_source("frontend/src/lib/utils/date-locale.ts")
    assert "export function formatDateTime(" in src, (
        "v0.7.189 regression: formatDateTime helper is gone. The 5 "
        "migrated call sites will break (no longer importable)."
    )
    assert "export function formatDate(" in src
    # BCP-47 mapping table is the underlying mechanism.
    assert "LOCALE_BCP47_MAP" in src


def test_source_detail_uses_formatdatetime_not_tolocalestring():
    """v0.7.189: SourceDetailContent's absolute-time display must
    use formatDateTime(value, language), not raw `.toLocaleString()`.
    Mixing both produces two different formats on the same screen."""
    src = _read_source("frontend/src/components/source/SourceDetailContent.tsx")
    # The bad pattern is gone.
    bad = "new Date(source.created).toLocaleString()"
    assert bad not in src, (
        "v0.7.189 regression: SourceDetailContent reverted to "
        "toLocaleString() — date format will inconsistently honour "
        "OS locale instead of app i18n language."
    )
    assert "formatDateTime(source.created, language)" in src
    assert "formatDateTime(source.updated, language)" in src


def test_rebuild_embeddings_uses_formatdatetime():
    """v0.7.189: RebuildEmbeddings status timestamps use
    formatDateTime."""
    src = _read_source(
        "frontend/src/app/(dashboard)/advanced/components/RebuildEmbeddings.tsx"
    )
    assert "formatDateTime(status.started_at, language)" in src
    assert "formatDateTime(status.completed_at, language)" in src


def test_gmail_integration_uses_formatdatetime():
    """v0.7.189: GmailIntegration last_sent_at uses formatDateTime."""
    src = _read_source("frontend/src/components/deeper-notebook/GmailIntegration.tsx")
    assert "formatDateTime(status.last_sent_at, language)" in src
    assert "useTranslation" in src, (
        "v0.7.189 regression: GmailIntegration must import "
        "useTranslation to get `language` for formatDateTime."
    )


# ---------------------------------------------------------------------------
# useNotebookChat session-list invalidation
# ---------------------------------------------------------------------------


def test_notebook_chat_invalidates_session_list_on_stream_done():
    """v0.7.189: after a /chat/stream completes, useNotebookChat
    must invalidate notebookChatSessions so the sidebar's
    last-updated timestamp on the session refreshes immediately.
    """
    src = _read_source("frontend/src/lib/hooks/useNotebookChat.ts")
    # The invalidation must be in the streaming success path.
    # We search for the v0.7.189 comment marker as the precise pin.
    assert "v0.7.189" in src, (
        "v0.7.189 regression: useNotebookChat lost the session-list "
        "invalidation. Sidebar 'last updated' on the session card "
        "will stay stale after every stream until window focus."
    )
    # And the actual invalidate call exists in the stream-done region.
    # (refetchCurrentSession + invalidateQueries should be paired.)
    assert "QUERY_KEYS.notebookChatSessions(notebookId)" in src
