#requires -Version 5.1
<#
.SYNOPSIS
    Build Deeper Notebook for Windows x64 locally (the ROG).
    Mirrors the CI job `build-windows-x64` in .github/workflows/build-desktop.yml.

.DESCRIPTION
    Produces:
      dist\Deeper Notebook\Deeper Notebook.exe   (the launcher .exe + onedir bundle)
      dist\Deeper-Notebook-windows-x64.zip        (zipped, ready to share/install)

    Stages (same order as macOS `make build-mac`, minus the .app/.dmg packaging):
      1. Create an isolated build venv
      2. pip install backend + desktop requirements, then the package (editable)
      3. Build the Next.js frontend (npm ci + npm run build)
      4. Fetch pinned native runtimes (SurrealDB, Node, uv, python-build-standalone)
      5. PyInstaller -> dist\Deeper Notebook\
      6. Zip it -> dist\Deeper-Notebook-windows-x64.zip

.PARAMETER SkipFrontend
    Skip the frontend rebuild (use the existing frontend\.next build).

.PARAMETER SkipRuntimes
    Skip re-downloading the ~500 MB of native runtimes if desktop\bin is already populated.

.PARAMETER Clean
    Remove dist\ and the build venv before starting.

.EXAMPLE
    pwsh -File desktop\build\build_windows.ps1
.EXAMPLE
    pwsh -File desktop\build\build_windows.ps1 -SkipRuntimes -SkipFrontend
#>
[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipRuntimes,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
# Force UTF-8 so emoji/arrows in any sub-script can't crash on cp1252 (the exact
# bug that broke fetch_runtimes.py in CI).
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- locate repo root (this script lives in desktop\build\) ---
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
$BuildVenv = Join-Path $RepoRoot ".venv-build-win"
$VenvPy    = Join-Path $BuildVenv "Scripts\python.exe"

function Step($n, $msg) { Write-Host "`n=== [$n] $msg ===" -ForegroundColor Cyan }
function Die($msg)       { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

# --- prerequisites ---
Step 0 "Checking prerequisites"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Die "Python not found on PATH. Install Python 3.12 from python.org and re-run." }
$pyver = (& python -c "import sys;print('%d.%d'%sys.version_info[:2])").Trim()
if ($pyver -ne "3.12") { Write-Host "WARNING: Python $pyver detected; this project targets 3.12. Continuing anyway." -ForegroundColor Yellow }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Die "Node.js not found on PATH. Install Node 20 LTS from nodejs.org and re-run." }
if (-not (Get-Command npm  -ErrorAction SilentlyContinue)) { Die "npm not found on PATH (comes with Node)." }
Write-Host "  python $pyver, node $((& node --version))" -ForegroundColor Green

if ($Clean) {
    Step "C" "Cleaning dist\ and build venv"
    Remove-Item -Recurse -Force "dist", $BuildVenv -ErrorAction SilentlyContinue
}

# --- 1. build venv ---
Step 1 "Creating isolated build venv ($BuildVenv)"
if (-not (Test-Path $VenvPy)) { & python -m venv $BuildVenv }
& $VenvPy -m pip install --upgrade pip wheel | Out-Null

# --- 2. backend + desktop deps + the package ---
Step 2 "Installing Python dependencies (this compiles llama-cpp-python; can take 5-15 min)"
& $VenvPy -m pip install -r (Join-Path $RepoRoot "desktop\requirements.txt")
if ($LASTEXITCODE -ne 0) { Die "pip install requirements failed" }
& $VenvPy -m pip install -e $RepoRoot
if ($LASTEXITCODE -ne 0) { Die "pip install -e . failed" }

# --- 3. frontend ---
if (-not $SkipFrontend) {
    Step 3 "Building the Next.js frontend"
    Push-Location (Join-Path $RepoRoot "frontend")
    & npm ci;        if ($LASTEXITCODE -ne 0) { Pop-Location; Die "npm ci failed" }
    & npm run build; if ($LASTEXITCODE -ne 0) { Pop-Location; Die "npm run build failed" }
    Pop-Location
} else {
    Step 3 "Skipping frontend build (-SkipFrontend)"
}

# --- 4. native runtimes ---
if (-not $SkipRuntimes) {
    Step 4 "Fetching pinned native runtimes (SurrealDB / Node / uv / python-build-standalone)"
    & $VenvPy (Join-Path $RepoRoot "desktop\build\fetch_runtimes.py")
    if ($LASTEXITCODE -ne 0) { Die "fetch_runtimes.py failed" }
} else {
    Step 4 "Skipping runtime download (-SkipRuntimes)"
}

# --- 5. PyInstaller ---
Step 5 "Running PyInstaller (produces dist\Deeper Notebook\)"
& $VenvPy -m PyInstaller (Join-Path $RepoRoot "desktop\build\pyinstaller.spec") --noconfirm
if ($LASTEXITCODE -ne 0) { Die "PyInstaller failed" }

# --- 6. zip ---
Step 6 "Packaging dist\Deeper-Notebook-windows-x64.zip"
& pwsh -File (Join-Path $RepoRoot "desktop\build\post_build_windows.ps1")
if ($LASTEXITCODE -ne 0) { Die "post_build_windows.ps1 failed" }

# --- done ---
$Exe = Join-Path $RepoRoot "dist\Deeper Notebook\Deeper Notebook.exe"
$Zip = Join-Path $RepoRoot "dist\Deeper-Notebook-windows-x64.zip"
Write-Host "`n=== BUILD COMPLETE ===" -ForegroundColor Green
if (Test-Path $Exe) { Write-Host "  Launcher:  $Exe" -ForegroundColor Green }
if (Test-Path $Zip) { Write-Host "  Zip:       $Zip  ($([math]::Round((Get-Item $Zip).Length/1MB,0)) MB)" -ForegroundColor Green }
Write-Host "`nRun the app by launching the .exe above, or unzip the .zip anywhere and run it." -ForegroundColor Green
Write-Host "First launch reprovisions a user venv + extracts the bundled Python (one-time, a few minutes)." -ForegroundColor DarkGray
