# Purpose: start the Next.js frontend dev server from the frontend workspace.
[CmdletBinding()]
param(
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "common.ps1")

Invoke-FrontendNext -Arguments @("dev") -DryRun:$DryRun
