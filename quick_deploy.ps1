<#
.SYNOPSIS
    Quickly deploys the stack to Kubernetes.
#>
$ErrorActionPreference = 'Stop'
Write-Host '=== AI Scraping Defense: Quick Deploy ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

# Generate Kubernetes secrets
& "$PSScriptRoot/Generate-Secrets.ps1"

# Deploy manifests
& "$PSScriptRoot/deploy.ps1"

Write-Host 'Deployment complete. Monitor pods with: kubectl get pods -n ai-defense' -ForegroundColor Green
