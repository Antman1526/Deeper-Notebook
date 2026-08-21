# Final Release Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the completed Deeper Notebook 0.8.114 release reproducible and merge-ready by checking in deterministic default/off package-smoke setup, correcting release truth, removing tracked bytecode, fixing the remaining tracked Ruff issue, and proving the final branch.

**Architecture:** Add a small Python fixture authority that creates isolated provider-none runtime roots from existing configuration and model-download constants, plus a Python runner and CommonJS browser probe that reuse the hardened package-smoke lifecycle. Expose safe staged/installed Make targets, keep receipts machine-readable, and separate repository hygiene/docs commits from behavior changes. Root performs final full gates, fresh review, and local-main integration after the implementation worker returns.

**Tech Stack:** Python 3.12, pytest, Node.js/CommonJS, Playwright, GNU Make, Ruff, Gitleaks, Git.

## Global Constraints

- Active checkout is the repository-relative worktree `<repo>/.worktrees/today-productization` on `codex/today-productization`.
- Preserve `/Applications/Deeper Notebook.app`, its timestamped backup, `dist/`, Task 8 receipts, user data, credentials, and the supplied untracked `.codex/agent-context/today-productization-2026-08-20.md`.
- Never launch staged and installed smoke concurrently; every launch must own, stop, and reap only its own process group.
- Never access non-loopback HTTP(S), download models, call providers, mutate source visuals, install, push, publish, notarize, or rewrite remote history.
- Use `apply_patch` for edits. Do not reset/revert unrelated dirty files.
- Production behavior changes require strict RED then minimal GREEN. Configuration/docs/index cleanup may use static contract REDs.
- Commit each task atomically after focused tests, diff-check, and staged Gitleaks.

---

### Task 1: Deterministic package-smoke fixture authority

**Files:**
- Create: `desktop/build/package_smoke_fixture.py`
- Create: `desktop/tests/test_package_smoke_fixture.py`

**Interfaces:**
- Produces: `SmokeFixture` dataclass with `root`, `home`, `data_dir`, `model_dir`, `readiness_file`, and `environment` fields.
- Produces: `prepare_smoke_fixture(root: Path, *, source_visuals: bool, uv_cache_dir: Path) -> SmokeFixture`.
- Consumes: `desktop.config.Config.save`, `desktop.model_downloads` path/size constants.

- [ ] **Step 1: Write fixture safety and shape tests**

Add tests that require a nonexistent target, reject an existing target and a symlink, require owner-only config/root modes on POSIX, parse the config through `load_or_create`, assert generated secrets differ across fixtures, and assert default/off environment differences are limited to `DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED=0`.

```python
def test_prepare_smoke_fixture_is_private_offline_and_mode_exact(tmp_path: Path) -> None:
    default = prepare_smoke_fixture(
        tmp_path / "default", source_visuals=True, uv_cache_dir=tmp_path / "uv"
    )
    off = prepare_smoke_fixture(
        tmp_path / "off", source_visuals=False, uv_cache_dir=tmp_path / "uv"
    )
    assert load_or_create(default.data_dir / "config.toml").provider == "none"
    assert default.environment["UV_OFFLINE"] == "1"
    assert "DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED" not in default.environment
    assert off.environment["DEEPER_NOTEBOOK_SOURCE_VISUALS_ENABLED"] == "0"
```

- [ ] **Step 2: Run the fixture tests and capture strict RED**

Run: `uv run pytest -q desktop/tests/test_package_smoke_fixture.py`

Expected: collection/import failure because `package_smoke_fixture` does not exist.

- [ ] **Step 3: Implement the minimal fixture helper**

Use `Config(...).save(config_path)` with `secrets.token_urlsafe()` values. Create sparse files with `open(path, "wb").truncate(size)` at current paths. Derive size floors as follows:

```python
MODEL_PLACEHOLDERS = {
    Path(EMBEDDING_GGUF[1]): int(EMBEDDING_GGUF[3] * 0.8 * 1024 * 1024),
    Path(PIPER_VOICE_MODEL[1]): int(PIPER_VOICE_MODEL[3] * 0.8 * 1024 * 1024),
    Path(PIPER_VOICE_CONFIG[1]): 2048,
    Path(PIPER_RYAN_MODEL[1]): int(PIPER_RYAN_MODEL[3] * 0.8 * 1024 * 1024),
    Path(PIPER_RYAN_CONFIG[1]): 2048,
    **{
        Path(FASTER_WHISPER_STT_DIR) / filename: minimum
        for _url, filename, minimum in FASTER_WHISPER_STT_FILES
    },
}
```

