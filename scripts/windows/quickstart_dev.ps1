<#
.SYNOPSIS
    Sets up the development environment with a single command.
#>
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}
$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
. "$PSScriptRoot/Lib.ps1"

if (-not $IsWindows) {
    Write-Error "Unsupported OS. This entrypoint supports Windows only. Use scripts/linux/*.sh on Linux or scripts/macos/*.zsh on macOS."
    exit 1
}
Set-Location -Path $RootDir
Write-Host '=== AI Scraping Defense: Development Quickstart ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

# Prepare local directories
if (Test-Path (Join-Path $PSScriptRoot "setup_local_dirs.ps1")) {
    & "$PSScriptRoot/setup_local_dirs.ps1"
} else {
    bash "$PSScriptRoot/../linux/setup_local_dirs.sh"
}

# Generate local secrets
& "$PSScriptRoot/Generate-Secrets.ps1"

# Reset virtual environment
& "$PSScriptRoot/reset_venv.ps1"

# Install Python requirements with constraints
& "$RootDir/.venv/Scripts/pip.exe" install -r requirements.txt -c constraints.txt

# Validate .env configuration
& "$RootDir/.venv/Scripts/python.exe" scripts/validate_env.py

# Run tests
& "$RootDir/.venv/Scripts/python.exe" test/run_all_tests.py

# Launch with Docker Compose
. "$PSScriptRoot/Lib.ps1"
Invoke-Compose @('up','--build','-d')

Write-Host 'Development environment is up and running!' -ForegroundColor Green
