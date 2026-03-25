# Purpose: start the FastAPI backend from the project .venv without relying on Poetry.
[CmdletBinding()]
param(
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8080,
    [switch]$Reload,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "common.ps1")

$repoRoot = Get-RepoRoot
$python = Get-VenvPython
$arguments = @("-m", "uvicorn", "backend.main:app", "--host", $ListenHost, "--port", "$Port")

if ($Reload) {
    $arguments += "--reload"
}

Invoke-InRepo -WorkingDirectory $repoRoot -Command $python -Arguments $arguments -DryRun:$DryRun
