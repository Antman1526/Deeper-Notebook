# Building Open Notebook Plus for Windows

There are two ways to produce a Windows build (`Open Notebook Plus.exe` + a
distributable `.zip`). Both run the **same** stages as the macOS `make build-mac`
(minus the `.app`/`.dmg` packaging), producing a PyInstaller *onedir* bundle.

> **What you get:** `dist\Open Notebook Plus\Open Notebook Plus.exe` (the launcher)
> and `dist\Open-Notebook-Plus-windows-x64.zip` (the whole bundle, zipped).
> On first launch the app reprovisions a user venv and extracts the bundled
> Python runtime (one-time, a few minutes), then starts SurrealDB + the API +
> the Next.js frontend + the local AI sidecars and opens the desktop window.

---

## Option A — GitHub Actions (cloud, recommended)

No local Windows toolchain needed. Two workflows:

### A1. On-demand Windows-only build (fastest, ~15 min)
`.github/workflows/build-windows.yml` — Windows-only, manual trigger, does **not**
wait on the slow/expensive macOS jobs.

1. Go to the repo on GitHub -> **Actions** tab.
2. Select **build-windows** in the left sidebar.
3. Click **Run workflow** -> pick the `desktop-app` branch -> **Run workflow**.
4. When it finishes (~15 min), open the run -> **Artifacts** ->
   download **Open-Notebook-Plus-windows-x64** (the `.zip`).

Or trigger it from your Mac with the GitHub CLI:
```bash
gh workflow run build-windows.yml --ref desktop-app
gh run watch                       # follow it live
gh run download --name Open-Notebook-Plus-windows-x64   # grab the artifact when done
```

### A2. Full release build (all platforms)
`.github/workflows/build-desktop.yml` runs on every push to `main`/`desktop-app`,
on `v*` tags, and now via manual **Run workflow** too. It builds macOS arm64 +
x86_64 **and** Windows x64; tagged builds (`vX.Y.Z`) are attached to a GitHub Release.

---

## Option B — Build locally on the ROG (Windows machine)

### Prerequisites (install once)
- **Python 3.12** — https://python.org (check "Add to PATH" during install)
- **Node.js 20 LTS** — https://nodejs.org
- **Git** — https://git-scm.com
- (PowerShell 5.1 ships with Windows; `pwsh`/PowerShell 7 also works)

### Build (one command)
```powershell
git clone https://github.com/Antman1526/open-notebook-Plus.git
cd open-notebook-Plus
git checkout desktop-app
pwsh -File desktop\build\build_windows.ps1
```

The script:
1. Creates an isolated build venv (`.venv-build-win`)
2. `pip install` backend + desktop requirements, then the package (editable)
3. Builds the Next.js frontend (`npm ci && npm run build`)
4. Downloads pinned native runtimes (SurrealDB, Node, uv, python-build-standalone)
5. Runs PyInstaller -> `dist\Open Notebook Plus\`
6. Zips it -> `dist\Open-Notebook-Plus-windows-x64.zip`

**Useful flags:**
```powershell
pwsh -File desktop\build\build_windows.ps1 -Clean          # fresh build
pwsh -File desktop\build\build_windows.ps1 -SkipRuntimes   # reuse desktop\bin\ (skip ~500 MB download)
pwsh -File desktop\build\build_windows.ps1 -SkipFrontend   # reuse existing frontend\.next
```

> **Note:** the dependency install compiles `llama-cpp-python` (the local-LLM
> runtime) and can take 5–15 min the first time. A prebuilt CPU wheel is used in
> CI; for GPU acceleration on your RTX 5070 Ti you can later install a CUDA build
> of `llama-cpp-python` into the runtime venv.

---

## How the Windows build maps to macOS

| Stage | macOS (`make build-mac`) | Windows |
|---|---|---|
| Tests | `build-mac-test` | (run `make test` separately) |
| Deps lock | `build-mac-lock` | `pip install -r desktop/requirements.txt` |
| Frontend | `build-mac-frontend` | `npm ci && npm run build` |
| Runtimes | `fetch_runtimes.py` (darwin) | `fetch_runtimes.py` (windows-x86_64) |
| Freeze | PyInstaller -> `.app` (`BUNDLE`) | PyInstaller -> onedir (`COLLECT`) |
| Package | `hdiutil` -> `.dmg` | `Compress-Archive` -> `.zip` |

The PyInstaller spec (`desktop/build/pyinstaller.spec`) already branches on
`sys.platform` (`is_win`), using `resources/icon.ico` and emitting a Windows
`.exe` + onedir instead of a macOS `.app`.

---

## Troubleshooting

- **`fetch_runtimes.py` `UnicodeEncodeError` (cp1252)** — fixed in v0.8.68 (the
  script now forces UTF-8 stdout and uses ASCII status arrows). If you see it on
  an older checkout, set `PYTHONUTF8=1` before running.
- **Long-path errors during extraction** — enable Windows long paths:
  `Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' LongPathsEnabled 1`
  (admin), then reboot.
- **SmartScreen warning on first launch** — the `.exe` is unsigned; click
  *More info -> Run anyway*. For distribution, sign it with an Authenticode cert
  (future: add a signing step to the workflow).
- **No installer yet** — the build produces a portable `.zip`/onedir, not an
  `.msi`/setup `.exe`. An Inno Setup or NSIS installer step can be added later.
