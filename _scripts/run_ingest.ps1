# Purpose: run backend/ingest.py using the project .venv, defaulting to a local SQLite record manager unless explicitly told to use the configured DB URL.
[CmdletBinding()]
param(
    [switch]$UseConfiguredRecordManager,
    [switch]$UseLocalRecordManager,
    [string]$LocalRecordManagerUrl = "sqlite:///record_manager_local.db",
    [switch]$ForceUpdate,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "common.ps1")

$repoRoot = Get-RepoRoot
$python = Get-VenvPython

if ($UseConfiguredRecordManager) {
    $env:USE_CONFIGURED_RECORD_MANAGER = "true"
    Write-Host "Using configured RECORD_MANAGER_DB_URL"
}
elseif ($UseLocalRecordManager) {
    $env:RECORD_MANAGER_DB_URL = $LocalRecordManagerUrl
    Write-Host ("Using local record manager: {0}" -f $LocalRecordManagerUrl)
}
else {
    $env:RECORD_MANAGER_DB_URL = $LocalRecordManagerUrl
    Remove-Item Env:USE_CONFIGURED_RECORD_MANAGER -ErrorAction SilentlyContinue
    Write-Host ("Using default local record manager: {0}" -f $LocalRecordManagerUrl)
}

if ($ForceUpdate) {
    $env:FORCE_UPDATE = "true"
    Write-Host "FORCE_UPDATE=true"
}

Invoke-InRepo -WorkingDirectory $repoRoot -Command $python -Arguments @("backend\ingest.py") -DryRun:$DryRun
