param(
    [Parameter(Mandatory = $true)]
    [int]$ProcessId,
    [Parameter(Mandatory = $true)]
    [string]$ScopePath
)

$ErrorActionPreference = "Stop"
$appProcess = Get-Process -Id $ProcessId -ErrorAction Stop
if (-not $appProcess.CloseMainWindow()) {
    throw "Packaged app exposed no graceful window shutdown."
}
if (-not $appProcess.WaitForExit(90000)) {
    throw "Packaged app did not shut down gracefully."
}

Start-Sleep -Milliseconds 1000
$remaining = @(
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine.Contains($ScopePath)
        }
)
if ($remaining.Count -ne 0) {
    $details = $remaining |
        Select-Object ProcessId, Name, CommandLine |
        ConvertTo-Json -Compress
    throw "Packaged sidecars remain after shutdown: $details"
}
