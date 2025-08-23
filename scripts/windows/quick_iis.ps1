<#
.SYNOPSIS
    Quickly sets up the stack for IIS on Windows.
.DESCRIPTION
    Launches the Python services and configures IIS as a reverse proxy.
#>
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location -Path $RootDir

Write-Host '=== AI Scraping Defense: IIS Quick Start ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

# Start backend services
& "$RootDir/iis/start_services.ps1"

# Configure IIS proxy rules
& "$RootDir/iis/configure_proxy.ps1"

Write-Host 'IIS deployment is ready.' -ForegroundColor Green
