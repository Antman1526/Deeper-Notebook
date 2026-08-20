"""v0.7.203 — Studio page full i18n extraction.

Background: the entire Studio page (~30 user-visible strings) was
hardcoded English. Non-English users — the only ONP install base
that ACTUALLY hits the i18n system — saw English on a primary
entry point. Audit HIGH #1 from v0.7.196, carried through several
deferred lists because the diff size (30 strings × 10 locales =
~300 string changes) deserved a dedicated commit.

Fix shape:
  1. New `studio.*` namespace in `frontend/src/lib/locales/<code>/
     index.ts` for all 10 locales (en-US + 9 translated).
  2. `frontend/src/app/(dashboard)/studio/page.tsx` rewritten to
     route every user-visible string through `t('studio.*')`.
  3. `isAllowed()` (file-rejection reason) refactored to return a
     `{key, params}` tuple instead of a pre-formatted English
     string; caller (which has access to t() via useTranslation)
     interpolates.

These tests:
  - AST pin: no hardcoded English on the Studio render tree.
  - AST pin: all 10 locales have the full `studio.*` namespace.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = (
    "en-US",
    "zh-CN",
    "zh-TW",
    "pt-BR",
    "ja-JP",
    "it-IT",
    "fr-FR",
    "ru-RU",
    "bn-IN",
    "es-ES",
)
STUDIO_KEYS = (
    "backToNotebooks",
    "title",
    "subtitle",
    "step1Title",
    "step1Description",
    "uploadFilesLabel",
    "dropFilesHere",
    "browse",
    "removeFile",
    "linksLabel",
    "linksPlaceholder",
    "linksHelp",
    "step2Title",
    "notebookModeTitle",
    "notebookModeDescription",
    "podcastModeTitle",
    "podcastModeDescription",
    "bothModeTitle",
    "bothModeDescription",
    "coursePackModeTitle",
    "coursePackModeDescription",
    "episodeProfileLabel",
    "episodeProfilePlaceholder",
    "speakerProfileLabel",
    "speakerProfilePlaceholder",
    "titleLabel",
    "titlePlaceholder",
    "generatingNotebook",
    "generatingPodcast",
    "generatingBoth",
    "queuingCoursePack",
    "generateNotebook",
    "generatePodcast",
    "generateBoth",
    "generateCoursePack",
    "notebookGenerated",
    "podcastJobStarted",
    "bothJobStarted",
    "notebookGeneratedDescription",
    "podcastJobStartedDescription",
    "bothJobStartedDescription",
    "coursePackQueued",
    "coursePackQueuedDescription",
    # v0.8.70 — retired `coursePackGenerated` / `coursePackGeneratedDescription`
    # from the pin. They belonged to the original SYNCHRONOUS course-pack flow;
    # course packs now generate via the async/queued path (`coursePackQueued*`,
    # still referenced in studio/page.tsx). The two "generated" keys had zero
    # references anywhere in source (caught by the frontend unused-key test) and
    # were removed from every locale, so pinning them here only forced dead
    # strings back into 14 files. coursePackQueued* stays pinned — it's live.
    "generatedWithWarnings",
    "generationFailed",
    "filesRejected",
    "filesRejectedPlural",
    "unsupportedType",
    "fileTooLarge",
)


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_all_locales_have_full_studio_namespace():
    """v0.7.203 — every locale (en-US + 9 translated) must declare
    a `studio:` object with the complete v0.7.203 key set. The
    existing locale-parity vitest enforces structural sameness;
    this Python pin catches missing key NAMES (which the vitest
    would also catch but only at frontend test time)."""
    missing: list[tuple[str, str]] = []
    for code in LOCALES:
        src = _src(f"frontend/src/lib/locales/{code}/index.ts")
        # Cheap regex check — each key must appear once inside a
        # `key: "..."` pattern (or `key:` followed by a quoted value).
        for key in STUDIO_KEYS:
            if not re.search(rf"\b{key}:\s*\"", src):
                missing.append((code, key))
    assert not missing, (
        f"v0.7.203 regression: missing studio.* keys in non-en-US locales: {missing!r}"
    )


def test_studio_page_has_no_hardcoded_english_jsx_strings():
    """v0.7.203 — the Studio render tree must NOT contain hardcoded
    English strings that the user can read. Inline rationale comments
    are fine (start with `// ` or `{/*`) but visible JSX text and
    aria-labels must route through t()."""
    src = _src("frontend/src/app/(dashboard)/studio/page.tsx")

    # The specific English strings the page used to contain. Each
    # one must be GONE from the active source (comments are OK).
    forbidden = [
        "Back to Notebooks",
        "1. Upload documents",
        "2. Pick output mode",
        "Study notebook",
        "Podcast episode",
        "Episode profile",
        "Speaker profile",
        "Pick a profile",
        "Pick speakers",
        "Generating study notebook",
        "Submitting podcast job",
        "Notebook generated",
        "Podcast generation started",
        "Studio generation failed",
        "Generated with warnings",
        "Drop files here or",
    ]
    # Strip comment lines so historical-rationale lines don't false-
    # positive the regex (the file documents pre-v0.7.203 behavior
    # in v0.7.x comments).
    code_only_lines: list[str] = []
    in_block_comment = False
    for ln in src.splitlines():
        stripped = ln.lstrip()
        if stripped.startswith("/*") or stripped.startswith("{/*"):
            in_block_comment = True
        if in_block_comment:
            if "*/" in ln or "*/}" in ln:
                in_block_comment = False
            continue
        if stripped.startswith("//"):
            continue
        code_only_lines.append(ln)
    code_only = "\n".join(code_only_lines)

    offenders = [s for s in forbidden if s in code_only]
    assert not offenders, (
        f"v0.7.203 regression: Studio page reverted some hardcoded "
        f"English strings: {offenders!r}. Non-English users will "
        f"see English on a primary entry point."
    )


def test_studio_page_uses_t_studio_namespace():
    """v0.7.203 — the Studio page must invoke `t('studio.X')` for
    its labels. Pin a few load-bearing keys so an aggressive
    refactor that drops them doesn't silently revert the
    extraction."""
    src = _src("frontend/src/app/(dashboard)/studio/page.tsx")
    # Static keys referenced via `t('studio.X')` directly.
    for key in (
        "studio.title",
        "studio.subtitle",
        "studio.step1Title",
        "studio.notebookModeTitle",
        "studio.generateNotebook",
    ):
        assert f"t('{key}')" in src or f't("{key}")' in src, (
            f"v0.7.203 regression: Studio page no longer references "
            f"t('{key}'). String may have been re-hardcoded."
        )
    # Dynamic keys: `unsupportedType` and `fileTooLarge` are
    # referenced via `t(reason.key)` where `reason.key` is one of
    # the RejectionReason union strings. Pin them via the union
    # declaration instead of a literal t() call.
    for dyn in ("studio.unsupportedType", "studio.fileTooLarge"):
        assert dyn in src, (
            f"v0.7.203 regression: {dyn} no longer appears in the "
            f"Studio page. RejectionReason union may have lost the "
            f"key, leaving the rejection toast untranslated."
        )


def test_studio_isallowed_returns_key_params():
    """v0.7.203 — isAllowed must return a `{key, params}` reason
    object (translated in the caller) instead of a pre-formatted
    English string. Otherwise the rejection reason in the toast
    is hardcoded English."""
    src = _src("frontend/src/app/(dashboard)/studio/page.tsx")
    assert "interface RejectionReason" in src
    assert "key: 'studio.unsupportedType' | 'studio.fileTooLarge'" in src
