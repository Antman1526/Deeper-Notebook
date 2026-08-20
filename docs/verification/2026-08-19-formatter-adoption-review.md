# Formatter adoption — allowlist re-approval review

**2026-08-19 · `ruff format` (701 files) · reviewed before applying**

Every approval below was already granted; `ruff format` re-split its line, so
the recorded text changed by punctuation while its meaning did not. Each row
shows the line as approved and as it now reads. Mapping is by order and is
unambiguous wherever the live occurrence count equals the pinned count.


## `api/routers/transformations.py` :: `open_notebook`

live=1 pinned=1 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L131: `submit_command, "open_notebook", "optimize_prompt",`
  - now L136: `"open_notebook",`

## `desktop/launcher.py` :: `open_notebook`

live=5 pinned=5 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L1503: `"--namespace", "open_notebook",`
  - now L1565: `"open_notebook",`
- `compatibility_alias`
  - was L1504: `"--database", "open_notebook",`
  - now L1567: `"open_notebook",`

## `desktop/tests/test_app_migration.py` :: `Open Notebook Plus`

live=28 pinned=28 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L475: `applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID`
  - now L470: `replacement = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)`
- `compatibility_alias`
  - was L506: `applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID`
  - now L499: `replacement = _app(applications, "Open Notebook Plus.app", COMPATIBLE_BUNDLE_ID)`

## `desktop/tests/test_data_root_migration.py` :: `open-notebook-plus`

live=2 pinned=2 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L902: `and node.value in {".deeper-notebook", ".open-notebook-plus"}`
  - now L863: `".open-notebook-plus",`

## `desktop/tests/test_launcher_prefs.py` :: `open-notebook-plus`

live=4 pinned=4 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L37: `lambda: tmp_path / ".open-notebook-plus" / "launcher.env")`
  - now L41: `lambda: tmp_path / ".open-notebook-plus" / "launcher.env",`
- `compatibility_alias`
  - was L46: `lambda: tmp_path / ".open-notebook-plus" / "launcher.env")`
  - now L56: `lambda: tmp_path / ".open-notebook-plus" / "launcher.env",`

## `desktop/tests/test_release_manifest.py` :: `Open Notebook Plus`

live=7 pinned=7 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L359: `'Type: files; Name: "{autoprograms}\\Open Notebook Plus.lnk"'`
  - now L359: `shortcut_cleanup = 'Type: files; Name: "{autoprograms}\\Open Notebook Plus.lnk"'`

## `desktop/tests/test_release_manifest.py` :: `Open notebook+`

live=2 pinned=2 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L405: `'"Open notebook+" "Open notebook+"'`
  - now L403: `'wait_for_pid_visible_window "$legacy_pid" "Open notebook+" "Open notebook+"'`
- `compatibility_alias`
  - was L405: `'"Open notebook+" "Open notebook+"'`
  - now L403: `'wait_for_pid_visible_window "$legacy_pid" "Open notebook+" "Open notebook+"'`

## `desktop/tests/test_window.py` :: `ONP_`

live=27 pinned=27 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L214: `"window.ONP_STT_URL = window.DEEPER_NOTEBOOK_STT_URL;"`
  - now L319: `assert "window.ONP_STT_URL = window.DEEPER_NOTEBOOK_STT_URL;" in js`
- `compatibility_alias`
  - was L234: `"window.ONP_TTS_URL = window.DEEPER_NOTEBOOK_TTS_URL;"`
  - now L320: `assert "window.ONP_TTS_URL = window.DEEPER_NOTEBOOK_TTS_URL;" in js`

## `desktop/tests/test_window.py` :: `Open Notebook Plus`

live=2 pinned=2 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L370: `"Open Notebook Plus.app and Deeper Notebook.app both exist."`
  - now L411: `"message": ("Open Notebook Plus.app and Deeper Notebook.app both exist."),`

## `docs/7-DEVELOPMENT/architecture.md` :: `open_notebook`

live=12 pinned=12 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L606: `app="open_notebook",`
  - now L607: `app="open_notebook", command="process_source", input={...}`

## `docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md` :: `open-notebook-Plus`

live=53 pinned=53 orphaned=2 unclaimed=2 — **unambiguous**

- `historical_reference`
  - was L1439: `def open_window(url: str, on_close: Callable[[], None], title: str = "open-notebook-Plus",`
  - now L1540: `title: str = "open-notebook-Plus",`
- `historical_reference`
  - was L1710: `window = webview.create_window("open-notebook-Plus — Setup",`
  - now L1836: `"open-notebook-Plus — Setup",`

## `docs/superpowers/plans/2026-05-09-open-notebook-plus-desktop.md` :: `open-notebook-plus`

live=19 pinned=19 orphaned=1 unclaimed=1 — **unambiguous**

- `historical_reference`
  - was L1370: `/ ".open-notebook-plus" / "surreal_data"`
  - now L1449: `/ ".open-notebook-plus"`

## `docs/superpowers/plans/2026-05-11-open-notebook-plus-v0.3-implementation.md` :: `Open Notebook Plus`

live=13 pinned=13 orphaned=1 unclaimed=1 — **unambiguous**

- `historical_reference`
  - was L2187: `Menu("Open Notebook Plus", [`
  - now L2326: `"Open Notebook Plus",`

## `docs/superpowers/plans/2026-05-25-local-models-mcp-chat-platform.md` :: `open_notebook`

live=64 pinned=64 orphaned=2 unclaimed=2 — **unambiguous**

- `historical_reference`
  - was L939: `"open_notebook.database.repository.repo_query", _q,`
  - now L1026: `"open_notebook.database.repository.repo_query",`
- `historical_reference`
  - was L942: `"open_notebook.database.repository.repo_upsert", _u,`
  - now L1030: `"open_notebook.database.repository.repo_upsert",`

