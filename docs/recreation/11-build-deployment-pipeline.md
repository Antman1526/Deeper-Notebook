# 11 — Build & Deployment Pipeline

> Two independent artifacts: the **macOS desktop app** (primary, version `0.8.95`) and the
> **Docker server image** (upstream track, version `1.8.5`). They version different things
> and must not be "reconciled".

---

## 1. `make build-mac` — stage graph

```
build-mac: build-mac-test build-mac-lock build-mac-venv build-mac-frontend \
           build-mac-runtimes build-mac-pyinstaller build-mac-dmg
```

| Stage | Time | Output |
|---|---|---|
| `build-mac-test` | ~6 min | Gate: preflight + 832 desktop + 4,767 backend |
| `build-mac-lock` | ~10 s | `desktop/requirements.lock` (963 pins) |
| `build-mac-venv` | ~1 min | `.build-venv` |
| `build-mac-frontend` | ~2 min | `frontend/.next` standalone — **bakes flags** |
| `build-mac-runtimes` | ~1 min | `desktop/bin/` (SHA-verified) |
| `build-mac-pyinstaller` | ~10 min | `dist/Deeper Notebook.app` + re-seal |
| `build-mac-dmg` | ~2 min | `dist/Deeper-Notebook-mac-arm64.dmg` (~520 MB) |

## 2. The gate

```make
build-mac-test: build-mac-venv
	@# Preflight: a repair-script test CANNOT pass while the app or its
	@# SurrealDB is running. Fail up front with the remedy instead of
	@# ~5 minutes into the suite with an opaque assertion.
	@if pgrep -f '/Applications/Deeper Notebook.app/Contents/MacOS' >/dev/null 2>&1 \
	  || pgrep -f 'surreal-darwin' >/dev/null 2>&1; then \
	  echo "❌ Deeper Notebook (or its SurrealDB sidecar) is running."; \
	  echo "   Quit the app fully, then re-run make build-mac."; \
	  exit 1; \
	fi
	@$(BUILD_PY) -m pytest desktop/tests/ desktop/memory/tests/ -q
	@# Retry failures ONCE. Three timing-scaled tests flake under heavy load
	@# and cost three consecutive builds in one day; each passed in isolation.
	@# A deterministic failure still fails twice.
	@uv run pytest tests/ -q --ignore=tests/integration || \
	  { echo "⚠️  Backend failures — retrying only the failed tests once…"; \
	    uv run pytest tests/ -q --ignore=tests/integration \
	      --last-failed --last-failed-no-failures none; }
```

> **Never pipe a gate to `tail`.** A piped recipe's exit status is the last command's
> (`tail`, always 0), which made an earlier "precondition" toothless.

## 3. Lockfile regeneration

```make
build-mac-lock:
	@uv pip compile pyproject.toml desktop/requirements.txt \
		--python-version 3.12 --universal -o desktop/requirements.lock --quiet
```

**Both** input files are required. Compiling only `pyproject.toml` silently dropped deps
declared solely in `desktop/requirements.txt` — the casualty was `llama-cpp-python`,
producing `ModuleNotFoundError: No module named 'llama_cpp'` at sidecar spawn. `--universal`
keeps the lock cross-platform with markers.

## 4. Runtime fetching

`fetch_runtimes.py` downloads to a unique staging path, verifies SHA-256 with
`hmac.compare_digest`, then atomically `replace()`s the destination. A failed download
never clobbers a previously verified artifact.

```python
def download(url: str, dest: Path, expected_sha256: str | None = None) -> None:
    _validate_https_url(url)
    if expected_sha256 is None:
        raise ValueError("A pinned runtime SHA-256 is required")
    staging = dest.with_name(f".{dest.name}.{secrets.token_hex(8)}.part")
    try:
        with urllib.request.urlopen(url, timeout=...) as r, staging.open("wb") as f:
            shutil.copyfileobj(r, f)
        _verify_download(staging, expected_sha256)
        staging.replace(dest)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
```

Archive members are validated (`validate_tar_members` / `validate_zip_members`) with an
`expected_root` before extraction — path-traversal defence.

## 5. Codesigning

```make
build-mac-pyinstaller:
	@$(BUILD_PYINSTALLER) desktop/build/pyinstaller.spec --noconfirm
	@codesign --force --deep --sign "$(DEEPER_NOTEBOOK_CODESIGN_IDENTITY)" "dist/Deeper Notebook.app"
	@codesign --verify --deep --strict "dist/Deeper Notebook.app"
```

