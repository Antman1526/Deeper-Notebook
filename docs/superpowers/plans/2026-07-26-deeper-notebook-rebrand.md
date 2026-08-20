# Deeper Notebook Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand Open Notebook Plus as Deeper Notebook across the source tree, native applications, frontend, backend metadata, exports, configuration, repository links, and release artifacts without losing existing user data or breaking upgrade continuity.

**Architecture:** Establish one canonical identity contract, migrate active code to the `deeper_notebook` package, retain narrowly tested legacy aliases, and route all desktop state through a guarded data-root resolver. Visible branding and release packaging then consume the same identity values. A repository audit classifies every remaining legacy string so upstream history, persisted IDs, and compatibility contracts are preserved deliberately rather than by accident.

**Tech Stack:** Python 3.11-3.12, FastAPI, Pydantic v2, SurrealDB, PyInstaller, pywebview, Inno Setup, Next.js 15, React 19, TypeScript 5, Vitest, pytest, GitHub Actions.

**Depends on:** Approved design in `docs/superpowers/specs/2026-07-26-deeper-notebook-rebrand-design.md`.

---

## Global Constraints

- Preserve the existing Inno Setup `AppId` value `{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}`.
- Preserve the SurrealDB namespace/database `open_notebook`, persisted record IDs, and queued surreal-command application IDs until a separate data migration exists.
- Preserve accurate `lfnovo/open-notebook` upstream references and historical changelog/release references.
- Canonical environment variables win over legacy aliases. Never log secret values.
- Never merge two non-equivalent data roots automatically.
- Never delete the legacy data root during migration or rollback.
- Do not rename the local checkout directory while a service is using it.
- Do not regenerate dependency lockfiles merely because a product string appears in historical metadata.
- Complete native Windows build proof on a Windows host; macOS cannot prove a Windows launch.

## File Map

**Create**

- `deeper_notebook/__init__.py`: canonical package entry point.
- `deeper_notebook/identity.py`: canonical product, repository, namespace, and compatibility constants.
- `deeper_notebook/environment.py`: canonical/legacy environment resolution.
- `open_notebook/__init__.py`: deprecated compatibility package after the package move.
- `desktop/data_root.py`: data-root classification, receipt, migration, and recovery contract.
- `brand/deeper-notebook-mark.svg`: canonical Notebook Spark vector.
- `scripts/rebrand_audit.py`: classified legacy-name inventory.
- `scripts/rebrand-allowlist.json`: exact compatibility/upstream/history allowlist.
- `open_notebook/_alias.py`: complete legacy-submodule import alias finder.
- `tests/fixtures/legacy_import_modules.txt`: every legacy module path imported by the pre-move tree.
- `tests/test_product_identity.py`
- `tests/test_environment_aliases.py`
- `tests/test_python_import_compatibility.py`
- `desktop/tests/test_data_root_migration.py`
- `desktop/app_migration.py`
- `desktop/tests/test_app_migration.py`
- `frontend/src/lib/brand.ts`
- `frontend/src/lib/brand.test.ts`

**Move**

- `open_notebook/**` implementation modules to `deeper_notebook/**`.
- `api/routers/onp.py` to `api/routers/deeper_notebook.py`.
- `frontend/src/lib/api/onp.ts` to `frontend/src/lib/api/deeper-notebook.ts`.
- `frontend/src/components/onp/` to `frontend/src/components/deeper-notebook/`.
- `desktop/build/open-notebook-plus.iss` to `desktop/build/deeper-notebook.iss`.

**Modify**

- All Python imports that reference the product package.
- `pyproject.toml`
- `desktop/config.py`
- `desktop/paths.py`
- `desktop/bootstrap.py`
- `desktop/launcher.py`
- `desktop/launcher_prefs.py`
- `desktop/singleton.py`
- `desktop/window.py`
- `desktop/__main__.py`
- `desktop/model_manager/server.py`
- `desktop/memory_dashboard/server.py`
- `api/main.py`
- `api/updates_service.py`
- `deeper_notebook/logging.py`
- `deeper_notebook/config.py`
- `deeper_notebook/studio/generation/persistence.py`
- `deeper_notebook/studio/exporters/documents.py`
- `deeper_notebook/studio/exporters/spreadsheets.py`
- `frontend/src/app/layout.tsx`
- `frontend/src/app/globals.css`
- `frontend/src/app/(dashboard)/page.tsx`
- `frontend/src/components/intro/IntroReveal.tsx`
- `frontend/src/components/layout/AppSidebar.tsx`
- All `frontend/src/lib/locales/*/index.ts`
- `desktop/build/pyinstaller.spec`
- `desktop/build/post_build_mac.sh`
- `desktop/build/post_build_windows.ps1`
- `desktop/build/build_windows.ps1`
- `.github/workflows/build-desktop.yml`
- `.github/workflows/build-windows.yml`
- Active downstream documentation and support links.

---

### Task 1: Define the Canonical Identity and Legacy Inventory Contract

**Files:**

- Create: `deeper_notebook/__init__.py`
- Create: `deeper_notebook/identity.py`
- Create: `scripts/rebrand_audit.py`
- Create: `scripts/rebrand-allowlist.json`
- Create: `tests/test_product_identity.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing identity tests**

```python
from deeper_notebook.identity import (
    API_NAMESPACE,
    DATA_DIR_NAME,
    LEGACY_API_NAMESPACE,
    LEGACY_DATA_DIR_NAME,
    PRODUCT_NAME,
    REPOSITORY,
    TAGLINE,
)


def test_canonical_product_identity():
    assert PRODUCT_NAME == "Deeper Notebook"
    assert TAGLINE == "Think further with every source"
    assert REPOSITORY == "Antman1526/Deeper-Notebook"
    assert DATA_DIR_NAME == ".deeper-notebook"
    assert API_NAMESPACE == "/api/deeper-notebook"