The helper must refuse an existing root before creating anything and must never accept a root outside the caller-provided path.

- [ ] **Step 4: Run GREEN and scoped quality gates**

Run:

```bash
uv run pytest -q desktop/tests/test_package_smoke_fixture.py
uv run ruff check desktop/build/package_smoke_fixture.py desktop/tests/test_package_smoke_fixture.py
uv run ruff format --check desktop/build/package_smoke_fixture.py desktop/tests/test_package_smoke_fixture.py
python3 -m compileall -q desktop/build/package_smoke_fixture.py desktop/tests/test_package_smoke_fixture.py
```

Expected: all exit 0.

- [ ] **Step 5: Commit**

```bash
git add desktop/build/package_smoke_fixture.py desktop/tests/test_package_smoke_fixture.py
gitleaks protect --staged --redact
git commit -m "test(desktop): prepare isolated release smoke roots"
```

### Task 2: Serial package and read-only browser proof

**Files:**
- Create: `desktop/build/package_browser_probe.cjs`
- Create: `desktop/build/package_release_smoke.py`
- Create: `desktop/tests/test_package_release_smoke.py`
- Modify: `desktop/tests/test_package_smoke_contract.py`

**Interfaces:**
- Consumes: `prepare_smoke_fixture`, `package_smoke.launch_monitored_process`, `wait_for_readiness`, `stop_process`, and `write_receipt`.
- Produces CLI: `python desktop/build/package_release_smoke.py --executable PATH --artifact PATH --output-root PATH --uv-cache-dir PATH --playwright-module PATH [--expected-artifact-sha256 HEX]`.
- Produces receipts: `<output-root>/default.json` and `<output-root>/source-visuals-off.json`.

- [ ] **Step 1: Write runner/browser contract tests**

Tests must assert default then off serial ordering, no second launch before cleanup, exact two-origin loopback allowlist, GET-only browser requests, all-six-true default expectations, sourceVisuals-only false rollback, usable Sources page, zero visual mutations, receipt-on-failure, and cleanup after browser/child failure.

```python
def test_release_smoke_runs_default_then_off_without_overlap(monkeypatch, tmp_path):
    events = []
    monkeypatch.setattr(release_smoke, "run_mode", lambda mode, *_a, **_k: events.append(mode))
    assert release_smoke.run_release_smoke(arguments_for(tmp_path)) == 0
    assert events == ["default", "source-visuals-off"]
```

Add a static browser contract asserting `allowedOrigins` is exactly frontend and API origin, routes abort any other HTTP(S) origin, and off-mode detects non-GET `/visual` traffic.

- [ ] **Step 2: Run strict RED**

Run: `uv run pytest -q desktop/tests/test_package_release_smoke.py desktop/tests/test_package_smoke_contract.py`

Expected: missing runner/probe contracts fail.

- [ ] **Step 3: Implement the CommonJS probe**

Port the proven Task 8 logic into a generic script. Parse `--mode`, `--frontend-url`, `--api-url`, and `--playwright-module`; require both hosts to equal `127.0.0.1`; use `page.route("**/*")` to abort HTTP(S) outside the exact two origins; emit one JSON object to stdout; and close Chromium in `finally`.

- [ ] **Step 4: Implement the Python serial runner**

Create separate fixture roots per mode, refuse a non-empty output root, verify the artifact/hash before launching, invoke the browser with the repository Playwright module, parse only its JSON receipt, and call `stop_process` in `finally`. Default expected features are all six `true`; off changes only `sourceVisuals` to `false`. Write a top-level summary receipt even if the first mode fails; never start the second mode after a failed first mode.

- [ ] **Step 5: Run GREEN and adjoining lifecycle tests**

Run:

```bash
uv run pytest -q desktop/tests/test_package_release_smoke.py desktop/tests/test_package_smoke_contract.py
uv run ruff check desktop/build/package_release_smoke.py desktop/build/package_smoke_fixture.py desktop/tests/test_package_release_smoke.py desktop/tests/test_package_smoke_contract.py
node --check desktop/build/package_browser_probe.cjs
python3 -m compileall -q desktop/build/package_release_smoke.py
```

