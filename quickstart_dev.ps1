<#
.SYNOPSIS
    Sets up the development environment with a single command.
#>
$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot
Write-Host '=== AI Scraping Defense: Development Quickstart ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

# Prepare local directories
if (Test-Path "setup_local_dirs.ps1") { & "$PSScriptRoot/setup_local_dirs.ps1" } else { bash ./setup_local_dirs.sh }

# Generate local secrets
& "$PSScriptRoot/Generate-Secrets.ps1"

# Reset virtual environment
& "$PSScriptRoot/reset_venv.ps1"

# Run tests
& "$PSScriptRoot/.venv/Scripts/python.exe" test/run_all_tests.py

# Launch with Docker Compose
docker-compose up --build -d

Write-Host 'Development environment is up and running!' -ForegroundColor Green