def test_legacy_identity_is_explicitly_compatibility_only():
    assert LEGACY_DATA_DIR_NAME == ".open-notebook-plus"
    assert LEGACY_API_NAMESPACE == "/api/onp"
```

- [ ] **Step 2: Run the test and confirm RED**

Run: `uv run pytest tests/test_product_identity.py -q`

Expected: collection fails because `deeper_notebook.identity` does not exist.

- [ ] **Step 3: Implement the identity module**

```python
"""Canonical Deeper Notebook product identity."""

PRODUCT_NAME = "Deeper Notebook"
PRODUCT_SLUG = "deeper-notebook"
TAGLINE = "Think further with every source"
REPOSITORY_OWNER = "Antman1526"
REPOSITORY_NAME = "Deeper-Notebook"
REPOSITORY = f"{REPOSITORY_OWNER}/{REPOSITORY_NAME}"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
DATA_DIR_NAME = ".deeper-notebook"
LEGACY_DATA_DIR_NAME = ".open-notebook-plus"
API_NAMESPACE = "/api/deeper-notebook"
LEGACY_API_NAMESPACE = "/api/onp"
PYTHON_DISTRIBUTION = "deeper-notebook"
PYTHON_PACKAGE = "deeper_notebook"
LEGACY_PYTHON_PACKAGE = "open_notebook"
MAC_APP_NAME = "Deeper Notebook.app"
WINDOWS_EXE_NAME = "Deeper Notebook.exe"
WINDOWS_INSTALLER_NAME = "Deeper-Notebook-Setup-x64.exe"
```

`deeper_notebook/__init__.py` exports `PRODUCT_NAME`, `TAGLINE`, and `__version__` only; it must not import database or model modules at package import time. `deeper_notebook.__version__` is the Python distribution/server version from `pyproject.toml` (`1.8.5` at plan creation). `desktop.__version__` remains the independent native desktop release version (`0.8.95` at plan creation).

- [ ] **Step 4: Add a classified legacy-name audit**

The script scans tracked text files and tracked path names (`git ls-files -z`), ignores binary contents, and emits JSON with these categories:

```python
CATEGORIES = (
    "compatibility_alias",
    "upstream_reference",
    "historical_reference",
    "migration_documentation",
    "unexpected_active_identity",
)
PATTERNS = (
    "Open Notebook Plus",
    "Open Notebook",
    "Open notebook+",
    "OpenNotebook",
    "open-notebook-Plus",
    "open-notebook-plus",
    "open_notebook",
    "OPEN_NOTEBOOK_",
    "ONP_",
    "/onp/",
    "onpFetch",
    "--onp-",
    "components/onp",
    "/api/onp",
)
```

The allowlist contains exact path plus pattern plus category records. It may use a trailing `/**` only for `docs/superpowers/specs`, `docs/superpowers/plans`, and upstream documentation directories. `--check` exits non-zero when any result is `unexpected_active_identity` or an allowlist entry no longer matches.

- [ ] **Step 5: Add audit classifier tests**

Test the classifier independently of the still-unrebranded working tree:

```python
def test_audit_distinguishes_compatibility_from_active_branding():
    allowlist = {
        (
            "desktop/build/deeper-notebook.iss",
            "AppId={{572C65B3",
        ): "compatibility_alias"
    }
    assert (
        classify_match(
            "desktop/build/deeper-notebook.iss",
            "AppId={{572C65B3",
            allowlist,
        )
        == "compatibility_alias"
    )
    assert (
        classify_match(
            "frontend/src/app/layout.tsx",
            "Open Notebook Plus",
            allowlist,
        )
        == "unexpected_active_identity"
    )
```

Seed the allowlist only with known compatibility data: Surreal namespace/database values, surreal-command app IDs, the stable Windows installer GUID context, historical specs/changelogs, and accurate `lfnovo/open-notebook` references. Do not allowlist active UI, package metadata, artifact names, update URLs, or downstream support links.

- [ ] **Step 6: Make the Python distribution canonical**

Update `pyproject.toml`:

```toml
[project]
name = "deeper-notebook"
description = "Local-first, source-grounded research and personal knowledge workspace"

[tool.setuptools.packages.find]
include = ["deeper_notebook*", "open_notebook*"]
```

Do not change the existing upstream/container version track in this task.
Regenerate `uv.lock` so the editable root distribution is canonical, and prove
editable and wheel metadata:

```bash
uv lock
uv sync --locked
uv build
unzip -p dist/deeper_notebook-1.8.5-py3-none-any.whl '*/METADATA' | grep '^Name: deeper-notebook$'
```

- [ ] **Step 7: Run focused checks**

Run:

```bash
uv run pytest tests/test_product_identity.py -q
uv run ruff check deeper_notebook/identity.py tests/test_product_identity.py scripts/rebrand_audit.py
```

Expected: tests pass; the audit may still report active legacy identity until later tasks, so temporarily run it without `--check` and save the baseline count in the commit message.

- [ ] **Step 8: Commit**

```bash
git add deeper_notebook pyproject.toml uv.lock scripts/rebrand_audit.py scripts/rebrand-allowlist.json tests/test_product_identity.py
git commit -m "feat(brand): define Deeper Notebook identity contract"
```

---

### Task 2: Add Canonical Environment Variables with Deterministic Legacy Aliases

**Files:**

- Create: `deeper_notebook/environment.py`
- Create: `tests/test_environment_aliases.py`
- Modify: `api/main.py`
- Modify: `api/routers/gmail.py`
- Modify: Gmail integration components and OAuth callback tests.
- Modify: `desktop/launcher.py`
- Modify: `desktop/launcher_prefs.py`
- Modify: all active Python runtime modules that directly read `OPEN_NOTEBOOK_*` or `ONP_*`.
- Modify: `.env.example`
- Modify: `docs/5-CONFIGURATION/onp-env-reference.md`

- [ ] **Step 1: Write failing precedence and redaction tests**

```python
from deeper_notebook.environment import normalize_product_environment, resolve_env


