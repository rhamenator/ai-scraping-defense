# Requires Docker Desktop
param()
$adminCheck = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $adminCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Warning "It's recommended to run this script from an elevated PowerShell session."
}
$ErrorActionPreference = 'Stop'
Write-Host "=== Launching Fake Website ===" -ForegroundColor Cyan

if (-not (Test-Path '.env')) {
    Copy-Item 'sample.env' '.env'
    Write-Host 'Created .env from sample.env'
}

# Add or update REAL_BACKEND_HOST
$content = Get-Content '.env'
if ($content -match '^REAL_BACKEND_HOST=') {
    $content = $content -replace '^REAL_BACKEND_HOST=.*', 'REAL_BACKEND_HOST=http://fake_website:80'
    $content | Set-Content '.env'
} else {
    Add-Content '.env' 'REAL_BACKEND_HOST=http://fake_website:80'
}

# Create a minimal fake site
$siteDir = Join-Path (Get-Location) 'fake_site'
if (-not (Test-Path $siteDir)) { New-Item $siteDir -ItemType Directory | Out-Null }
$index = Join-Path $siteDir 'index.html'
if (-not (Test-Path $index)) {
@'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Fake Website</title>
</head>
<body>
  <h1>Hello from the Fake Website!</h1>
  <p>If you see this page through the proxy, the stack is working.</p>
</body>
</html>
'@ | Set-Content $index
}

# Start the stack
docker-compose up --build -d

$networkName = . "$PSScriptRoot/Lib.ps1"; Get-DefenseNetwork
if (-not $networkName) {
    Write-Error 'Could not locate the defense_network. Is the stack running?'
    exit 1
}

if (-not (docker ps -q -f name=fake_website)) {
    docker run -d --name fake_website `
        --network $networkName `
        -p 8081:80 `
        -v "$siteDir:/usr/share/nginx/html:ro" `
        nginx:alpine
} else {
    Write-Host 'fake_website container already running'
}

Write-Host 'Fake site available at http://localhost:8081'
Write-Host 'Proxy via AI Scraping Defense at http://localhost:8080'
