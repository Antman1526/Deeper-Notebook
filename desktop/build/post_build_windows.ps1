# desktop/build/post_build_windows.ps1 — archive the complete PyInstaller onedir bundle
$ErrorActionPreference = "Stop"
$Name = "Open Notebook Plus"
$Src = "dist\$Name"
$Dest = "dist\Open-Notebook-Plus-windows-x64.zip"

if (-not (Test-Path $Src)) {
  Write-Error "$Src not found. Run pyinstaller first."
  exit 1
}

$Launcher = Join-Path $Src "$Name.exe"
if (-not (Test-Path $Launcher)) {
  Write-Error "$Launcher not found. The PyInstaller bundle is incomplete."
  exit 1
}

$BundleFiles = Get-ChildItem -Path $Src -Recurse -File
if ($BundleFiles.Count -lt 2) {
  Write-Error "$Src contains only a launcher. Refusing to distribute an incomplete onedir bundle."
  exit 1
}

if (Test-Path $Dest) { Remove-Item $Dest }
Compress-Archive -Path "$Src\*" -DestinationPath $Dest
Write-Host "Built $Dest"