The **final** re-seal after all PyInstaller passes is mandatory: macOS auto-seals arm64
Mach-O binaries on first write, and any later modification — including Spotlight writing
xattrs — invalidates the seal. A broken seal makes macOS kill the binary at launch with
**no error, no dialog, no crash report**.

### Stable identity (strongly recommended)

```bash
bash scripts/create-signing-identity.sh
export DEEPER_NOTEBOOK_CODESIGN_IDENTITY="Deeper Notebook Local"
```

Ad-hoc (`--sign -`) gives a **new identity every rebuild**, so macOS resets TCC grants and
the next launch wedges on a consent dialog. The script had two bugs worth knowing:
self-signed certs need `-r trustRoot` (not `trustAsRoot`, which errors), and existence
checks must not use `find-identity -v` (which hides untrusted identities, causing
duplicate imports plus a false failure).

## 6. Install

```make
build-mac-install:
	@osascript -e 'quit app "Deeper Notebook"' 2>/dev/null || true
	@for i in $$(seq 1 20); do pgrep -f '…/Deeper Notebook.app/Contents/MacOS' >/dev/null || break; sleep 1; done
	@pkill -9 -f 'surreal-darwin'; pkill -9 -f 'llama_cpp.server'; pkill -9 -f 'surreal_commands.cli.worker'
	@rm -rf "/Applications/Deeper Notebook.app"
	@cp -R "dist/Deeper Notebook.app" /Applications/
	@xattr -dr com.apple.quarantine "/Applications/Deeper Notebook.app" || true
```

Quitting **before** deleting is required: deleting a running bundle orphaned sidecars and
left zombie Next servers holding ports.

> **No built-in rollback.** Back the bundle up first:
> `ditto "/Applications/Deeper Notebook.app" ~/backups/DN-<date>.app` — `ditto` preserves
> the codesign seal where `cp -R` may not.

## 7. Post-build verification (do not skip)

A green build does not prove the flags took. Verify against the **packaged bundle**:

```bash
# 1. Seal
codesign --verify --deep --strict "/Applications/Deeper Notebook.app"
codesign -dvv "/Applications/Deeper Notebook.app" 2>&1 | grep Authority

# 2. Runtime digest actually shipped
shasum -a 256 "…/Contents/Resources/desktop/bin/python-darwin-arm64.tar.gz"

# 3. Flags inlined — the ONLY reliable check
#    (marker greps are useless: packaging strips .map files and doubles naive counts;
#     prerendered HTML can't discriminate because routes are client-rendered shells)
python3 - <<'PY'
import re
p='…/.next/server/chunks/ssr/[root-of-the-server]__1wygwq4._.js'
t=open(p,encoding='utf8',errors='replace').read()
for f in ('isSourceVisualsEnabled','isVisualSystemV2Enabled'):
    print(re.search('"'+f+r'",0,function\(\)\{return [^}]{0,60}\}', t).group(0))
PY
# expect c("1",void 0,!1) for an enabled build
```

Checksum-diffing the 156 SSR chunks against a clean flags-off build isolates exactly
**two** differing files — the inlined literals.

## 8. Docker (server track)

```make
docker-build-local     # local platform
docker-push            # version tags, linux/amd64 + linux/arm64
docker-push-latest     # updates v1-latest
docker-release         # full release
```

Images: `lfnovo/open_notebook` (Docker Hub), `ghcr.io/lfnovo/open-notebook`.
`Dockerfile` (multi-service) and `Dockerfile.single` (all-in-one).

## 9. Security scans (network-dependent, not in `build-mac`)

```make
security-scan:
	@uvx bandit -r deeper_notebook api desktop \
	  -x "desktop/bin,desktop/tests,desktop/memory/tests" -q --severity-level high
	@uvx --python /opt/homebrew/bin/python3.12 pip-audit \
	  -r desktop/requirements.lock --no-deps || true
```

Bandit **fails** on HIGH in project code (`desktop/bin` is vendored third-party).
pip-audit **reports** against the documented triage in
`docs/verification/2026-08-16-security-scan.md`. The Homebrew interpreter is required —
uv-managed pythons ship without a working `ensurepip`, which pip-audit needs to build its
temp venv.

## 10. Release checklist

1. `main` clean; audit exit 0
2. Quit the app
3. `make build-mac` with identity + flags
4. Verify seal, runtime digest, inlined flags
5. Back up the installed bundle
6. `make build-mac-install`; relaunch
7. Confirm 7/7 model health, a live search, honest update banner
8. Update the release record under `docs/verification/`

---

*Continues in [12 — Error Handling & Logging](./12-error-handling-logging.md).*
