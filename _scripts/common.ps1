# Purpose: shared helpers for repo-root script entry points and .venv command execution.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-VenvPython {
    $python = Join-Path (Get-RepoRoot) ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "Missing Python interpreter: $python"
    }
    return $python
}

function Get-FrontendRoot {
    return (Join-Path (Get-RepoRoot) "frontend")
}

function Get-NodeExecutable {
    $node = Get-Command node -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if ($null -eq $node) {
        throw "Missing Node.js executable in PATH."
    }

    return $node.Source
}

function Get-FrontendNextCli {
    $nextCli = Join-Path (Get-FrontendRoot) "node_modules\next\dist\bin\next"
    if (-not (Test-Path $nextCli)) {
        throw "Missing local Next.js CLI: $nextCli. Install frontend dependencies first."
    }

    return $nextCli
}

function Invoke-FrontendNext {
    param(
        [string[]]$Arguments = @(),
        [switch]$DryRun
    )

    $nextArguments = @((Get-FrontendNextCli)) + $Arguments

    Invoke-InRepo `
        -WorkingDirectory (Get-FrontendRoot) `
        -Command (Get-NodeExecutable) `
        -Arguments $nextArguments `
        -DryRun:$DryRun
}

function Invoke-InRepo {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [string]$Command,

        [string[]]$Arguments = @(),
        [switch]$DryRun
    )

    $display = @($Command) + $Arguments
    Write-Host ("Working directory: {0}" -f $WorkingDirectory)
    Write-Host ("Command: {0}" -f ($display -join " "))

    if ($DryRun) {
        return
    }

    Push-Location $WorkingDirectory
    try {
        & $Command @Arguments
    }
    finally {
        Pop-Location
    }
}
