"""ONP v0.6 — Email-digest builder.

Queries SurrealDB for recent activity across notebooks/sources/notes/podcasts/
memory and renders an HTML email body. Sections respect the user's per-section
toggles from GmailIntegration.
"""
from __future__ import annotations

import html as _html
from datetime import datetime, timedelta, timezone
from typing import Any

from open_notebook.database.repository import repo_query
from open_notebook.domain.gmail import GmailIntegration


async def build_digest_html(g: GmailIntegration) -> tuple[str, int]:
    """Build digest HTML for the time window since the last send (or last 7 d).

    Returns (html_body, total_item_count). Caller wraps in MIME and sends.
    """
    since = g.last_sent_at
    if since is None:
        # First send: last 7 days so the user sees a meaningful summary
        since = datetime.now(timezone.utc) - timedelta(days=7)

    since_iso = since.isoformat()

    sections: list[str] = []
    total = 0

    # ONP v0.6.2 — SurrealDB compares datetime columns by type, not by string.
    # Cast `$since` to <datetime> in each WHERE so an ISO-8601 param works.
    if g.include_notebooks:
        rows = await _safe_query(
            "SELECT id, name, description, created, updated FROM notebook "
            "WHERE (archived != true) "
            "AND (updated > <datetime>$since OR created > <datetime>$since) "
            "ORDER BY updated DESC LIMIT 20",
            {"since": since_iso},
        )
        if rows:
            sections.append(_render_section(
                "Notebooks",
                f"{len(rows)} notebook{'s' if len(rows) != 1 else ''} created or updated",
                [_render_notebook(r) for r in rows],
            ))
            total += len(rows)

    if g.include_sources:
        # `source` table has no `type` or `status` column (asset metadata is
        # stored on the linked asset record). Just show title + created.
        rows = await _safe_query(
            "SELECT id, title, created FROM source "
            "WHERE created > <datetime>$since ORDER BY created DESC LIMIT 30",
            {"since": since_iso},
        )
        if rows:
            sections.append(_render_section(
                "Sources added",
                f"{len(rows)} new source{'s' if len(rows) != 1 else ''} (PDFs, links, transcripts)",
                [_render_source(r) for r in rows],
            ))
            total += len(rows)

    if g.include_notes:
        rows = await _safe_query(
            "SELECT id, title, created FROM note "
            "WHERE created > <datetime>$since ORDER BY created DESC LIMIT 20",
            {"since": since_iso},
        )
        if rows:
            sections.append(_render_section(
                "Notes written",
                f"{len(rows)} new note{'s' if len(rows) != 1 else ''}",
                [_render_note(r) for r in rows],
            ))
            total += len(rows)

    if g.include_podcasts:
        # Table is `episode` (migration 7), not `podcast_episode`. Status is
        # on the linked `command` record, so skip it for the digest summary.
        rows = await _safe_query(
            "SELECT id, name, created FROM episode "
            "WHERE created > <datetime>$since ORDER BY created DESC LIMIT 20",
            {"since": since_iso},
        )
        if rows:
            sections.append(_render_section(
                "Podcast episodes",
                f"{len(rows)} podcast{'s' if len(rows) != 1 else ''} generated",
                [_render_podcast(r) for r in rows],
            ))
            total += len(rows)

    if g.include_memory:
        rows = await _safe_query(
            "SELECT id, text, scope, confidence, created_at "
            "FROM memory_fact WHERE created_at > <datetime>$since "
            "ORDER BY created_at DESC LIMIT 30",
            {"since": since_iso},
        )
        if rows:
            sections.append(_render_section(
                "Memory facts",
                f"{len(rows)} fact{'s' if len(rows) != 1 else ''} extracted",
                [_render_memory(r) for r in rows],
            ))
            total += len(rows)

    if total == 0:
        sections.append(
            '<p style="color:#888;font-style:italic;">No notebook activity '
            'in the digest window. Quiet days are fine — your digest will '
            'show up again next time you create something.</p>'
        )

    window = "since last digest" if g.last_sent_at else "in the last 7 days"
    header = f"""
<h1 style="margin:0 0 8px;color:#1A2B3C;font-size:22px;">Open Notebook Plus</h1>
<p style="margin:0 0 24px;color:#888;font-size:13px;">
  Activity {_html.escape(window)} · sent {datetime.now(timezone.utc).strftime("%b %d, %Y · %H:%M UTC")}
</p>
"""
    footer = """
<hr style="border:none;border-top:1px solid #eee;margin:32px 0 12px;">
<p style="color:#aaa;font-size:11px;text-align:center;">
  You're receiving this because you connected Gmail in Open Notebook Plus.
  Manage frequency or disconnect in Settings → Email Digests.
</p>
"""
    body = "\n".join(sections)
    html_doc = f"""<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                   max-width:640px;margin:0 auto;padding:24px;color:#1A2B3C;">
{header}
{body}
{footer}
</body></html>"""
    return html_doc, total


def _render_section(title: str, sub: str, items: list[str]) -> str:
    list_html = "\n".join(f'<li style="margin:6px 0;">{i}</li>' for i in items)
    return f"""
<section style="margin:0 0 24px;">
  <h2 style="margin:0 0 4px;font-size:15px;color:#2D7FF9;">{_html.escape(title)}</h2>
  <p style="margin:0 0 8px;color:#888;font-size:12px;">{_html.escape(sub)}</p>
  <ul style="padding-left:18px;margin:0;font-size:13px;list-style:disc;">
    {list_html}
  </ul>
</section>"""


def _render_notebook(r: dict) -> str:
    name = _esc(r.get("name") or "(untitled)")
    desc = _esc((r.get("description") or "")[:120])
    return f"<strong>{name}</strong>" + (f" — <span style='color:#888;'>{desc}</span>" if desc else "")


def _render_source(r: dict) -> str:
    return f"<strong>{_esc(r.get('title') or '(untitled)')}</strong>"


def _render_note(r: dict) -> str:
    return f"<strong>{_esc(r.get('title') or '(untitled)')}</strong>"


def _render_podcast(r: dict) -> str:
    return f"<strong>{_esc(r.get('name') or '(unnamed)')}</strong>"


def _render_memory(r: dict) -> str:
    text = _esc((r.get("text") or "")[:160])
    conf = r.get("confidence", 1.0)
    return f"{text} <span style='color:#888;'>({float(conf):.2f})</span>"


async def _safe_query(query: str, vars: dict) -> list[dict]:
    """Run a query, return empty list on any error (don't break the digest
    over one missing table — e.g. memory_fact may not exist on fresh DBs)."""
    try:
        result = await repo_query(query, vars)
        if isinstance(result, list):
            return result
        return []
    except Exception:
        return []


def _esc(s: Any) -> str:
    return _html.escape(str(s)) if s is not None else ""
