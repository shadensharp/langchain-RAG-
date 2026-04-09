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

# Prefer repo-local .env values over stale shell exports when starting the app locally.
$managedEnvNames = @(
    "WEAVIATE_URL",
    "WEAVIATE_API_KEY",
    "DASHSCOPE_API_KEY",
    "RECORD_MANAGER_DB_URL",
    "USE_CONFIGURED_RECORD_MANAGER",
    "FORCE_UPDATE",
    "APP_PERSISTENCE_DB_URL",
    "BACKEND_CORS_ORIGINS",
    "LANGCHAIN_TRACING_V2",
    "LANGCHAIN_ENDPOINT",
    "LANGCHAIN_API_KEY",
    "LANGCHAIN_PROJECT"
)

foreach ($name in $managedEnvNames) {
    Remove-Item ("Env:{0}" -f $name) -ErrorAction SilentlyContinue
}

if ($Reload) {
    $arguments += "--reload"
}

Invoke-InRepo -WorkingDirectory $repoRoot -Command $python -Arguments $arguments -DryRun:$DryRun
