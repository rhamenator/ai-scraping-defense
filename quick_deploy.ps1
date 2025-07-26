<#
.SYNOPSIS
    Quickly deploys the stack to Kubernetes.
#>
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
Write-Host '=== AI Scraping Defense: Quick Deploy ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

# Deploy manifests
& "$PSScriptRoot/deploy.ps1"

Write-Host 'Deployment complete. Monitor pods with: kubectl get pods -n ai-defense' -ForegroundColor Green
