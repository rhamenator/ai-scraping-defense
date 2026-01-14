param()
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}
$ErrorActionPreference = 'Stop'
Write-Host "Creating necessary local directories for AI Scraping Defense Stack..." -ForegroundColor Cyan

$dirs = @('config','data','db','logs','logs/nginx','models','archives','secrets','nginx/errors','nginx/certs')
foreach ($d in $dirs) { New-Item -ItemType Directory -Path $d -Force | Out-Null }

$certDir = 'nginx/certs'
$certPath = Join-Path $certDir 'tls.crt'
$keyPath = Join-Path $certDir 'tls.key'
if (-not (Test-Path $certPath) -or -not (Test-Path $keyPath)) {
    $openssl = Get-Command openssl -ErrorAction SilentlyContinue
    if ($openssl) {
        Write-Host 'Generating a self-signed TLS certificate for local HTTPS...' -ForegroundColor Cyan
        & $openssl.Path req -x509 -nodes -newkey rsa:2048 -days 3650 `
            -keyout $keyPath `
            -out $certPath `
            -subj "/CN=localhost"
    } else {
        Write-Warning 'OpenSSL not found; skipping TLS certificate generation.'
    }
}

# Placeholder secrets
$secretFiles = @('pg_password.txt','redis_password.txt','smtp_password.txt','external_api_key.txt','ip_reputation_api_key.txt','community_blocklist_api_key.txt')
foreach ($f in $secretFiles) { New-Item -ItemType File -Path (Join-Path 'secrets' $f) -Force | Out-Null }

if (Test-Path 'secrets') {
    $icacls = Get-Command icacls -ErrorAction SilentlyContinue
    if ($icacls) {
        try {
            & $icacls.Path 'secrets' /inheritance:r /grant:r "$env:USERNAME:(OI)(CI)F" | Out-Null
        } catch {
            Write-Warning "Unable to set ACLs for the secrets directory: $($_.Exception.Message)"
        }
    } else {
        Write-Warning 'icacls not found; skipping ACL hardening for secrets.'
    }
}

Write-Host '---------------------------------------------------------------------'
Write-Host 'IMPORTANT REMINDERS:'
Write-Host "1. Place your actual 'robots.txt' into the './config/' directory."
Write-Host "2. Place your 'init_markov.sql' into the './db/' directory."
Write-Host '3. Populate all files in ./secrets/ with your actual secret values.'
Write-Host "4. For Kubernetes: ensure you have created 'kubernetes/postgres-init-script-cm.yaml'."
Write-Host "5. For Kubernetes: update 'kubernetes/secrets.yaml' with your base64 encoded secrets."
Write-Host '6. Build your Docker images, push them, and update image references in Kubernetes YAML.'
Write-Host '---------------------------------------------------------------------'
Write-Host 'Directory structure setup complete.' -ForegroundColor Green
