<#
.SYNOPSIS
  Start a Cloudflare Tunnel for local stack testing behind ISP port blocks.

.DESCRIPTION
  Quick tunnel:
    .\scripts\windows\start_cloudflare_tunnel.ps1

  Named tunnel:
    $env:CLOUDFLARE_TUNNEL_TOKEN="..."; .\scripts\windows\start_cloudflare_tunnel.ps1

  Target override:
    .\scripts\windows\start_cloudflare_tunnel.ps1 -TargetUrl "http://localhost:8080"
#>

[CmdletBinding()]
param(
    [string]$TargetUrl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -Path $RootDir

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Key,
        [string]$Path = ".env"
    )
    if (-not (Test-Path $Path)) {
        return ""
    }
    $line = Get-Content -Path $Path | Where-Object { $_ -match "^$Key=" } | Select-Object -Last 1
    if (-not $line) {
        return ""
    }
    return ($line -split "=", 2)[1].Trim()
}

function To-DockerOriginUrl {
    param([Parameter(Mandatory = $true)][string]$Url)
    $updated = $Url -replace '^http://localhost:', 'http://host.docker.internal:'
    $updated = $updated -replace '^https://localhost:', 'https://host.docker.internal:'
    return $updated
}

$defaultPort = Get-EnvValue -Key "NGINX_HTTP_PORT"
if (-not $defaultPort) { $defaultPort = "80" }

if (-not $TargetUrl) {
    $TargetUrl = $env:CLOUDFLARE_TUNNEL_TARGET_URL
}
if (-not $TargetUrl) {
    $TargetUrl = "http://localhost:$defaultPort"
}

$tunnelToken = $env:CLOUDFLARE_TUNNEL_TOKEN

Write-Host "=== Cloudflare Tunnel Launcher (Windows) ===" -ForegroundColor Cyan
Write-Host "Repository root: $RootDir"
Write-Host "Target URL:      $TargetUrl"
Write-Host ""

if ($tunnelToken) {
    Write-Host "Mode: named tunnel (token-based)"
} else {
    Write-Host "Mode: quick tunnel (temporary trycloudflare.com URL)"
}
Write-Host ""

$cloudflaredCmd = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cloudflaredCmd) {
    if ($tunnelToken) {
        & cloudflared tunnel --no-autoupdate run --token $tunnelToken
    } else {
        & cloudflared tunnel --no-autoupdate --url $TargetUrl
    }
    exit $LASTEXITCODE
}

Write-Warning "cloudflared binary not found; attempting Docker fallback..."
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    throw "Neither cloudflared nor docker is available."
}

if ($tunnelToken) {
    & docker run --rm cloudflare/cloudflared:latest tunnel --no-autoupdate run --token $tunnelToken
    exit $LASTEXITCODE
}

$dockerTargetUrl = To-DockerOriginUrl -Url $TargetUrl
& docker run --rm cloudflare/cloudflared:latest tunnel --no-autoupdate --url $dockerTargetUrl
exit $LASTEXITCODE