Expected: all exit 0.

- [ ] **Step 6: Commit**

```bash
git add desktop/build/package_browser_probe.cjs desktop/build/package_release_smoke.py desktop/tests/test_package_release_smoke.py desktop/tests/test_package_smoke_contract.py
gitleaks protect --staged --redact
git commit -m "test(desktop): automate release browser smoke"
```

### Task 3: Make targets and current release truth

**Files:**
- Modify: `Makefile`
- Modify: `desktop/tests/test_release_manifest.py`
- Modify: `docs/TODO.md`
- Create: `docs/verification/2026-08-21-local-release-smoke.md`

**Interfaces:**
- Produces Make targets: `smoke-release-mac-app` and `smoke-release-installed-mac-app`.
- Consumes caller-owned `RELEASE_SMOKE_EXECUTABLE`, `RELEASE_SMOKE_ARTIFACT`, `RELEASE_SMOKE_OUTPUT_ROOT`, `RELEASE_SMOKE_UV_CACHE_DIR`, `RELEASE_SMOKE_PLAYWRIGHT_MODULE`, and optional expected hash.

- [ ] **Step 1: Add static Make/doc truth tests**

Require both targets, require the installed target to name `/Applications/Deeper Notebook.app` only as an input, and reject `cp`, `ditto`, `rm`, `pkill`, `xattr`, or install dependencies inside the target slice. Require TODO to contain current app/DMG hashes, backup path, and installed/default/off proof rather than “install proof deferred”.

- [ ] **Step 2: Run strict RED**

Run:

```bash
uv run pytest -q desktop/tests/test_release_manifest.py -k 'release_smoke or packaged_v0_8_114'
```

Expected: missing target/current-truth assertions fail.

- [ ] **Step 3: Add Make targets and docs**

Make targets call only `uv run python desktop/build/package_release_smoke.py` with exported/raw paths and no shell-expanded environment payload. Update TODO section 0.3 to current facts:

- installed/staged executable: `e06d908649762446fb08cc6de28ce8470b4ba711296650fdfcca6937fc136475`;
- bundled Surreal: `30babdd7fe6d84187cd2196a01df7c623aa1700dc24e5d229b2703c718315b26`;
- DMG: `92ab2bf32c783bce103c12cb1d81030b8e3da73784a77264afa3ce5dad98678a`;
- backup: `/Applications/Deeper Notebook.app.backup-20260821T085744Z`;
- default/off staged, installed, and browser receipts under the preserved Task 8 root;
- remaining Developer ID/notary, Windows, push/publication gates.

- [ ] **Step 4: Run GREEN and Make dry-runs**

Run:

```bash
uv run pytest -q desktop/tests/test_release_manifest.py -k 'release_smoke or packaged_v0_8_114'
make -n smoke-release-mac-app RELEASE_SMOKE_OUTPUT_ROOT=/tmp/dn-smoke RELEASE_SMOKE_UV_CACHE_DIR=/tmp/uv
make -n smoke-release-installed-mac-app RELEASE_SMOKE_OUTPUT_ROOT=/tmp/dn-smoke RELEASE_SMOKE_UV_CACHE_DIR=/tmp/uv
git diff --check
```

Expected: all exit 0; dry-run contains no mutation command.

- [ ] **Step 5: Commit**

```bash
git add Makefile desktop/tests/test_release_manifest.py docs/TODO.md docs/verification/2026-08-21-local-release-smoke.md
gitleaks protect --staged --redact
git commit -m "docs(release): productize local package proof"
```

### Task 4: Repository hygiene and Ruff cleanup

**Files:**
- Create: `tests/test_repository_hygiene.py`
- Modify: `api/routers/search.py`
- Delete from Git: every tracked `desktop/build/__pycache__/*.pyc`

**Interfaces:**
- Produces invariant: `git ls-files '*.pyc'` returns no paths.

- [ ] **Step 1: Add a tracked-bytecode regression and run RED**

```python
def test_repository_tracks_no_python_bytecode() -> None:
    result = subprocess.run(
        ["git", "ls-files", "*.pyc"], cwd=REPOSITORY_ROOT,
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.splitlines() == []
```

Run: `uv run pytest -q tests/test_repository_hygiene.py`

