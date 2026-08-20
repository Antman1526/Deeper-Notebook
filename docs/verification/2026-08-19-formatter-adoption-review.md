# Formatter adoption — allowlist re-approval review

**2026-08-19 · `ruff format` (701 files) · reviewed before applying**

Every approval below was already granted; `ruff format` re-split its line, so
the recorded text changed by punctuation while its meaning did not. Each row
shows the line as approved and as it now reads. Mapping is by order and is
unambiguous wherever the live occurrence count equals the pinned count.

> **Tokens redacted.** Every legacy identifier quoted below is replaced with
> `«legacy»`. The review's purpose is to show which occurrence moved where and
> that *was* and *now* are the same construct; the literal token adds nothing to
> that, and leaving it in makes this file trip the very audit it documents.


## `api/routers/transformations.py` :: `«legacy»`

live=1 pinned=1 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L131: `submit_command, "«legacy»", "optimize_prompt",`
  - now L136: `"«legacy»",`

## `desktop/launcher.py` :: `«legacy»`

live=5 pinned=5 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L1503: `"--namespace", "«legacy»",`
  - now L1565: `"«legacy»",`
- `compatibility_alias`
  - was L1504: `"--database", "«legacy»",`
  - now L1567: `"«legacy»",`

## `desktop/tests/test_app_migration.py` :: `«legacy»`

live=28 pinned=28 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L475: `applications, "«legacy».app", COMPATIBLE_BUNDLE_ID`
  - now L470: `replacement = _app(applications, "«legacy».app", COMPATIBLE_BUNDLE_ID)`
- `compatibility_alias`
  - was L506: `applications, "«legacy».app", COMPATIBLE_BUNDLE_ID`
  - now L499: `replacement = _app(applications, "«legacy».app", COMPATIBLE_BUNDLE_ID)`

## `desktop/tests/test_data_root_migration.py` :: `«legacy»`

live=2 pinned=2 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L902: `and node.value in {".deeper-notebook", ".«legacy»"}`
  - now L863: `".«legacy»",`

## `desktop/tests/test_launcher_prefs.py` :: `«legacy»`

live=4 pinned=4 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L37: `lambda: tmp_path / ".«legacy»" / "launcher.env")`
  - now L41: `lambda: tmp_path / ".«legacy»" / "launcher.env",`
- `compatibility_alias`
  - was L46: `lambda: tmp_path / ".«legacy»" / "launcher.env")`
  - now L56: `lambda: tmp_path / ".«legacy»" / "launcher.env",`

## `desktop/tests/test_release_manifest.py` :: `«legacy»`

live=7 pinned=7 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L359: `'Type: files; Name: "{autoprograms}\\«legacy».lnk"'`
  - now L359: `shortcut_cleanup = 'Type: files; Name: "{autoprograms}\\«legacy».lnk"'`

## `desktop/tests/test_release_manifest.py` :: `«legacy»`

live=2 pinned=2 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L405: `'"«legacy»" "«legacy»"'`
  - now L403: `'wait_for_pid_visible_window "$legacy_pid" "«legacy»" "«legacy»"'`
- `compatibility_alias`
  - was L405: `'"«legacy»" "«legacy»"'`
  - now L403: `'wait_for_pid_visible_window "$legacy_pid" "«legacy»" "«legacy»"'`

## `desktop/tests/test_window.py` :: `«legacy»`

live=27 pinned=27 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L214: `"window.«legacy»STT_URL = window.DEEPER_NOTEBOOK_STT_URL;"`
  - now L319: `assert "window.«legacy»STT_URL = window.DEEPER_NOTEBOOK_STT_URL;" in js`
- `compatibility_alias`
  - was L234: `"window.«legacy»TTS_URL = window.DEEPER_NOTEBOOK_TTS_URL;"`
  - now L320: `assert "window.«legacy»TTS_URL = window.DEEPER_NOTEBOOK_TTS_URL;" in js`

## `desktop/tests/test_window.py` :: `«legacy»`

live=2 pinned=2 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L370: `"«legacy».app and Deeper Notebook.app both exist."`
  - now L411: `"message": ("«legacy».app and Deeper Notebook.app both exist."),`

## `docs/7-DEVELOPMENT/architecture.md` :: `«legacy»`

live=12 pinned=12 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L606: `app="«legacy»",`
  - now L607: `app="«legacy»", command="process_source", input={...}`

## `docs/superpowers/plans/2026-05-09-«legacy»-desktop.md` :: `«legacy»`

live=53 pinned=53 orphaned=2 unclaimed=2 — **unambiguous**

- `historical_reference`
  - was L1439: `def open_window(url: str, on_close: Callable[[], None], title: str = "«legacy»",`
  - now L1540: `title: str = "«legacy»",`
- `historical_reference`
  - was L1710: `window = webview.create_window("«legacy» — Setup",`
  - now L1836: `"«legacy» — Setup",`

## `docs/superpowers/plans/2026-05-09-«legacy»-desktop.md` :: `«legacy»`

live=19 pinned=19 orphaned=1 unclaimed=1 — **unambiguous**

- `historical_reference`
  - was L1370: `/ ".«legacy»" / "surreal_data"`
  - now L1449: `/ ".«legacy»"`

## `docs/superpowers/plans/2026-05-11-«legacy»-v0.3-implementation.md` :: `«legacy»`

live=13 pinned=13 orphaned=1 unclaimed=1 — **unambiguous**

- `historical_reference`
  - was L2187: `Menu("«legacy»", [`
  - now L2326: `"«legacy»",`