def test_canonical_long_name_wins(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_PASSWORD", "canonical")
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "legacy")
    assert resolve_env("DEEPER_NOTEBOOK_PASSWORD") == "canonical"


def test_legacy_long_name_remains_accepted(monkeypatch):
    monkeypatch.delenv("DEEPER_NOTEBOOK_PASSWORD", raising=False)
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "legacy")
    assert resolve_env("DEEPER_NOTEBOOK_PASSWORD") == "legacy"


def test_short_name_precedence(monkeypatch):
    monkeypatch.setenv("DEEPER_NOTEBOOK_DB_POOL_SIZE", "16")
    monkeypatch.setenv("DN_DB_POOL_SIZE", "8")
    monkeypatch.setenv("OPEN_NOTEBOOK_DB_POOL_SIZE", "6")
    monkeypatch.setenv("ONP_DB_POOL_SIZE", "4")
    normalized = normalize_product_environment(dict(os.environ))
    assert normalized["DEEPER_NOTEBOOK_DB_POOL_SIZE"] == "16"
    assert normalized["DN_DB_POOL_SIZE"] == "16"
    assert normalized["OPEN_NOTEBOOK_DB_POOL_SIZE"] == "16"
    assert normalized["ONP_DB_POOL_SIZE"] == "16"


def test_receipt_never_contains_secret_value(monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_ENCRYPTION_KEY", "do-not-log-me")
    _, receipt = resolve_env("DEEPER_NOTEBOOK_ENCRYPTION_KEY", with_receipt=True)
    assert receipt.winner == "OPEN_NOTEBOOK_ENCRYPTION_KEY"
    assert "do-not-log-me" not in repr(receipt)
```

- [ ] **Step 2: Run and confirm RED**

Run: `uv run pytest tests/test_environment_aliases.py -q`

Expected: collection fails because the resolver does not exist.

- [ ] **Step 3: Implement one resolver**

```python
@dataclass(frozen=True)
class SettingAliases:
    canonical: str
    canonical_short: str | None = None
    legacy: str | None = None
    legacy_short: str | None = None

    @property
    def precedence(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in (
                self.canonical,
                self.canonical_short,
                self.legacy,
                self.legacy_short,
            )
            if name is not None
        )


SETTINGS = {
    "DEEPER_NOTEBOOK_DB_POOL_SIZE": SettingAliases(
        canonical="DEEPER_NOTEBOOK_DB_POOL_SIZE",
        canonical_short="DN_DB_POOL_SIZE",
        legacy="OPEN_NOTEBOOK_DB_POOL_SIZE",
        legacy_short="ONP_DB_POOL_SIZE",
    ),
    "DEEPER_NOTEBOOK_PASSWORD": SettingAliases(
        canonical="DEEPER_NOTEBOOK_PASSWORD",
        legacy="OPEN_NOTEBOOK_PASSWORD",
    ),
}


def resolve_env(
    canonical: str,
    default: str | None = None,
    *,
    getter: Callable[[str], str | None] = os.environ.get,
    with_receipt: bool = False,
):
    aliases = SETTINGS[canonical]
    values = {name: getter(name) for name in aliases.precedence}
    winner = next(
        (name for name in aliases.precedence if values[name] is not None),
        None,
    )
    value = values[winner] if winner is not None else default
    receipt = EnvResolution(
        canonical=canonical,
        winner=winner,
        used_legacy=winner in {aliases.legacy, aliases.legacy_short},
    )
    return (value, receipt) if with_receipt else value
```

Register every supported setting once. `normalize_product_environment()` mirrors the winning value into all assigned aliases for the current child-process environment. It emits at most one warning per legacy key and never prints values. Tests cover all four precedence positions, conflicts, deliberately empty values, missing values, `_FILE` secret getters, and child-process mirroring.

- [ ] **Step 4: Normalize before importing runtime services**

Call normalization:

- At the top of the desktop launcher before subprocess environments are built.
- At API startup before authentication, logging, credentials, model routing, or database configuration reads environment variables.
- In the surreal-command worker bootstrap before importing command modules.

Canonical names are documented first. Legacy names are labeled deprecated and remain functional.

- [ ] **Step 5: Move active runtime reads to canonical names**

Mechanically replace active product-owned reads:

- `OPEN_NOTEBOOK_<NAME>` -> `DEEPER_NOTEBOOK_<NAME>`
- `ONP_<NAME>` -> `DN_<NAME>`

Each runtime setting calls `resolve_env()` rather than reading both names itself. Secret settings pass the existing file-aware secret getter:

```python
encryption_key = resolve_env(
    "DEEPER_NOTEBOOK_ENCRYPTION_KEY",
    getter=get_secret_from_env,
)
```

Child-process environments contain canonical keys plus the normalized legacy
mirrors required by upstream/old workers. Add a guard test that fails when
production Python directly reads a legacy key outside
`deeper_notebook/environment.py`.

- [ ] **Step 6: Update launcher preference whitelist**

Add canonical keys and retain legacy keys:

```python
ALLOWED_KEYS = frozenset(
    {
        "DEEPER_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH",
        "DEEPER_NOTEBOOK_LOCAL_DRAFT_N_PREDICT",
        "DEEPER_NOTEBOOK_LOCAL_N_CTX",
        "DN_CHAT_LLM_CTX",
        "DN_CHAT_LLM_CTX_MAX",
        "OPEN_NOTEBOOK_LOCAL_DRAFT_MODEL_PATH",
        "OPEN_NOTEBOOK_LOCAL_DRAFT_N_PREDICT",
        "OPEN_NOTEBOOK_LOCAL_N_CTX",
        "ONP_CHAT_LLM_CTX",
        "ONP_CHAT_LLM_CTX_MAX",
    }
)
```

When both aliases occur in `launcher.env`, write only the canonical winner back.

- [ ] **Step 7: Run focused tests**

Run:

```bash
uv run pytest tests/test_environment_aliases.py desktop/tests/test_launcher_prefs.py tests/test_credentials_api.py tests/test_db_pool.py -q
uv run ruff check deeper_notebook/environment.py tests/test_environment_aliases.py
```

- [ ] **Step 8: Commit**

```bash
git add deeper_notebook/environment.py tests/test_environment_aliases.py api/main.py desktop/launcher.py desktop/launcher_prefs.py .env.example docs/5-CONFIGURATION/onp-env-reference.md
git commit -m "feat(config): accept Deeper Notebook environment names"
```

---

### Task 3: Implement Guarded Desktop Data-Root Migration

**Files:**

- Create: `desktop/data_root.py`
- Create: `desktop/tests/test_data_root_migration.py`
- Modify: `desktop/config.py`
- Modify: `desktop/bootstrap.py`
- Modify: `desktop/launcher.py`
- Modify: `desktop/launcher_prefs.py`
- Modify: `desktop/singleton.py`
- Modify: `desktop/window.py`
- Modify: `desktop/__main__.py`
- Modify: `desktop/model_manager/server.py`
- Modify: `desktop/memory_dashboard/server.py`
- Modify: `api/updates_service.py`
- Modify: `open_notebook/logging.py` (moved to `deeper_notebook/logging.py` in Task 4)

- [ ] **Step 1: Write failing state-classification tests**

Cover all five filesystem states:

```python
@pytest.mark.parametrize(
    ("canonical_exists", "legacy_exists", "expected"),
    [
        (False, False, "not-needed"),
        (True, False, "ready"),
        (False, True, "migration-pending"),
        (True, True, "ready"),
    ],
)
def test_classifies_roots(tmp_path, canonical_exists, legacy_exists, expected):
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    if canonical_exists:
        canonical.mkdir()
    if legacy_exists:
        legacy.mkdir()
    assert classify_roots(canonical, legacy).state == expected


def test_non_equivalent_roots_are_conflict(tmp_path):
    canonical = tmp_path / ".deeper-notebook"
    legacy = tmp_path / ".open-notebook-plus"
    (canonical / "config.toml").parent.mkdir(parents=True)
    (legacy / "config.toml").parent.mkdir(parents=True)
    (canonical / "config.toml").write_text("theme='dark'")
    (legacy / "config.toml").write_text("theme='light-blue'")
    assert classify_roots(canonical, legacy).state == "migration-conflict"
```

- [ ] **Step 2: Write failing migration safety tests**

Tests must prove:

- Legacy-only same-volume migration uses `os.replace`.
- Receipt is written outside both roots before the move.
- Critical hashes match after migration.
- A non-empty conflicting canonical root is never replaced.
- A failed validation returns `migration-failed` and leaves the legacy root.
- Re-running after success is idempotent.
- A legacy symlink that resolves to the canonical root classifies as `ready`.
- Failure to create a compatibility symlink is recorded but does not invalidate a verified migration.
- Receipt JSON contains paths and hashes but no file contents or secret values.
- Lock contention returns `migration-deferred`.
- The lock records PID, host, process start time, and migration ID.
- A verified-dead stale lock is recoverable; an unknown/live owner is never reclaimed.
- Injected failure after receipt creation, rename, validation, link creation, or receipt finalization restores the legacy path.
- Receipt files and their parent directory are flushed with `fsync` before any irreversible transition is reported.

- [ ] **Step 3: Implement the contract**

Use immutable result types:

```python
MigrationState = Literal[
    "not-needed",
    "ready",
    "migration-pending",
    "migration-deferred",
    "migration-conflict",
    "migration-failed",
    "rollback-available",
]


@dataclass(frozen=True)
class DataRootDecision:
    state: MigrationState
    active_root: Path
    canonical_root: Path
    legacy_root: Path
    receipt_path: Path | None = None
    reason_code: str | None = None
```

Critical files are `config.toml`, `launcher.env`, `update_state.json`, `data/**`, and `venv/.lock-hash`. Hash regular files only; reject symlinks in critical paths. Use `flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY` and acquire the exclusive lock with `os.open(lock_path, flags, 0o600)`. The JSON lock payload contains PID, hostname, process start time, migration ID, and creation time. Reclaim only when the same-host PID is confirmed absent or its start time differs; otherwise defer.

Migration flow:

1. Write a `started` receipt under `~/.deeper-notebook-migrations/`.
2. Flush the receipt file and receipt directory with `fsync`.
3. Confirm source/destination share a device.
4. Snapshot critical hashes.
5. Call `os.replace(legacy, canonical)` and `fsync` the home directory.
6. Re-hash canonical critical files.
7. On macOS/Linux, attempt a directory symlink from the legacy path to the canonical root; on Windows, attempt the supported directory-link strategy only when the process has permission.
8. Record `compatibility_link_created`, validation results, and explicit rollback instructions in a temporary final receipt.
9. Flush the final receipt, atomically replace the started receipt, and flush the receipt directory.
10. Remove the owned migration lock and return the canonical root.

If any step after the directory rename fails, remove only the compatibility
link created by this operation, confirm the canonical critical hashes still
match the pre-move snapshot, call `os.replace(canonical, legacy)`, flush the
home directory, and record `rolled-back`. If hashes no longer match or rollback
itself fails, return `rollback-available`, start no write-capable service, and
preserve both the receipt and exact operator instructions.

If same-volume atomic rename is unavailable, return `migration-deferred` and continue on the legacy root. Do not perform a recursive copy.

- [ ] **Step 4: Route every active desktop state consumer through the resolver**

Replace hard-coded `.open-notebook-plus` construction in the listed files with:

```python
from desktop.data_root import active_data_root

data_home = active_data_root()
```

Add a guard test that scans production Python files and fails on new direct constructions of either data-directory name outside `deeper_notebook/identity.py`, `desktop/data_root.py`, migration documentation, and tests.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest desktop/tests/test_data_root_migration.py desktop/tests/test_config.py desktop/tests/test_launcher_prefs.py desktop/tests/test_bootstrap.py tests/test_logging_config.py tests/test_updates_service.py -q
uv run ruff check desktop/data_root.py desktop/tests/test_data_root_migration.py
```

- [ ] **Step 6: Commit**

```bash
git add desktop open_notebook/logging.py api/updates_service.py tests/test_logging_config.py tests/test_updates_service.py
git commit -m "feat(desktop): migrate legacy state to Deeper Notebook"
```

---

### Task 4: Move the Canonical Python Package and Keep a Forwarding Shim

**Files:**

- Move: implementation under `open_notebook/` to `deeper_notebook/`
- Create: `open_notebook/__init__.py`
- Create: `open_notebook/_alias.py`
- Create: `tests/fixtures/legacy_import_modules.txt`
- Create: `tests/test_python_import_compatibility.py`
- Modify: all production and test Python imports
- Modify: `pyproject.toml`
- Modify: `desktop/build/pyinstaller.spec`
- Modify: desktop runtime-path logic and upstream-sync guards

- [ ] **Step 1: Write failing canonical-import tests**

```python
def test_canonical_import_is_primary():
    from deeper_notebook.domain.notebook import Note as canonical
    from open_notebook.domain.notebook import Note as legacy

    assert legacy is canonical


def test_legacy_config_module_is_same_object():
    canonical = importlib.import_module("deeper_notebook.config")
    legacy = importlib.import_module("open_notebook.config")
    assert legacy is canonical


@pytest.mark.parametrize(
    "legacy_name",
    Path("tests/fixtures/legacy_import_modules.txt").read_text().splitlines(),
)
def test_every_pre_move_legacy_import_resolves_to_canonical_object(legacy_name):
    canonical_name = legacy_name.replace("open_notebook", "deeper_notebook", 1)
    assert importlib.import_module(legacy_name) is importlib.import_module(
        canonical_name
    )
```

Also assert `importlib.metadata.metadata("deeper-notebook")["Name"] == "deeper-notebook"` in an installed-package test.

- [ ] **Step 2: Run and confirm RED**

Run: `uv run pytest tests/test_python_import_compatibility.py -q`

Expected: canonical domain modules do not exist yet.

- [ ] **Step 3: Perform the mechanical package move**

Use Git-aware moves and one exact import rewrite:

```bash
git mv open_notebook/ai deeper_notebook/ai
git mv open_notebook/analysis deeper_notebook/analysis
git mv open_notebook/capture deeper_notebook/capture
git mv open_notebook/database deeper_notebook/database
git mv open_notebook/digest deeper_notebook/digest
git mv open_notebook/domain deeper_notebook/domain
git mv open_notebook/evaluation deeper_notebook/evaluation
git mv open_notebook/graphs deeper_notebook/graphs
git mv open_notebook/health deeper_notebook/health
git mv open_notebook/local_models deeper_notebook/local_models
git mv open_notebook/mcp deeper_notebook/mcp
git mv open_notebook/podcasts deeper_notebook/podcasts
git mv open_notebook/prompt_optimizer deeper_notebook/prompt_optimizer
git mv open_notebook/research deeper_notebook/research
git mv open_notebook/security deeper_notebook/security
git mv open_notebook/studio deeper_notebook/studio
git mv open_notebook/study deeper_notebook/study
git mv open_notebook/tools deeper_notebook/tools
git mv open_notebook/utils deeper_notebook/utils
git mv open_notebook/video deeper_notebook/video
git mv open_notebook/config.py deeper_notebook/config.py
git mv open_notebook/exceptions.py deeper_notebook/exceptions.py
git mv open_notebook/feature_flags.py deeper_notebook/feature_flags.py
git mv open_notebook/logging.py deeper_notebook/logging.py
git mv open_notebook/CLAUDE.md deeper_notebook/CLAUDE.md
```

Mechanically rewrite Python import statements from `open_notebook` to `deeper_notebook`. Do not rewrite string values for Surreal namespace/database, record IDs, queued command app IDs, historical docs, or upstream Docker references.

- [ ] **Step 4: Implement the compatibility package**

`open_notebook/_alias.py` installs a complete finder before any legacy
submodule is imported:

```python
from __future__ import annotations

import importlib
import importlib.abc
import importlib.util


class LegacyAliasLoader(importlib.abc.Loader):
    def __init__(self, canonical_name: str) -> None:
        self.canonical_name = canonical_name
        self.canonical_spec = None

    def create_module(self, spec):
        module = importlib.import_module(self.canonical_name)
        self.canonical_spec = module.__spec__
        return module

    def exec_module(self, module) -> None:
        module.__spec__ = self.canonical_spec
        module.__loader__ = self.canonical_spec.loader
        module.__package__ = self.canonical_spec.parent


class LegacyAliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname: str, path=None, target=None):
        if not fullname.startswith("open_notebook."):
            return None
        canonical_name = fullname.replace("open_notebook", "deeper_notebook", 1)
        canonical_spec = importlib.util.find_spec(canonical_name)
        if canonical_spec is None:
            return None
        return importlib.util.spec_from_loader(
            fullname,
            LegacyAliasLoader(canonical_name),
            is_package=canonical_spec.submodule_search_locations is not None,
        )
```

`open_notebook/__init__.py` installs one finder and aliases the package:

```python
"""Deprecated import compatibility for Deeper Notebook."""

from __future__ import annotations

import importlib
import sys

from ._alias import LegacyAliasFinder

if not any(isinstance(finder, LegacyAliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, LegacyAliasFinder())
_canonical = importlib.import_module("deeper_notebook")
sys.modules[__name__] = _canonical
```

The shim contains no duplicated implementation. Generate the fixture module
list from the pre-rewrite `rg` inventory, sort it, and retain it as the
compatibility contract. Add an explicit deprecation note without printing
warnings during normal application startup.

- [ ] **Step 5: Update migration and packaging paths**

Change migration discovery to resolve from the canonical package directory rather than the current working directory:

```python
if mig_dir is None:
    mig_dir = Path(__file__).resolve().parent / "migrations"
```

Update PyInstaller hidden imports/data collection and desktop runtime path tests to package `deeper_notebook`. Keep the compatibility package in the frozen app.

- [ ] **Step 6: Protect persisted command identities**

Keep surreal-command decorators and submission strings using the existing `app="open_notebook"` during this release. Add a test and allowlist classification stating that this is a persisted queue compatibility identifier, not a product label. Do not rename queued jobs in place.

- [ ] **Step 7: Run package and regression tests**

Run:

```bash
uv run pytest tests/test_python_import_compatibility.py tests/test_migration_discovery.py tests/test_domain.py tests/test_notes_api.py tests/test_search_api.py tests/test_graphs.py tests/test_video_overview.py tests/test_video_overview_router.py -q
uv run ruff check deeper_notebook open_notebook api commands desktop
uv run pytest -q
```

Expected: the full backend/desktop suite passes before committing the package move.

- [ ] **Step 8: Commit**

```bash
git add deeper_notebook open_notebook api commands desktop scripts tests pyproject.toml
git commit -m "refactor: make deeper_notebook the canonical package"
```

---

### Task 5: Add the Notebook Spark / Research Core Brand System

**Files:**

- Create: `brand/deeper-notebook-mark.svg`
- Create: `frontend/src/lib/brand.ts`
- Create: `frontend/src/lib/brand.test.ts`
- Modify: `frontend/public/logo.svg`
- Modify: `frontend/src/app/favicon.ico`
- Modify: `frontend/src/app/globals.css`
- Move: `frontend/src/components/onp/` to `frontend/src/components/deeper-notebook/`
- Modify: `frontend/src/components/deeper-notebook/tokens.css`
- Modify: `desktop/resources/make_icon.py`
- Regenerate: `desktop/resources/icon.png`
- Regenerate: `desktop/resources/icon.icns`
- Regenerate: `desktop/resources/icon.ico`

- [ ] **Step 1: Write failing brand-token tests**

```typescript
import { describe, expect, it } from 'vitest'
import { BRAND } from './brand'

describe('Deeper Notebook brand', () => {
  it('exposes the approved identity and Research Core palette', () => {
    expect(BRAND.name).toBe('Deeper Notebook')
    expect(BRAND.tagline).toBe('Think further with every source')
    expect(BRAND.colors).toEqual({
      deep: '#071B1D',
      darkTeal: '#0F766E',
      teal: '#2DD4BF',
      cyan: '#38BDF8',
      light: '#CCFBF1',
    })
  })
})
```

- [ ] **Step 2: Add the exact canonical vector**

Use this accessible, transparent SVG as the source for all icon variants:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-labelledby="title">
  <title id="title">Deeper Notebook</title>
  <defs>
    <linearGradient id="core" x1="48" y1="36" x2="210" y2="220" gradientUnits="userSpaceOnUse">
      <stop stop-color="#2DD4BF"/>
      <stop offset="1" stop-color="#38BDF8"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="58" fill="#071B1D"/>
  <path d="M63 53h101c18 0 29 11 29 29v119H91c-16 0-28-12-28-28V53Z"
        fill="#0F766E" stroke="url(#core)" stroke-width="12" stroke-linejoin="round"/>
  <path d="M91 53v148" stroke="#CCFBF1" stroke-width="10" stroke-linecap="round" opacity=".9"/>
  <path d="m157 82 8 23 23 8-23 8-8 23-8-23-23-8 23-8 8-23Z" fill="#CCFBF1"/>
  <circle cx="157" cy="113" r="10" fill="#38BDF8"/>
</svg>
```

- [ ] **Step 3: Apply Research Core tokens**

Rename `--onp-*` tokens/classes to `--dn-*` and update consumers. Set the core palette from `BRAND.colors`; retain theme adaptability for existing user-selectable themes. The default theme uses deep blue-green surfaces, teal primary actions, cyan focus, and light teal foreground. Reduced-motion rules remain unchanged.

- [ ] **Step 4: Generate desktop and favicon assets**

Update `desktop/resources/make_icon.py` to render the same Notebook Spark geometry and Research Core palette as `brand/deeper-notebook-mark.svg` with the existing Pillow dependency, produce the required PNG sizes, produce `.icns` on macOS, and produce `.ico` with 16/32/48/64/128/256 pixel frames. The generator also writes the frontend favicon from the 256-pixel image. Tests verify each artifact exists, is non-empty, contains the approved palette, and includes a 256-pixel representation.

- [ ] **Step 5: Run visual contract checks**

Run:

```bash
cd frontend && npm test -- src/lib/brand.test.ts
uv run python desktop/resources/make_icon.py
file desktop/resources/icon.png desktop/resources/icon.icns desktop/resources/icon.ico frontend/src/app/favicon.ico
```

- [ ] **Step 6: Commit**

```bash
git add brand frontend desktop/resources
git commit -m "feat(brand): add Notebook Spark research identity"
```

---

### Task 6: Rebrand Active UI, Desktop Chrome, API Metadata, Exports, and Locales

**Files:**

- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/(dashboard)/page.tsx`
- Modify: `frontend/src/components/intro/IntroReveal.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx`
- Modify: all `frontend/src/lib/locales/*/index.ts`
- Modify: desktop window, splash, tray, first-run, model-manager, and memory-dashboard UI files.
- Modify: `api/main.py`
- Modify: Deeper Notebook exporter/provenance files.
- Modify: associated frontend and desktop tests.

- [ ] **Step 1: Write failing active-brand tests**

Add assertions for:

- Next metadata title and description.
- Dashboard wordmark and tagline.
- Intro dialog accessible name.
- Sidebar logo alt text.
- Every locale `common.appName`.
- Desktop default window title, splash, tray, first-run, and already-running dialog.
- API `/`, `/api/version`, and health metadata.
- PDF/DOCX/PPTX/XLSX/export provenance creator/application fields.

Example locale test:

```typescript
for (const [locale, messages] of Object.entries(locales)) {
  expect(messages.common.appName, locale).toBe('Deeper Notebook')
  expect(JSON.stringify(messages)).not.toMatch(
    /Open Notebook Plus|Open notebook\+/
  )
}
```

- [ ] **Step 2: Replace active visible copy**

Use:

- Name: `Deeper Notebook`
- Tagline: `Think further with every source`
- Description: `Local-first research and knowledge workspace`

Update every locale with the proper product name unchanged. Translate surrounding sentences, not the proper name.

- [ ] **Step 3: Rename the downstream API/frontend namespace**

Move the router and frontend helper. Canonical endpoints become `/api/deeper-notebook/*`. Register the same router a second time at `/api/onp/*` with `include_in_schema=False`:

```python
app.include_router(
    deeper_notebook.router,
    prefix="/api/deeper-notebook",
    tags=["deeper-notebook"],
)
app.include_router(
    deeper_notebook.router,
    prefix="/api/onp",
    include_in_schema=False,
)
```

Routes inside the theme router use `/theme`, not a hard-coded namespace.
Refactor the Gmail router from `prefix="/onp/gmail"` to the namespace-relative
`prefix="/gmail"` and dual-register it:

```python
app.include_router(
    gmail.router,
    prefix="/api/deeper-notebook",
    tags=["deeper-notebook-gmail"],
)
app.include_router(
    gmail.router,
    prefix="/api/onp",
    include_in_schema=False,
)
```

New connect flows generate
`/api/deeper-notebook/gmail/callback`. The hidden legacy
`/api/onp/gmail/callback` stays operational for already registered OAuth
redirect URIs and in-flight callbacks, and both callbacks complete into the
same token/state handler. Add tests for canonical connect/callback, legacy
callback continuity, state validation on both paths, and unchanged refresh
tokens. `deeperNotebookFetch()` replaces `onpFetch()` in active code; a
deprecated export remains for compatibility. Migrate every active Gmail
frontend URL to the canonical namespace.

- [ ] **Step 4: Rebrand generated artifacts**

Export metadata uses `Deeper Notebook` as creator/application. Provenance URNs use `urn:deeper-notebook:*`. Preserve the ability to read old `urn:open-notebook-plus:*` records; do not rewrite stored historical artifacts.

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest desktop/tests/test_first_run.py tests/test_notes_api.py tests/test_evidence_studio_artifact_api.py tests/test_v0_7_210_version_and_reaper.py tests/test_gmail_router.py tests/test_gmail_cache.py -q
cd frontend && npm test -- src/lib/hooks/use-translation.test.ts src/components/layout/AppSidebar.test.tsx src/components/intro
```

- [ ] **Step 6: Commit**

```bash
git add api desktop deeper_notebook frontend tests
git commit -m "feat(brand): present Deeper Notebook across the product"
```

---

### Task 7: Rebrand Desktop Packages, Installers, Updates, and Release Workflows

**Files:**

- Modify: `desktop/build/pyinstaller.spec`
- Move/Modify: `desktop/build/deeper-notebook.iss`
- Modify: `desktop/build/post_build_mac.sh`
- Modify: `desktop/build/post_build_windows.ps1`
- Modify: `desktop/build/build_windows.ps1`
- Modify: `desktop/tests/test_release_manifest.py`
- Create: `desktop/app_migration.py`
- Create: `desktop/tests/test_app_migration.py`
- Modify: `.github/workflows/build-desktop.yml`
- Modify: `.github/workflows/build-windows.yml`
- Modify: `api/updates_service.py`
- Modify: `frontend/src/lib/hooks/use-version-check.ts`
- Modify: `tests/test_updates_service.py`

- [ ] **Step 1: Update release-contract tests first**

Assert exact artifact names:

```python
assert "Deeper-Notebook-mac-arm64.dmg" in workflow
assert "Deeper-Notebook-mac-x86_64.dmg" in workflow
assert "Deeper-Notebook-windows-x64.zip" in workflow
assert "Deeper-Notebook-Setup-x64.exe" in workflow
assert "Open-Notebook-Plus-" not in workflow
```

Installer tests assert:

```python
assert '#define MyAppName "Deeper Notebook"' in installer
assert '#define MyAppExeName "Deeper Notebook.exe"' in installer
assert "AppId={{572C65B3-D1E8-4EBD-8D64-2BFDF3CA5842}" in installer
```

- [ ] **Step 2: Update PyInstaller and native metadata**

Set executable, collection, app bundle, display name, permission descriptions, and output names to Deeper Notebook. Keep the current macOS bundle identifier for this release unless a signed packaged upgrade test and permission-migration note are completed; classify it as a compatibility identifier.

- [ ] **Step 3: Update Windows installer without changing product identity**

Use:

```ini
#define MyAppName "Deeper Notebook"
#define MyAppExeName "Deeper Notebook.exe"
DefaultDirName={localappdata}\Programs\Deeper Notebook
OutputBaseFilename=Deeper-Notebook-Setup-x64
```

Keep the exact existing `AppId`. A Windows compatibility job checks out the
approved legacy baseline commit `7888102` into a separate worktree, builds its
`Open-Notebook-Plus-Setup-x64.exe`, records its SHA-256, installs it, seeds a
synthetic notebook/config under the legacy data root, and launch-probes it.
The job then installs the new `Deeper-Notebook-Setup-x64.exe`, verifies the
seeded data through the migrated app, verifies exactly one uninstall entry for
the stable `AppId`, launch-probes `Deeper Notebook.exe`, uninstalls, and
verifies the temporary install directory is removed. Installing the new
installer twice is retained as a repair test but is not labeled an upgrade
test.

- [ ] **Step 4: Handle the renamed macOS application bundle**

Implement `desktop/app_migration.py` with pure detection and an explicit
replacement action. When `/Applications/Open Notebook Plus.app` and
`/Applications/Deeper Notebook.app` coexist with the compatible bundle ID,
Deeper Notebook shows a one-time recovery card. It never deletes the old app
silently. The user-approved action moves the old bundle to the macOS Trash
using the native recoverable mechanism and records a receipt under the
canonical data root. Tests use temporary application directories and prove
same-bundle detection, no-op when absent, refusal outside the exact legacy
bundle, recoverable move, and one-time receipt behavior.

A macOS compatibility job builds commit `7888102`, launches the legacy app
against a temporary home, seeds state, installs the new app under its new
bundle name, launch-probes migration, invokes the explicit replacement helper
in the temporary Applications directory, and verifies one remaining app plus
matching state hashes.

- [ ] **Step 5: Repoint updates**

Set `GITHUB_REPO = "Deeper-Notebook"` and fallback release links to `https://github.com/Antman1526/Deeper-Notebook/releases/latest`. `app_version()` checks the `deeper-notebook` distribution first and the legacy distribution only as compatibility fallback.

- [ ] **Step 6: Run release checks**

Run:

```bash
uv run pytest desktop/tests/test_release_manifest.py desktop/tests/test_app_migration.py tests/test_updates_service.py -q
make build-mac
hdiutil verify dist/Deeper-Notebook-mac-$(uname -m).dmg
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File desktop/build/build_windows.ps1
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" desktop/build/deeper-notebook.iss
```

- [ ] **Step 7: Commit**

```bash
git add desktop .github/workflows api/updates_service.py frontend/src/lib/hooks/use-version-check.ts tests/test_updates_service.py
git commit -m "build(desktop): ship Deeper Notebook artifacts"
```

---

### Task 8: Repoint Active Documentation and Close the Legacy Inventory

**Files:**

- Modify: `README.md`
- Modify: `SECURITY.md` only where links refer to the downstream product.
- Modify: `docs/BUILD_WINDOWS.md`
- Modify: `.github/ISSUE_TEMPLATE/*`
- Modify: active product-owned docs and setup links.
- Modify: `scripts/rebrand-allowlist.json`
- Modify: `tests/test_v0_7_201_audit_sweep.py`

- [ ] **Step 1: Write failing downstream-link assertions**

Assert active links target `https://github.com/Antman1526/Deeper-Notebook`, while explicit upstream-sync and attribution links still target `https://github.com/lfnovo/open-notebook`.

- [ ] **Step 2: Update active product documentation**

README opening copy, badges, clone commands, native build names, screenshots/captions, configuration examples, support links, and release instructions use Deeper Notebook. Add a migration section describing canonical and legacy environment variables and data directories.

- [ ] **Step 3: Preserve history accurately**

Do not mass-rewrite:

- `README.upstream.md`
- historical `CHANGELOG.md` entries
- historical plans/specs
- old release artifact references that document what was actually shipped
- upstream Docker image names

Append a short successor note when a historical document is likely to confuse a current reader.

- [ ] **Step 4: Require zero unexpected active legacy matches**

Add the final repository-wide subprocess assertion to
`tests/test_product_identity.py`:

```python
result = subprocess.run(
    [sys.executable, "scripts/rebrand_audit.py", "--check"],
    cwd=REPO_ROOT,
    capture_output=True,
    text=True,
)
assert result.returncode == 0, result.stdout + result.stderr
```

Run:

```bash
uv run python scripts/rebrand_audit.py --check
```

Expected JSON summary:

```json
{
  "unexpected_active_identity": 0
}
```

Every remaining match must name its exact category and reason in the allowlist.

- [ ] **Step 5: Run production proof**

Run:

```bash
uv run pytest -q
cd frontend && npm test && npm run build
uv run python scripts/rebrand_audit.py --check
git diff --check
```

Then perform:

1. Fresh-profile native launch smoke using a temporary home.
2. Legacy-only profile migration smoke with before/after hashes.
3. Both-roots conflict smoke proving recovery mode and zero writes.
4. macOS app and DMG verification.
5. Windows installer/upgrade/uninstall smoke on Windows CI.

- [ ] **Step 6: Commit**

```bash
git add README.md SECURITY.md docs .github/ISSUE_TEMPLATE scripts tests
git commit -m "docs: complete the Deeper Notebook rebrand"
```

- [ ] **Step 7: Rename the local checkout only after all processes stop**

Verify the worktree is clean, stop the native app and local development
services, confirm `origin` is
`https://github.com/Antman1526/Deeper-Notebook.git`, then move the checkout
within its current parent:

```bash
mv "/Users/Antman/Documents/Open Notebook/open-notebook-Plus" \
  "/Users/Antman/Documents/Open Notebook/Deeper-Notebook"
git -C "/Users/Antman/Documents/Open Notebook/Deeper-Notebook" status --short --branch
git -C "/Users/Antman/Documents/Open Notebook/Deeper-Notebook" remote get-url origin
```

Do this as the final workspace handoff because moving the active cwd earlier
would invalidate running terminals and local services.

---

## Completion Gate

The rebrand is complete only when:

- `scripts/rebrand_audit.py --check` reports zero unexpected active identities.
- Existing data opens through the guarded migration path with matching hashes.
- Canonical and legacy configuration precedence tests pass.
- Canonical and legacy import tests pass.
- Active UI, exports, API metadata, desktop chrome, and every locale show Deeper Notebook.
- macOS artifacts launch and verify.
- Windows artifacts build, upgrade the stable installer identity, launch on Windows, and uninstall cleanly.
- The worktree contains no unrelated staged paths.
- The local checkout is handed off as `/Users/Antman/Documents/Open Notebook/Deeper-Notebook` after process shutdown.
