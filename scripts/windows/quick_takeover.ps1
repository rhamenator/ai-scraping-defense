<#
.SYNOPSIS
    Stops existing Apache or Nginx services and runs the stack on port 80.
.DESCRIPTION
    Shuts down host web servers and launches the docker services with the selected proxy.
#>
param(
    [ValidateSet('apache','nginx')]
    [string]$Proxy = 'nginx'
)

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location -Path $RootDir

Write-Host '=== AI Scraping Defense: Server Takeover ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

$services = @('apache2','apache','nginx')
foreach ($svc in $services) {
    $service = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($service -and $service.Status -eq 'Running') {
        Write-Host "Stopping $svc service..." -ForegroundColor Yellow
        Stop-Service -Name $svc -Force
    }
}

if ($Proxy -eq 'apache') {
    Write-Host 'Launching stack with Apache on port 80...' -ForegroundColor Cyan
    $env:APACHE_HTTP_PORT = '80'
    Invoke-Compose @('up','-d','apache_proxy')
} else {
    Write-Host 'Launching stack with Nginx on port 80...' -ForegroundColor Cyan
    Invoke-Compose @('up','-d','nginx_proxy')
}

Write-Host "Stack is now serving on port 80 via $Proxy." -ForegroundColor Green
 . "$PSScriptRoot/Lib.ps1"

if (-not $IsWindows) {
    Write-Error "Unsupported OS. This entrypoint supports Windows only. Use scripts/linux/*.sh on Linux or scripts/macos/*.zsh on macOS."
    exit 1
}