## `docs/superpowers/plans/2026-05-25-local-models-mcp-chat-platform.md` :: `«legacy»`

live=64 pinned=64 orphaned=2 unclaimed=2 — **unambiguous**

- `historical_reference`
  - was L939: `"«legacy».database.repository.repo_query", _q,`
  - now L1026: `"«legacy».database.repository.repo_query",`
- `historical_reference`
  - was L942: `"«legacy».database.repository.repo_upsert", _u,`
  - now L1030: `"«legacy».database.repository.repo_upsert",`

## `docs/superpowers/plans/2026-07-26-deeper-notebook-rebrand.md` :: `«legacy»`

live=48 pinned=48 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L722: `"«legacy»", "deeper_notebook", 1`
  - now L732: `canonical_name = fullname.replace("«legacy»", "deeper_notebook", 1)`

## `scripts/rebrand_audit.py` :: `«legacy»`

live=8 pinned=8 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L1633: `{"«legacy»", "«legacy»"}`
  - now L1581: `if kind == "env_alias" and not set(patterns).issubset({"«legacy»", "«legacy»"}):`

## `scripts/rebrand_audit.py` :: `«legacy»`

live=7 pinned=7 orphaned=2 unclaimed=2 — **unambiguous**

- `migration_documentation`
  - was L86: `("deeper_notebook/logging.py", "«legacy»"): (`
  - now L82: `("deeper_notebook/logging.py", "«legacy»"): ("migration_documentation"),`
- `migration_documentation`
  - was L1633: `{"«legacy»", "«legacy»"}`
  - now L1581: `if kind == "env_alias" and not set(patterns).issubset({"«legacy»", "«legacy»"}):`

## `scripts/rebrand_audit.py` :: `«legacy»`

live=5 pinned=5 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L67: `("tests/test_product_identity.py", "«legacy»"): (`
  - now L67: `("tests/test_product_identity.py", "«legacy»"): ("compatibility_alias"),`

## `scripts/rebrand_audit.py` :: `«legacy»`

live=7 pinned=7 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L78: `("tests/test_task5_brand_namespace.py", "«legacy»"): (`
  - now L76: `("tests/test_task5_brand_namespace.py", "«legacy»"): ("compatibility_alias"),`

## `scripts/rebrand_audit.py` :: `«legacy»`

live=9 pinned=9 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L1197: `and pattern == "«legacy»"`
  - now L1176: `if relative_path == "deeper_notebook/identity.py" and pattern == "«legacy»":`

## `tests/test_environment_aliases.py` :: `«legacy»`

live=50 pinned=50 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L628: `assert normalized["«legacy»METRICS_AUTH_TOKEN_FILE"] == str(`
  - now L620: `assert normalized["«legacy»METRICS_AUTH_TOKEN_FILE"] == str(legacy_path)`
- `compatibility_alias`
  - was L666: `assert normalized["«legacy»METRICS_AUTH_TOKEN_FILE"] == str(`
  - now L656: `assert normalized["«legacy»METRICS_AUTH_TOKEN_FILE"] == str(legacy_path)`

## `tests/test_podcast_suggest.py` :: `«legacy»`

live=5 pinned=5 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L123: `"«legacy» Local", "Deep Dive", "Quick Brief",`
  - now L254: `"«legacy» Local",`
- `compatibility_alias`
  - was L328: `"Quick Brief", "«legacy» Local"`
  - now L344: `assert body["episode_profile_name"] in {"Quick Brief", "«legacy» Local"}`

## `tests/test_product_identity.py` :: `«legacy»`

live=60 pinned=60 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L2448: `'{"pattern": "«legacy»"}\n'`
  - now L2369: `"scripts/rebrand-allowlist.json": ('{"pattern": "«legacy»"}\n'),`

## `tests/test_product_identity.py` :: `«legacy»`

live=13 pinned=13 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L2432: `and match["path"] == "legacy/«legacy».txt"`
  - now L2354: `match["source"] == "path" and match["path"] == "legacy/«legacy».txt"`

## `tests/test_product_identity.py` :: `«legacy»`

live=51 pinned=51 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L2507: `'legacy_module = «legacy»; submit_command('`
  - now L2426: `line = 'legacy_module = «legacy»; submit_command("«legacy»", "work", {})'`
- `compatibility_alias`
  - was L2508: `'"«legacy»", "work", {})'`
  - now L2426: `line = 'legacy_module = «legacy»; submit_command("«legacy»", "work", {})'`

## `tests/test_task6_active_product.py` :: `«legacy»`

live=5 pinned=1 orphaned=1 unclaimed=5 — **AMBIGUOUS, deferred**

- `compatibility_alias`
  - was L177: `r"«legacy»|Open notebook\+|«legacy»\+"`
  - now L104: `assert "«legacy»" not in source, relative_path`

## `tests/test_task6_active_product.py` :: `«legacy»`

live=4 pinned=4 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L177: `r"«legacy»|Open notebook\+|«legacy»\+"`
  - now L176: `stale = re.compile(r"«legacy»|Open notebook\+|«legacy»\+")`

## `tests/test_v0_7_210_version_and_reaper.py` :: `«legacy»`

live=3 pinned=3 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L112: `"return bridge.DEEPER_NOTEBOOK_VERSION || bridge.«legacy»VERSION"`
  - now L112: `assert "return bridge.DEEPER_NOTEBOOK_VERSION || bridge.«legacy»VERSION" in bridge`

---

**39 re-approvals proposed · 1 deferred as ambiguous**
