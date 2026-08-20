"""v0.7.201 — audit sweep across backend services + notes router.

Fresh audit (post-v0.7.200) on areas not yet covered by previous
sweeps: credentials_service.py, podcast_service.py, api/main.py
/readyz, notes router, SetupBanner fork URL, markdown-editor theme.

Five discrete bugs:

1. `credentials_service.test_credential` leaked str(e) in the
   `Error: {truncated}` fallback. Esperanto/SDK exceptions can
   embed endpoint URLs + partial keys. Sanitized.

2. `podcast_service` `notebook = await Notebook.get(...)` could be
   None; `str(None) = "None"` silently became the podcast's content.
   Now raises NotFoundError before touching the notebook reference.

3. `api/main.py:/readyz` returned `str(exc)` from a failed migration
   check inside the public JSON body. Migration exceptions can
   embed SurrealDB driver frames + file paths. Sanitized to
   "migrations check failed".

4. `api/routers/notes.py` had 5 bare `HTTPException(404, "X not
   found")` callsites instead of `raise NotFoundError(...)`.
   Defeated the v0.7.179-183 global classifier sweep. Added
   `except NotFoundError: raise` handlers to list_notes and
   create_note (the only two functions that didn't already have
   them) so the typed exception reaches the global handler.

5. (Frontend, no test here) — SetupBanner URL pointed at upstream
   lfnovo repo; switched to Plus fork. Markdown editor had
   hardcoded `data-color-mode="light"`; now follows next-themes.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_test_credential_does_not_leak_str_exception():
    """v0.7.201 — `test_credential` fallback message must NOT
    include `truncated = error_msg[:100]` formatted with `Error:`.
    SDK exception strings can embed endpoint URLs + partial API
    keys; that's the v0.7.177/184 info-leak class."""
    src = _src("api/credentials_service.py")
    # Strip Python `# ...` comments so the historical-rationale block
    # doesn't false-positive the regex.
    code_only = "\n".join(
        ln
        for ln in src.splitlines()
        if "#" not in ln.split('"')[0] or not ln.lstrip().startswith("#")
    )
    # Simpler: strip lines starting with `#`.
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    )
    assert 'f"Error: {truncated}"' not in code_only, (
        "v0.7.201 regression: test_credential fallback restored the "
        "str(e) leak in the toast/API response."
    )
    # The new generic message must include the provider name +
    # actionable text.
    assert "Connection test failed. Check that the" in src


def test_podcast_service_raises_notfound_on_missing_notebook():
    """v0.7.201 — `podcast_service.generate_podcast` must raise
    `NotFoundError` when `Notebook.get(notebook_id)` returns None.
    Otherwise `str(None) = "None"` becomes the podcast's content
    and generation produces a nonsensical episode."""
    src = _src("api/podcast_service.py")
    assert "if notebook is None:" in src
    # The raise must be NotFoundError (not bare HTTPException).
    assert "raise NotFoundError(" in src
    # The fallback path must let NotFoundError pass through to the
    # global classifier.
    assert "if isinstance(e, NotFoundError):\n                        raise" in src


def test_readyz_does_not_leak_migrations_error():
    """v0.7.201 — `/readyz` JSON body must NOT include `str(exc)`
    from a migration failure. Migration exceptions can embed
    SurrealDB driver frames, .surql file paths, DB DSN fragments
    — none safe for a public health endpoint."""
    src = _src("api/main.py")
    assert "migrations_error = str(exc)" not in src, (
        "v0.7.201 regression: /readyz restored the str(exc) leak."
    )
    # Generic placeholder must replace it.
    assert 'migrations_error = "migrations check failed"' in src


