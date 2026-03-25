# Purpose: run a production frontend build from the frontend workspace.
[CmdletBinding()]
param(
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "common.ps1")

Invoke-FrontendNext -Arguments @("build") -DryRun:$DryRun
