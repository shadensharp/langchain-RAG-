# Purpose: start the Next.js frontend dev server from the frontend workspace.
[CmdletBinding()]
param(
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 3000,
    [switch]$DryRun
)

. (Join-Path $PSScriptRoot "common.ps1")

Invoke-FrontendNext -Arguments @("dev", "-H", $ListenHost, "-p", "$Port") -DryRun:$DryRun