def test_notes_router_uses_typed_not_found_error():
    """v0.7.201 — `api/routers/notes.py` must use `raise
    NotFoundError(...)` for missing-note / missing-notebook cases,
    NOT `raise HTTPException(status_code=404, ...)`. The global
    classifier in `api/main.py` formats NotFoundError into a clean
    404 with a user-friendly message; the bare HTTPException
    bypassed that consistency."""
    src = _src("api/routers/notes.py")
    # The bare-404 pattern must be gone (for these two strings —
    # other 404s would have different detail text).
    assert 'HTTPException(status_code=404, detail="Note not found")' not in src
    assert 'HTTPException(status_code=404, detail="Notebook not found")' not in src
    # And NotFoundError raises must be present in their place.
    assert 'raise NotFoundError("Note not found")' in src
    assert 'raise NotFoundError("Notebook not found")' in src


def test_notes_router_has_notfound_bubble_in_list_and_create():
    """v0.7.201 — the v0.7.201 swap of HTTPException(404) →
    NotFoundError requires `except NotFoundError: raise` handlers
    BEFORE the generic `except Exception` in list_notes and
    create_note. Without it, NotFoundError gets caught by the
    `except Exception` block and collapsed to 500."""
    src = _src("api/routers/notes.py")
    # Pin both v0.7.201 markers — one in list_notes, one in create_note.
    assert "v0.7.201 — bubble typed exceptions to the global classifier" in src
    assert "v0.7.201 — same bubble-pattern fix as list_notes" in src


def test_setup_banner_points_at_deeper_notebook_repo():
    """The active encryption-docs link must follow the downstream product."""
    src = _src("frontend/src/components/layout/SetupBanner.tsx")
    assert "Antman1526/Deeper-Notebook" in src, (
        "Deeper Notebook users would land on documentation that may not "
        "match the downstream build."
    )
    code_only = "\n".join(
        ln
        for ln in src.splitlines()
        if not ln.lstrip().startswith("//") and not ln.lstrip().startswith("{/*")
    )
    assert "Antman1526/open-notebook-Plus" not in code_only
    assert "lfnovo/open-notebook" not in code_only


def test_active_documentation_uses_downstream_links_and_preserves_upstream():
    active_paths = (
        "README.md",
        "SECURITY.md",
        "docs/BUILD_WINDOWS.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/installation_issue.yml",
    )
    for path in active_paths:
        src = _src(path)
        assert "Antman1526/open-notebook-Plus" not in src, path

    readme = _src("README.md")
    assert "https://github.com/Antman1526/Deeper-Notebook" in readme
    assert "https://github.com/lfnovo/open-notebook" in readme
    assert "git clone https://github.com/Antman1526/Deeper-Notebook.git" in readme

    issue_templates = "\n".join(
        _src(path) for path in active_paths if path.startswith(".github/")
    )
    assert "https://github.com/Antman1526/Deeper-Notebook" in issue_templates


def test_readme_documents_current_artifacts_and_migration_contract():
    readme = _src("README.md")

    assert "# Deeper Notebook" in readme
    assert "Notebook Spark" in readme
    assert "Research Core" in readme
    assert "Deeper-Notebook-mac-<arch>.dmg" in readme
    assert "Deeper-Notebook-windows-x64.zip" in readme
    assert "Deeper-Notebook-Setup-x64.exe" in readme
    assert "## Migrating from Open Notebook Plus" in readme
    assert "DEEPER_NOTEBOOK_*" in readme
    assert "DN_*" in readme
    assert "DEEPER_NOTEBOOK_*" in readme
    assert "DEEPER_NOTEBOOK_*" in readme
    assert "~/.deeper-notebook/" in readme
    assert "~/.open-notebook-plus/" in readme
    assert "%USERPROFILE%\\.deeper-notebook" in readme
    assert "%USERPROFILE%\\.open-notebook-plus" in readme


def test_markdown_editor_follows_theme():
    """v0.7.201 — `MarkdownEditor` must read `useTheme()` instead
    of hardcoding `data-color-mode="light"`. Otherwise the editor
    renders white-on-dark inside a dark-themed dialog — obvious
    visual mismatch."""
    src = _src("frontend/src/components/ui/markdown-editor.tsx")
    assert "useTheme" in src
    # Hardcoded light must be gone from the active markup.
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("//")
    )
    assert 'data-color-mode="light"' not in code_only
