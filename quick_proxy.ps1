<#
.SYNOPSIS
    Quickly sets up the stack using Apache or Nginx as a reverse proxy.
.DESCRIPTION
    Launches the docker services and selects the desired proxy.
#>
param(
    [ValidateSet('apache','nginx')]
    [string]$Proxy = 'nginx'
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

Write-Host '=== AI Scraping Defense: Proxy Quick Start ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

if ($Proxy -eq 'apache') {
    Write-Host 'Launching stack with Apache reverse proxy...' -ForegroundColor Cyan
    docker compose up -d apache_proxy
}
else {
    Write-Host 'Launching stack with Nginx reverse proxy...' -ForegroundColor Cyan
    docker compose up -d nginx_proxy
}

Write-Host "Stack is running behind $Proxy." -ForegroundColor Green
