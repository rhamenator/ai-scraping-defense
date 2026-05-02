<#
.SYNOPSIS
    Quickly sets up the stack using Apache or Nginx as a reverse proxy.
.DESCRIPTION
    Launches docker services and selects the desired proxy with runtime compatibility checks.
#>
param(
    [ValidateSet('apache','nginx')]
    [string]$Proxy = 'nginx'
)

. "$PSScriptRoot/Lib.ps1"

if (-not $IsWindows) {
    Write-Error "Unsupported OS. This entrypoint supports Windows only. Use scripts/linux/*.sh on Linux or scripts/macos/*.zsh on macOS."
    exit 1
}

$ErrorActionPreference = 'Stop'
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -Path $RootDir

Write-Host '=== AI Scraping Defense: Proxy Quick Start ===' -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

Ensure-NoNewPrivileges

if ($Proxy -eq 'nginx') {
    $desiredHttpPort = if ($env:NGINX_HTTP_PORT) { $env:NGINX_HTTP_PORT } else { Get-EnvFileValue -Key 'NGINX_HTTP_PORT' }
    $desiredHttpsPort = if ($env:NGINX_HTTPS_PORT) { $env:NGINX_HTTPS_PORT } else { Get-EnvFileValue -Key 'NGINX_HTTPS_PORT' }
    if (-not $desiredHttpPort) { $desiredHttpPort = '80' }
    if (-not $desiredHttpsPort) { $desiredHttpsPort = '443' }

    $desiredHttpPortInt = [int]$desiredHttpPort
    $desiredHttpsPortInt = [int]$desiredHttpsPort

    if ((Test-PortInUse -Port $desiredHttpPortInt) -and -not (Test-NginxOwnsPort -HostPort $desiredHttpPortInt -ContainerPort 80)) {
        foreach ($candidate in @(8088, 8081, 18080)) {
            if (-not (Test-PortInUse -Port $candidate)) {
                $env:NGINX_HTTP_PORT = "$candidate"
                Write-Host "Port $desiredHttpPort is in use; using NGINX_HTTP_PORT=$candidate for this run." -ForegroundColor Yellow
                break
            }
        }
    }

    if ((Test-PortInUse -Port $desiredHttpsPortInt) -and -not (Test-NginxOwnsPort -HostPort $desiredHttpsPortInt -ContainerPort 443)) {
        foreach ($candidate in @(8443, 9443, 18443)) {
            if (-not (Test-PortInUse -Port $candidate)) {
                $env:NGINX_HTTPS_PORT = "$candidate"
                Write-Host "Port $desiredHttpsPort is in use; using NGINX_HTTPS_PORT=$candidate for this run." -ForegroundColor Yellow
                break
            }
        }
    }
}

if ($Proxy -eq 'apache') {
    Write-Host 'Launching stack with Apache reverse proxy...' -ForegroundColor Cyan
    Invoke-Compose @('up','-d','apache_proxy')
}
else {
    Write-Host 'Launching stack with Nginx reverse proxy...' -ForegroundColor Cyan
    Invoke-Compose @('up','-d','nginx_proxy')
}

Write-Host "Stack is running behind $Proxy." -ForegroundColor Green