## `docs/superpowers/plans/2026-07-26-deeper-notebook-rebrand.md` :: `open_notebook`

live=48 pinned=48 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L722: `"open_notebook", "deeper_notebook", 1`
  - now L732: `canonical_name = fullname.replace("open_notebook", "deeper_notebook", 1)`

## `scripts/rebrand_audit.py` :: `ONP_`

live=8 pinned=8 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L1633: `{"OPEN_NOTEBOOK_", "ONP_"}`
  - now L1581: `if kind == "env_alias" and not set(patterns).issubset({"OPEN_NOTEBOOK_", "ONP_"}):`

## `scripts/rebrand_audit.py` :: `OPEN_NOTEBOOK_`

live=7 pinned=7 orphaned=2 unclaimed=2 — **unambiguous**

- `migration_documentation`
  - was L86: `("deeper_notebook/logging.py", "OPEN_NOTEBOOK_"): (`
  - now L82: `("deeper_notebook/logging.py", "OPEN_NOTEBOOK_"): ("migration_documentation"),`
- `migration_documentation`
  - was L1633: `{"OPEN_NOTEBOOK_", "ONP_"}`
  - now L1581: `if kind == "env_alias" and not set(patterns).issubset({"OPEN_NOTEBOOK_", "ONP_"}):`

## `scripts/rebrand_audit.py` :: `OpenNotebook`

live=5 pinned=5 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L67: `("tests/test_product_identity.py", "OpenNotebook"): (`
  - now L67: `("tests/test_product_identity.py", "OpenNotebook"): ("compatibility_alias"),`

## `scripts/rebrand_audit.py` :: `onp-theme`

live=7 pinned=7 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L78: `("tests/test_task5_brand_namespace.py", "onp-theme"): (`
  - now L76: `("tests/test_task5_brand_namespace.py", "onp-theme"): ("compatibility_alias"),`

## `scripts/rebrand_audit.py` :: `open_notebook`

live=9 pinned=9 orphaned=1 unclaimed=1 — **unambiguous**

- `migration_documentation`
  - was L1197: `and pattern == "open_notebook"`
  - now L1176: `if relative_path == "deeper_notebook/identity.py" and pattern == "open_notebook":`

## `tests/test_environment_aliases.py` :: `OPEN_NOTEBOOK_`

live=50 pinned=50 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L628: `assert normalized["OPEN_NOTEBOOK_METRICS_AUTH_TOKEN_FILE"] == str(`
  - now L620: `assert normalized["OPEN_NOTEBOOK_METRICS_AUTH_TOKEN_FILE"] == str(legacy_path)`
- `compatibility_alias`
  - was L666: `assert normalized["OPEN_NOTEBOOK_METRICS_AUTH_TOKEN_FILE"] == str(`
  - now L656: `assert normalized["OPEN_NOTEBOOK_METRICS_AUTH_TOKEN_FILE"] == str(legacy_path)`

## `tests/test_podcast_suggest.py` :: `Open Notebook Plus`

live=5 pinned=5 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L123: `"Open Notebook Plus Local", "Deep Dive", "Quick Brief",`
  - now L254: `"Open Notebook Plus Local",`
- `compatibility_alias`
  - was L328: `"Quick Brief", "Open Notebook Plus Local"`
  - now L344: `assert body["episode_profile_name"] in {"Quick Brief", "Open Notebook Plus Local"}`

## `tests/test_product_identity.py` :: `Open Notebook Plus`

live=60 pinned=60 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L2448: `'{"pattern": "Open Notebook Plus"}\n'`
  - now L2369: `"scripts/rebrand-allowlist.json": ('{"pattern": "Open Notebook Plus"}\n'),`

## `tests/test_product_identity.py` :: `open-notebook-plus`

live=13 pinned=13 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L2432: `and match["path"] == "legacy/open-notebook-plus.txt"`
  - now L2354: `match["source"] == "path" and match["path"] == "legacy/open-notebook-plus.txt"`

## `tests/test_product_identity.py` :: `open_notebook`

live=51 pinned=51 orphaned=2 unclaimed=2 — **unambiguous**

- `compatibility_alias`
  - was L2507: `'legacy_module = open_notebook; submit_command('`
  - now L2426: `line = 'legacy_module = open_notebook; submit_command("open_notebook", "work", {})'`
- `compatibility_alias`
  - was L2508: `'"open_notebook", "work", {})'`
  - now L2426: `line = 'legacy_module = open_notebook; submit_command("open_notebook", "work", {})'`

## `tests/test_task6_active_product.py` :: `Open Notebook`

live=5 pinned=1 orphaned=1 unclaimed=5 — **AMBIGUOUS, deferred**

- `compatibility_alias`
  - was L177: `r"Open Notebook Plus|Open notebook\+|Open Notebook\+"`
  - now L104: `assert "Open Notebook Plus" not in source, relative_path`

## `tests/test_task6_active_product.py` :: `Open Notebook Plus`

live=4 pinned=4 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L177: `r"Open Notebook Plus|Open notebook\+|Open Notebook\+"`
  - now L176: `stale = re.compile(r"Open Notebook Plus|Open notebook\+|Open Notebook\+")`

## `tests/test_v0_7_210_version_and_reaper.py` :: `ONP_`

live=3 pinned=3 orphaned=1 unclaimed=1 — **unambiguous**

- `compatibility_alias`
  - was L112: `"return bridge.DEEPER_NOTEBOOK_VERSION || bridge.ONP_VERSION"`
  - now L112: `assert "return bridge.DEEPER_NOTEBOOK_VERSION || bridge.ONP_VERSION" in bridge`

---

**39 re-approvals proposed · 1 deferred as ambiguous**
