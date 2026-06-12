# desktop/build/post_build_windows.ps1 — wrap dist/Open Notebook Plus into a .zip
$ErrorActionPreference = "Stop"
$Name = "Open Notebook Plus"
$Src = "dist\$Name"
$Dest = "dist\Open-Notebook-Plus-windows-x64.zip"

if (-not (Test-Path $Src)) {
  Write-Error "$Src not found. Run pyinstaller first."
  exit 1
}

if (Test-Path $Dest) { Remove-Item $Dest }
Compress-Archive -Path "$Src\*" -DestinationPath $Dest
Write-Host "Built $Dest"