Expected: FAIL listing the twelve tracked bytecode files.

- [ ] **Step 2: Remove tracked bytecode and fix only import order**

Delete the twelve tracked `.pyc` files with `apply_patch` or exact index-safe file removal. In `api/routers/search.py`, move `from deeper_notebook.search.fusion import reciprocal_rank_fusion` into Ruff-sorted order; change no executable statement.

- [ ] **Step 3: Run GREEN and scoped Ruff**

Run:

```bash
uv run pytest -q tests/test_repository_hygiene.py
test -z "$(git ls-files '*.pyc')"
uv run ruff check api/routers/search.py tests/test_repository_hygiene.py
uv run ruff format --check api/routers/search.py tests/test_repository_hygiene.py
git diff --check
```

Expected: all exit 0.

- [ ] **Step 4: Commit**

```bash
git add api/routers/search.py tests/test_repository_hygiene.py
git add -u desktop/build/__pycache__
gitleaks protect --staged --redact
git commit -m "chore(repo): stop tracking Python bytecode"
```

### Task 5: Worker verification and handoff

**Files:**
- Modify: `.codex/agent-context/final-release-cleanup-2026-08-21.md`
- Modify: `/Users/Antman/.codex/context.md`

- [ ] **Step 1: Run affected suites**

```bash
PYTHONDONTWRITEBYTECODE=1 uv run pytest -q desktop/tests/test_package_smoke_fixture.py desktop/tests/test_package_release_smoke.py desktop/tests/test_package_smoke_contract.py desktop/tests/test_release_manifest.py tests/test_repository_hygiene.py
```

- [ ] **Step 2: Run static and security gates**

```bash
uv run ruff check api deeper_notebook desktop tests --exclude desktop/bin
uv run ruff format --check api deeper_notebook desktop tests --exclude desktop/bin
python3 -m compileall -q api deeper_notebook desktop tests
uv run pytest -q tests/test_product_identity.py
uv run python scripts/rebrand_audit.py --check
git diff --check 7e8fcc49..HEAD
gitleaks git --redact --log-opts='7e8fcc49..HEAD'
```

- [ ] **Step 3: Return evidence to Sol**

Append concise commits, RED/GREEN receipts, changed files, open concerns, and exact worktree status to both supplied context files. Do not merge, push, rebuild, reinstall, remove the backup, or delete preserved receipts.

### Task 6: Root full verification, review, and local-main integration

**Owner:** Sol root only after worker completion.

- [ ] **Step 1: Inspect every commit and verify scope**

Run `git status --short`, `git log --oneline 7e8fcc49..HEAD`, `git diff --stat 7e8fcc49..HEAD`, and inspect the complete diff. Confirm no installed app, backup, receipt, user data, credential, or vendored runtime was changed.

- [ ] **Step 2: Run full release gates**

Run full backend non-integration, real-Surreal integration, frontend Vitest/TypeScript/lint/build, and the serial Visual/System Gallery browser matrices unless current unchanged-component evidence and elapsed cost justify an explicitly documented narrower rerun. Always run package/release focused tests, Ruff, compileall, identity, rebrand, diff-check, and range Gitleaks.

- [ ] **Step 3: Run official staged and installed smoke if preconditions are safe**

Verify no packaged app/Surreal/smoke process is live. Run the new staged target once and installed target once, serially, against the already-built artifacts with fresh output roots. Stop and report an environmental blocker rather than retrying if offline cache or artifact prerequisites are unavailable.

- [ ] **Step 4: Fresh-context review**

Supply the frozen design, plan, `7e8fcc49..HEAD` diff, global context, task context, and test receipts to `sol_reviewer` with no inherited conversation. Resolve every Critical/Important finding with strict RED/GREEN before re-review.

- [ ] **Step 5: Prepare and perform local merge only when safe**

Confirm local `main` is an ancestor of the release branch, its worktree has no overlapping user changes, and no remote action is implied. Merge normally into local `main`; never force, reset, or push. If the merge cannot be proven safe, leave the branch merge-ready and record the exact blocker.

- [ ] **Step 6: Final handoff and goal audit**

Update the Downloads handoff with commits, receipts, installed hashes, rollback paths, local-merge status, and external owners. Audit every design done criterion against current evidence. Mark the goal complete only if all locally actionable work is proven complete and any unperformed local merge has a precise safety blocker.
